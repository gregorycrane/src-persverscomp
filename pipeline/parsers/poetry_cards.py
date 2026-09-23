"""doc_type: poetry_cards. Relocated from Cell 4."""
import os
import re
from collections import OrderedDict
from pipeline.core.xml_utils import (
    NS, safe_parse, find_text_root, extract_text_recursive,
    leading_card_milestone_after_speaker, render_app_crit, render_page_break,
)

def parse_poetry_cards_tei(path, master_intervals, lineno_sigil=None, line_remap=None):
    if not os.path.exists(path): return None
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())

    data = OrderedDict((bk, OrderedDict()) for bk in master_intervals)
    flat_intervals, card_n_to_label = [], {}
    for bk, ivs in master_intervals.items():
        for iv in ivs:
            flat_intervals.append(iv)
            card_n_to_label[(bk, iv["card_n"])] = iv["label"]

    # Critical editions use both inline <l>...<app>...</app>...</l> and
    # stand-off <div type="apparatus"><app loc/corresp=...> structures.
    # Index the latter before the streaming walk so they can be attached to
    # their verse lines rather than flattened as ordinary Greek text.  Do the
    # same for commentary <note target="#line-id"> blocks.
    def _tag(e): return e.tag.split("}")[-1]
    parent = {child: par for par in text_entry.iter() for child in par}
    note_targets = {
        (e.get("target") or "").lstrip("#")
        for e in text_entry.iter()
        if _tag(e) == "ref" and e.get("type") == "note" and e.get("target")
    }
    footnote_lookup = {
        e.get("{http://www.w3.org/XML/1998/namespace}id"): e
        for e in text_entry.iter()
        if (_tag(e) == "note"
            and e.get("{http://www.w3.org/XML/1998/namespace}id") in note_targets)
    }
    lines = [e for e in text_entry.iter() if _tag(e) == "l" and e.get("n")]
    line_by_n = {e.get("n"): e for e in lines}
    line_id_to_n = {
        e.get("{http://www.w3.org/XML/1998/namespace}id"): e.get("n")
        for e in lines if e.get("{http://www.w3.org/XML/1998/namespace}id")
    }

    def _expand_numeric_spec(value):
        """Expand Wecklein-style loc values into existing line numbers."""
        value = (value or "").strip().replace("–", "-")
        out = []
        for piece in re.split(r"[\s,]+", value):
            if not piece: continue
            m = re.fullmatch(r"(\d+)-(\d+)", piece)
            if m:
                a, b = map(int, m.groups())
                if b < a:
                    # Abbreviated traditional references: 413-15 = 413-415,
                    # 1406-11 = 1406-1411.
                    tail = m.group(2)
                    b = int(str(a)[:-len(tail)] + tail)
                out.extend(str(n) for n in range(a, b + 1) if str(n) in line_by_n)
                continue
            m = re.fullmatch(r"(\d+)sq\.?", piece, re.I)
            if m:
                a = int(m.group(1))
                out.extend(str(n) for n in (a, a + 1) if str(n) in line_by_n)
                continue
            m = re.fullmatch(r"(\d+)sqq\.?", piece, re.I)
            if m:
                # The end is deliberately unspecified; anchor the entry at
                # its stated first line and preserve @loc for human reading.
                if m.group(1) in line_by_n: out.append(m.group(1))
                continue
            if piece in line_by_n: out.append(piece)
        return list(dict.fromkeys(out))

    def _pointer_lines(elem):
        pointers = (elem.get("corresp") or elem.get("target") or "").split()
        nums = []
        for pointer in pointers:
            key = pointer.lstrip("#")
            if key in line_id_to_n: nums.append(line_id_to_n[key])
            elif key.startswith("l.") and key[2:] in line_by_n: nums.append(key[2:])
        if nums: return list(dict.fromkeys(nums))
        if elem.get("from"):
            start = (elem.get("from") or "").lstrip("#")
            end = (elem.get("to") or elem.get("from") or "").lstrip("#")
            if start.startswith("l."): start = start[2:]
            if end.startswith("l."): end = end[2:]
            if start.isdigit() and end.isdigit():
                return [str(n) for n in range(int(start), int(end) + 1) if str(n) in line_by_n]
        return _expand_numeric_spec(elem.get("loc"))

    def _card_key(line_n):
        if not str(line_n).isdigit(): return None
        n = int(line_n)
        for iv in flat_intervals:
            if iv["start_line"] <= n <= iv["end_line"]:
                return iv["book"], iv["label"]
        return None

    def _one_anchor_per_card(targets):
        anchors = []
        seen = set()
        for n in targets:
            key = _card_key(n) or ("line", n)
            if key not in seen:
                seen.add(key); anchors.append(n)
        return anchors

    apps_by_line, notes_by_line = {}, {}
    unlocated_apps = []
    detached_containers = set()
    for app in (e for e in text_entry.iter() if _tag(e) == "app"):
        anc = parent.get(app)
        if anc is not None and _tag(anc) == "l":
            continue                         # existing inline behavior
        targets = _pointer_lines(app)
        if not targets:
            # Preserve an unlocated colophon/editorial subscription, but do
            # not pretend it belongs to a verse.  It is displayed once at
            # the end of the edition as an explicitly unlocated marker.
            unlocated_apps.append(app)
            if anc is not None and _tag(anc) == "div" and (anc.get("type") or "").lower() == "apparatus":
                detached_containers.add(anc)
            continue
        for anchor in _one_anchor_per_card(targets):
            apps_by_line.setdefault(anchor, []).append((app, targets))
        if anc is not None and _tag(anc) == "div" and (anc.get("type") or "").lower() == "apparatus":
            detached_containers.add(anc)

    for div in (e for e in text_entry.iter()
                if _tag(e) == "div" and (e.get("type") or "").lower() == "commentary"):
        found = False
        for note in (e for e in div.iter() if _tag(e) == "note"):
            targets = _pointer_lines(note)
            if not targets: continue
            found = True
            for anchor in _one_anchor_per_card(targets):
                notes_by_line.setdefault(anchor, []).append((note, targets))
        if found: detached_containers.add(div)

    def _compact_lines(nums):
        vals = [int(n) for n in nums if str(n).isdigit()]
        if not vals: return ", ".join(nums)
        if len(vals) > 2 and vals == list(range(vals[0], vals[-1] + 1)):
            return f"{vals[0]}–{vals[-1]}"
        return ", ".join(str(n) for n in vals)

    def _targeted_notes_html(line_n):
        rendered = []
        for note, targets in notes_by_line.get(line_n, []):
            body = extract_text_recursive(note, strip_paragraphs=True).strip()
            if not body: continue
            source_label = _compact_lines(targets)
            smyth = []
            for n in targets:
                cref = (line_by_n[n].get("corresp") or "").rsplit(":", 1)[-1]
                smyth.append(cref if cref else n)
            ref_label = _compact_lines(smyth)
            rendered.append(
                f'<span class="note targeted-note" data-target-lines="{source_label}">'
                f'[<b class="note-id">{source_label} → Smyth {ref_label}</b> {body}]</span>')
        return "".join(rendered)

    def _attach_standoff(line_elem, html):
        line_n = line_elem.get("n") or ""
        for app, targets in apps_by_line.get(line_n, []):
            lem = next((c for c in app if _tag(c) == "lem"), None)
            lemma = "".join(lem.itertext()).strip() if lem is not None else ""
            inline = render_app_crit(app)
            if lemma and lemma in html:
                html = html.replace(lemma, inline, 1)
            else:
                marker = render_app_crit(app, show_lemma=False)
                html = html[:-6] + marker + "</div>" if html.endswith("</div>") else html + marker
        if lines and line_elem is lines[-1]:
            for app in unlocated_apps:
                marker = render_app_crit(app, show_lemma=False)
                html += (f'<span class="note targeted-note unlocated-apparatus">'
                         f'[<b class="note-id">Unlocated apparatus</b> {marker}]</span>')
        return html + _targeted_notes_html(line_n)

    # Poem-carded works (Propertius etc.) label cards with the bare poem
    # number/name itself ("2", "8a", ...), never a "start-end" line range --
    # only the milestone-carded builder ever produces a hyphenated label.
    # The line-number fallback below assumes line numbers are unique within
    # a book (true for Homer/Vergil's continuous numbering); for elegy, line
    # numbers reset every poem, so e.g. poem 2's own line 1 would spuriously
    # match poem 1's 1-38 interval (scanned first) and get merged into it.
    # Detect that shape once and disable the fallback entirely for it -- the
    # div subtype="poem" boundary check above is the sole source of truth.
    is_poem_carded = bool(flat_intervals) and all('-' not in iv["label"] for iv in flat_intervals)

    # If this edition carries Storr card milestones, anchor on them and ignore
    # its own <l n> entirely (same treatment the Greek baseline gets).
    has_card_milestones = any(
        e.tag.split("}")[-1] == "milestone" and e.get("unit") == "card"
        for e in text_entry.iter())

    current_book = next(iter(master_intervals))
    cur_label = None
    buffer_map = {}
    pending_page_breaks = []

    def _add_content(bk, label, html):
        if html and html.strip():
            buffer_map.setdefault((bk, label), []).append(html)

    def _find_interval_for_line(bk, line_num):
        if not str(line_num).isdigit(): return None
        ln = int(line_num)
        for iv in flat_intervals:
            if iv["book"] == bk and iv["start_line"] <= ln <= iv["end_line"]: return iv
        for iv in flat_intervals:
            if iv["book"] == bk and iv["start_line"] <= ln: return iv
        # Book-scoped fallback (e.g. an argument line numbered "0", before
        # any card's own start_line): stay within THIS book. The old bare
        # `return flat_intervals[0]` returned the first interval in the
        # WHOLE flattened list across every book (book 1's), silently
        # reassigning current_book to book 1 whenever a book's own bounded
        # lookups found nothing -- which corrupted every book after the
        # first (see the tag != "div" note above for how this surfaced).
        for iv in flat_intervals:
            if iv["book"] == bk: return iv
        return flat_intervals[0] if flat_intervals else None

    def _get_first_line_num(node):
        if node.tag.split("}")[-1] == "l": return node.get("n")
        for ch in node.iter():
            if ch.tag.split("}")[-1] == "l": return ch.get("n")
        return None

    def _walk(elem):
        nonlocal current_book, cur_label
        tag = elem.tag.split("}")[-1]

        if elem in detached_containers:
            return

        # Dramatic editions may include a TEI cast list before the text.
        # It supplies identifiers for <sp @who> but is metadata, not part of
        # the running passage, so do not print the entire dramatis personae in
        # the first card.
        if tag == "castList":
            return

        # A few dramatic editions put the opening card milestone immediately
        # AFTER <speaker> inside <sp>.  Look ahead before walking the children
        # so the speaker label joins the speech on the new card instead of
        # being emitted at the end of the preceding one.
        if tag == "sp":
            opening_milestone = leading_card_milestone_after_speaker(elem)
            if opening_milestone is not None:
                n_val = (opening_milestone.get("n") or "").strip()
                if n_val and (current_book, n_val) in card_n_to_label:
                    cur_label = card_n_to_label[(current_book, n_val)]

        # Some editions (e.g. Evelyn-White's 1914 Theogony translation) embed
        # the card milestone AS THE FIRST CHILD of <l> rather than as a
        # preceding sibling (contrast the Greek baseline, which always puts
        # it before <l>). Because <l>/<stage> are leaves below — their full
        # text is pulled in one shot via extract_text_recursive and we never
        # recurse into them with _walk — a milestone nested this way is
        # never otherwise seen, so the card boundary silently never advances
        # and the whole text collapses into the first card. Check for it here.
        if tag in ("l", "stage"):
            for desc in elem.iter():
                if desc is elem:
                    continue
                if desc.tag.split("}")[-1] == "milestone" and desc.get("unit") == "card":
                    n_val = (desc.get("n") or "").strip()
                    if n_val and (current_book, n_val) in card_n_to_label:
                        cur_label = card_n_to_label[(current_book, n_val)]
                    break  # only the leading milestone (if any) should matter

        if tag == "div":
            subtype = (elem.get("subtype") or elem.get("type") or "").lower()
            n_val = (elem.get("n") or "").strip()
            # "canto" is a book-level division for the ottava-rima epics
            # (Ariosto): treated exactly like <div subtype="book">, with the
            # stanza <lg>s inside it as the cards (see the "lg" branch below).
            if subtype in ("book", "canto") and n_val:
                current_book = n_val
                # Kill stale carry-over: without this, cur_label keeps
                # whatever card label the PREVIOUS book last set, and if
                # this new book has any content before its own first card
                # milestone actually lands (a head/argument, a milestone
                # whose @n doesn't match card_n_to_label, etc.) that content
                # -- and sometimes a whole card's worth of it -- gets bucketed
                # under (new book, previous book's last label), producing a
                # phantom duplicate card in the new book's own line list.
                # Same fix already applied to parse_card_prose_tei; ported
                # here after the identical symptom showed up for poetry_cards
                # editions (Mooney/Seaton/Brunck on Apollonius, book N+1
                # inheriting book N's final card).
                _ivs = master_intervals.get(current_book)
                cur_label = _ivs[0]["label"] if _ivs else None
            elif subtype in ("card", "poem") and n_val and (current_book, n_val) in card_n_to_label:
                cur_label = card_n_to_label[(current_book, n_val)]
        elif tag == "lg" and (elem.get("type") or "").lower() == "stanza":
            # Ottava-rima cards: each <lg type="stanza" n="S"> under a
            # <div subtype="canto"> IS a card (label = the bare stanza
            # number, poem-carded style). An <lg> with any other type
            # (e.g. Rose's per-canto "argument") is left transparent.
            n_val = (elem.get("n") or "").strip()
            if n_val and (current_book, n_val) in card_n_to_label:
                cur_label = card_n_to_label[(current_book, n_val)]
        elif tag == "milestone" and elem.get("unit") == "card":
            n_val = (elem.get("n") or "").strip()
            if n_val and (current_book, n_val) in card_n_to_label:
                cur_label = card_n_to_label[(current_book, n_val)]
            # else: a milestone whose n is not a master card -> leave cur_label,
            #       its text folds into the current card (and is worth flagging).

        # Line-number fallback ONLY for editions with no milestones at all,
        # and only when cards are genuinely line-ranged (not poem-carded --
        # see is_poem_carded above). Must NOT run on "div" itself: the
        # book-boundary block above already set current_book/cur_label
        # correctly from the div's own @n, but _get_first_line_num on a
        # book <div> recurses into its ENTIRE subtree and returns that
        # book's very first <l> (often an argument line numbered "0",
        # before any card's start_line) -- which matches no interval in
        # THIS book and falls through to _find_interval_for_line's final
        # catch-all, `flat_intervals[0]`, the first interval in the WHOLE
        # flattened list (i.e. book 1's), not this book's. That silently
        # resets current_book to "1" at the top of every OTHER book's
        # subtree, and everything in it gets misfiled into book 1's cards
        # for the rest of that book. Only ever surfaced here because this
        # fallback was previously never exercised: every prior milestone-
        # carded work sets has_card_milestones=True and skips this whole
        # block, so a bookless-argument-line edition (Nonnus) is the first
        # to hit it.
        if not has_card_milestones and not is_poem_carded and tag != "div":
            lh = _get_first_line_num(elem)
            if lh:
                lookup = line_remap.get(str(lh), lh) if line_remap else lh
                iv = _find_interval_for_line(current_book, lookup)
                if iv:
                    cur_label = iv["label"]; current_book = iv["book"]

        label = cur_label
        if not label:
            bk_ivs = master_intervals.get(current_book, [])
            label = bk_ivs[0]["label"] if bk_ivs else "1"

        if tag == "milestone" and elem.get("unit") == "line":
            ln_num = (elem.get("n") or "").strip()
            if ln_num:
                _add_content(current_book, label,
                    f'<span class="inline-line-milestone" title="Line Milestone {ln_num}">{ln_num}</span>')


        if tag == "pb":
            # A physical page boundary commonly precedes running headers and
            # a new card milestone. Delay its visible marker until the next
            # verse so it lands in that verse's card and below the viewer's
            # sticky navigation rather than being hidden behind it.
            pending_page_breaks.append(render_page_break(elem))
            return

        if tag in ("l", "stage"):
            for page_break in pending_page_breaks:
                _add_content(current_book, label, page_break)
            pending_page_breaks.clear()
            rendered = extract_text_recursive(
                elem, strip_paragraphs=True, lineno_sigil=lineno_sigil,
                footnote_lookup=footnote_lookup)
            if tag == "l": rendered = _attach_standoff(elem, rendered)
            _add_content(current_book, label, rendered)
            # The leaf renderer excludes the XML tail: it belongs after the
            # stage/verse, and may contain the rest of a prose speech.
            if elem.tail:
                _add_content(current_book, cur_label, elem.tail)
            return
        elif tag == "p":
            has_verse_children = any(
                c.tag.split("}")[-1] in ("l", "milestone") for c in elem)
            if has_verse_children:
                if elem.text and elem.text.strip():
                    _add_content(current_book, label, elem.text)
                for ch in elem:
                    _walk(ch)
                if elem.tail:
                    _add_content(current_book, label, elem.tail)
                return
            t = extract_text_recursive(elem, strip_paragraphs=True).strip()
            if t: _add_content(current_book, label, f"<p>{t}</p>")
            if elem.tail:
                _add_content(current_book, cur_label, elem.tail)
            return
        elif tag == "note":
            note_id = elem.get("{http://www.w3.org/XML/1998/namespace}id") or elem.get("xml:id") or ""
            if note_id in footnote_lookup:
                # Linked source notes are rendered at their in-text <ref>
                # markers. Do not collect the stand-off register into the
                # final card as an unrelated block of notes.
                return
            t = extract_text_recursive(elem, strip_paragraphs=True).strip()
            if t:
                # Standalone end-of-poem notes (apparatus criticus etc.) carry
                # an @xml:id like "n1.1.13" (BOOK.POEM.LINE, matching the
                # inline <note target="#n1.1.13"/> anchor back in the verse).
                # Once detached from that anchor down here, the bare note
                # text alone doesn't say which line it's about -- show the
                # id (dropping the leading "n") so it's actually useful.
                if note_id.startswith("n"):
                    note_id = note_id[1:]
                id_prefix = f'<b class="note-id">{note_id}</b> ' if note_id else ''
                _add_content(current_book, label, f'<span class="note">[{id_prefix}{t}]</span>')
            if elem.tail:
                _add_content(current_book, cur_label, elem.tail)
            return

        if elem.text and elem.text.strip():
            _add_content(current_book, label, elem.text)
        for ch in elem:
            _walk(ch)
        if elem.tail:
            _add_content(current_book, label, elem.tail)

    _walk(text_entry)
    for (bk, label), snips in buffer_map.items():
        combined = " ".join(t.strip() for t in snips if t.strip())
        if combined:
            data.setdefault(bk, OrderedDict())[label] = {"1": combined}
    return data

    """Prose translation/edition with NO <l> tags, segmented only by embedded
    baseline card milestones <milestone unit='card' edRef='Storr' n='S'/> that
    commonly sit INSIDE <p>/<s>. Streams content in document order and bins each
    run into the Storr card named by the most recent card milestone, so output is
    keyed by Storr card label and aligns to the grid. <s> sentences are rendered
    atomically (balanced markup) and a card milestone that opens a sentence
    switches the card before that sentence is binned."""
