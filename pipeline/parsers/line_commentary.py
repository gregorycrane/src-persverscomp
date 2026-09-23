"""doc_type: line_commentary (Jebb-style and Sidgwick-style lemma/note markup).
Relocated from Cell 4."""
import re
from html import escape
from collections import OrderedDict
import os
from urllib.parse import urlsplit
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

def parse_line_commentary_tei(path, master_intervals, lineno_sigil=None,
                              anchor_axis="native", reference_sigil=None,
                              show_reference_line=False,
                              content_view="original",
                              translation_storage="parallel"):
    """Line-keyed verse commentary (e.g. Jebb on Sophocles).

    Bins every comment into the SAME canonical card as the verse baseline, using
    a running *line anchor* drawn (in priority order) from a div's numeric @n
    (commlines carry the exact verse line number) or, failing that, the start
    line of the nearest section's @corresp range. Heads and paragraphs are
    rendered wherever they occur, which tolerates the file's mixed intro
    wrappers (some intros are <div subtype="commline" n="introduction">, others
    <div subtype="section" n="introduction">).

    Every commline (and every @corresp-anchored section) now also emits a
    visible ".comm-lineno" label — e.g. "1" or "4-6" — as the first thing in
    its block, so the rendered commentary column shows which verse line(s)
    each cluster of notes covers. This is purely a display marker; it does not
    affect binning (binning still uses the *first* numeral of the anchor, via
    _interval_for_line).

    Returns data[bk][card_label] = {"1": combined_html}, matching
    parse_poetry_cards_tei so it drops straight onto the alignment grid.
    """
    if not os.path.exists(path):
        return None
    if not master_intervals:
        print("  \u26a0 line_commentary needs a poetry verse edition in the same "
              "work (no master_intervals built) \u2014 skipping.")
        return None
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())
    if text_entry is None:
        return None

    data = OrderedDict((bk, OrderedDict()) for bk in master_intervals)
    flat_intervals = [iv for ivs in master_intervals.values() for iv in ivs]

    def _interval_for_line(bk, line_num):
        if not str(line_num).isdigit():
            return None
        ln = int(line_num)
        for iv in flat_intervals:
            if iv["book"] == bk and iv["start_line"] <= ln <= iv["end_line"]:
                return iv
        cand = [iv for iv in flat_intervals if iv["book"] == bk and iv["start_line"] <= ln]
        return cand[-1] if cand else (flat_intervals[0] if flat_intervals else None)

    default_bk = next(iter(master_intervals))
    buffer_map = {}

    def _emit(bk, anchor, html):
        if not (html and html.strip()):
            return
        iv = _interval_for_line(bk, anchor) if anchor else None
        if iv is None:
            iv = flat_intervals[0] if flat_intervals else None
        label = iv["label"] if iv else "1"
        ebk = iv["book"] if iv else bk
        buffer_map.setdefault((ebk, label), []).append(html)

    def _render_lemma_note(lemma_el, note_el):
        """Render one lemma+comment pair. Factored out of _render_p so the
        bare-<seg> case below (commline divs with no <p> wrapper at all --
        see _render_bare_commline_pairs) can reuse the exact same
        lemma/comment -> HTML formatting instead of duplicating it."""
        lemma_html = ""
        if lemma_el is not None:
            lt = extract_text_recursive(lemma_el, strip_paragraphs=True).strip()
            if lt:
                lemma_html = f'<span class="lemma">{lt}</span> '
        body = ""
        if note_el is not None:
            body = extract_text_recursive(note_el, strip_paragraphs=True).strip()
            body = body.lstrip(". \u00a0").strip()
        if not (lemma_html or body):
            return ""
        return f'<div class="comm-entry">{lemma_html}<span class="comm-note">{body}</span></div>'

    def _render_bare_commline_pairs(commline_div):
        """CORRECTED after Wendel's Apollonius scholia showed real content
        vanishing (e.g. book 1 lines 580-639 came back completely empty
        despite the source XML having plenty of commentary there). Cause:
        813 of the file's 2,739 commline divs (30%) put <seg type="lemma">/
        <seg type="comment"> directly under <div type="commline">, with NO
        <p> wrapper -- but the only content-emitting path in this function
        was through <p> (see _render_p / the `tag == "p"` branch below), so
        every one of these 813 entries silently produced nothing at all,
        not even a fallback plain-prose dump.

        Direct children only (a <seg> living inside a <p> is not a direct
        child of the commline div, so already-working <p>-wrapped commlines
        return [] here -- no double-emission, no interference).

        51 of the 813 have MORE THAN ONE lemma/comment pair in the same
        div, so pairing can't just take "the first lemma, the first
        comment" -- that risks cross-matching unrelated pairs. The file
        already gives the real linkage explicitly (ana="#ID" on the lemma,
        xml:id="ID" on its comment), so that's used first; simple
        document-order pairing is only a fallback for the rare case where
        the id link is missing.
        """
        direct_children = list(commline_div)
        lemma_children = [c for c in direct_children
                           if c.tag.split("}")[-1] == "seg" and c.get("type") == "lemma"]
        if not lemma_children:
            return []

        by_id = {}
        for c in direct_children:
            xid = c.get("{http://www.w3.org/XML/1998/namespace}id") or c.get("xml:id")
            if xid:
                by_id[xid] = c

        comment_children = [c for c in direct_children
                             if c.tag.split("}")[-1] == "seg" and c.get("type") == "comment"]
        used_ids = set()
        results = []
        for lemma_el in lemma_children:
            ana = (lemma_el.get("ana") or "").lstrip("#").strip()
            note_el = by_id.get(ana) if ana else None
            if note_el is None:
                for c in comment_children:
                    if id(c) not in used_ids:
                        note_el = c
                        break
            if note_el is not None:
                used_ids.add(id(note_el))
            html = _render_lemma_note(lemma_el, note_el)
            if html:
                results.append(html)
        return results

    def _render_p(p):
        """One <p>: lemma + commentary note, or plain prose.

        Two lemma/note markup conventions exist across commentary sources,
        both recognized here so this keeps working for either:
          - Jebb-style (older files): <mentioned ana="#note_N"> for the
            lemma, <note type="commentary" xml:id="note_N"> anywhere inside
            the <p> for the note body.
          - Sidgwick-style (viaf-named files, e.g. the Eumenides commentary
            once it moved off its old tlg0085.tlg007-keyed filename):
            <seg ana="#note_N" type="lemma"> for the lemma, <seg
            type="comment" xml:id="note_N"> for the note body -- both plain
            <p> children, no <mentioned>/<note> anywhere. Previously only
            the Jebb-style pair was recognized, so every entry in a
            Sidgwick-style file silently fell through to the "plain prose"
            branch below (lemma and note dumped together, undifferentiated)
            instead of raising -- the parser never errors on this, it just
            quietly loses the lemma/note distinction, which is what made it
            easy to miss.
        """
        if content_view == "translation":
            # Machine-translated commentaries retain the source note and put
            # its translated rendering in a sibling <seg type="translation">.
            # Render only those top-level translated notes here: nested
            # translation segments (for an individual <mentioned> or <quote>)
            # are already incorporated into the complete translated note.
            translations = [
                child for child in p
                if child.tag.split("}")[-1] == "seg"
                and child.get("type") == "translation"
                and child.get("{http://www.w3.org/XML/1998/namespace}lang") == "eng"
            ]
            if translations:
                entries = []
                for node in translations:
                    body = extract_text_recursive(node, strip_paragraphs=True).strip()
                    if body:
                        entries.append(
                            f'<div class="comm-entry"><span class="comm-note">{body}</span></div>'
                        )
                return "".join(entries)

            source_notes = [
                child for child in p
                if child.tag.split("}")[-1] == "seg"
                and child.get("type") == "comment"
            ]
            entries = []
            for node in source_notes:
                body = extract_text_recursive(node, strip_paragraphs=True).strip()
                if body:
                    if translation_storage == "in_place":
                        # Some translated commentary files replace the source
                        # prose inside <seg type="comment"> rather than adding
                        # a sibling <seg type="translation">. In that encoding
                        # this body is already English; labelling it as a German
                        # fallback is both noisy and factually wrong.
                        entries.append(
                            f'<div class="comm-entry"><span class="comm-note">{body}</span></div>'
                        )
                    else:
                        # Do not make genuinely untranslated source notes
                        # disappear. The marker exposes partial coverage to
                        # editors when the parallel-translation encoding is used.
                        entries.append(
                            '<div class="comm-entry">'
                            '<span class="comm-note"><em>English translation unavailable; '
                            f'German original follows.</em> {body}</span></div>'
                        )
            return "".join(entries)

        lemma_nodes = []
        note_nodes = []
        for gc in p.iter():
            if gc is p:
                continue
            gtag = gc.tag.split("}")[-1]
            if (
                gtag in ("mentioned", "lem")
                or (gtag == "seg" and gc.get("type") == "lemma")
            ):
                lemma_nodes.append(gc)
                continue
            if (
                (gtag == "note" and gc.get("type") == "commentary")
                or (gtag == "seg" and gc.get("type") == "comment")
            ):
                note_nodes.append(gc)

        # Render every lemma-bearing paragraph in document order. Some
        # Sidgwick paragraphs encode two to four linked pairs (the old logic
        # silently discarded every pair after pair 1), while others put
        # introductory prose or a <gloss> before their sole pair (which the
        # same first-match shortcut also discarded, e.g. Eumenides 426).
        if lemma_nodes or note_nodes:
            def _inner_html(el):
                pieces = [el.text or ""]
                for child in el:
                    pieces.append(extract_text_recursive(
                        child, strip_paragraphs=True, _nested=True
                    ))
                    if child.tail:
                        pieces.append(child.tail)
                return "".join(pieces).strip()

            pieces = []
            if p.text and p.text.strip():
                pieces.append(f'<span class="comm-note">{p.text.strip()}</span>')
            for child in p:
                ctag = child.tag.split("}")[-1]
                if ctag in ("mentioned", "lem") or (ctag == "seg" and child.get("type") == "lemma"):
                    value = _inner_html(child)
                    if value:
                        pieces.append(f'<span class="lemma">{value}</span>')
                elif ctag == "app":
                    # Standalone critical apparatus files conventionally keep
                    # their anchor as <app><lem>…</lem></app>. Treat each lem
                    # as a highlighted lemma without flattening it into the
                    # Latin apparatus prose that follows in app/@tail.
                    for lemma in child.iter():
                        if lemma.tag.split("}")[-1] != "lem":
                            continue
                        value = _inner_html(lemma)
                        if value:
                            pieces.append(f'<span class="lemma">{value}</span>')
                elif ((ctag == "note" and child.get("type") == "commentary")
                      or (ctag == "seg" and child.get("type") == "comment")):
                    value = _inner_html(child).lstrip(". \u00a0").strip()
                    if value:
                        pieces.append(f'<span class="comm-note">{value}</span>')
                else:
                    value = extract_text_recursive(
                        child, strip_paragraphs=True, _nested=True
                    ).strip()
                    if value:
                        pieces.append(value)
                if child.tail and child.tail.strip():
                    pieces.append(f'<span class="comm-note">{child.tail.strip()}</span>')
            return (f'<div class="comm-entry">{" ".join(pieces)}</div>'
                    if pieces else "")

        lemma_el = lemma_nodes[0] if lemma_nodes else None
        note_el = note_nodes[0] if note_nodes else None
        lemma_html = ""
        lemma_text = ""
        if lemma_el is not None:
            lt = extract_text_recursive(lemma_el, strip_paragraphs=True).strip()
            if lt:
                lemma_text = lt
                lemma_html = f'<span class="lemma">{lt}</span> '   # same class <s> uses, inherits .commentary-text .lemma
        if note_el is not None:
            body = extract_text_recursive(note_el, strip_paragraphs=True).strip()
            body = body.lstrip(". \u00a0").strip()  # notes often open with a stray "."
        else:
            body = extract_text_recursive(p, strip_paragraphs=True).strip()
            # A standalone <mentioned> is itself part of the paragraph's text.
            # Once rendered as the highlighted lemma above, remove that same
            # leading text from the prose body so it is not displayed twice.
            if lemma_text and body.startswith(lemma_text):
                body = body[len(lemma_text):].lstrip(" :.\u00a0").strip()
        if not (lemma_html or body):
            return ""
        return f'<div class="comm-entry">{lemma_html}<span class="comm-note">{body}</span></div>'

    # Leading digit-run of an anchor string, e.g. "4" -> "4", "4_6" -> "4",
    # "117-253" -> "117". Used to decide which card a block belongs to; the
    # FULL raw label (with underscores normalized to a dash) is kept separately
    # for display so a range like "4_6" still reads as "4-6" on screen.
    _LEAD_NUM_RE = re.compile(r"(\d+)")

    def _display_label(raw):
        return raw.replace("_", "-").strip()

    cur_bk = default_bk
    cur_anchor = None          # running verse-line anchor (string of digits), used for binning
    cur_anchor_display = None  # human-facing label for the current anchor, used for the visible badge
    cur_reference_display = None  # reference-edition passage from @corresp
    last_emitted_display = None  # avoids repeating the same lineno badge for every sibling <p>
    emitted_source_pages = set()  # OCR often repeats the same <pb> in adjacent commline divs

    def _maybe_emit_lineno_badge():
        nonlocal last_emitted_display
        if not cur_anchor_display:
            return
        native = f"{lineno_sigil} {cur_anchor_display}" if lineno_sigil else cur_anchor_display
        reference = None
        if cur_reference_display and (show_reference_line or cur_reference_display != cur_anchor_display):
            prefix = f"{reference_sigil} " if reference_sigil else "reference "
            reference = f"{prefix}{cur_reference_display}"
        display_key = (native, reference)
        if display_key != last_emitted_display:
            parts = [f'<span class="comm-native-line">{escape(native)}</span>']
            if reference:
                parts.append(f'<span class="comm-reference-line">→ {escape(reference)}</span>')
            _emit(cur_bk, cur_anchor, f'<div class="comm-lineno">{" ".join(parts)}</div>')
            last_emitted_display = display_key

    def _entry_reference(elem):
        """Find a precise reference-edition passage carried by a lemma."""
        for node in elem.iter():
            if node is elem:
                continue
            node_tag = node.tag.split("}")[-1]
            is_lemma = (
                node_tag in ("mentioned", "lem")
                or (node_tag == "seg" and node.get("type") == "lemma")
            )
            if not is_lemma or node.get("type") == "translation":
                continue
            for target in (node.get("corresp") or "").split():
                if target.startswith("#") or ":" not in target:
                    continue
                passage = target.rsplit(":", 1)[-1].strip()
                book_prefix = f"{cur_bk}."
                if cur_bk and passage.startswith(book_prefix):
                    passage = passage[len(book_prefix):]
                if _LEAD_NUM_RE.match(passage):
                    return _display_label(passage)
        return None

    def _walk(elem):
        nonlocal cur_bk, cur_anchor, cur_anchor_display, cur_reference_display
        tag = elem.tag.split("}")[-1]
        if tag == "div":
            subtype = (elem.get("subtype") or elem.get("type") or "").lower()
            n_val = (elem.get("n") or "").strip()
            if subtype == "book" and n_val:
                cur_bk = n_val
            else:
                cur_reference_display = None
                # CORRECTED after Wendel's Apollonius scholia (tlg5012.tlg001,
                # 4 books) exposed a real bug: this branch used to check
                # @corresp BEFORE commline's own @n, and took the corresp
                # target's leading digit run as the line anchor. That's right
                # for single-book sources (Jebb/Sidgwick on Sophocles/
                # Aeschylus), where the target has no book component --
                # ":117-253" -> leading digits ARE the line. But a multi-book
                # work's corresp target is "book.line" (e.g.
                # "urn:...:2.15-2.20"), so the SAME leading-digit grab picked
                # up the BOOK number instead ("2"), not the line -- silently
                # collapsing ~2,735 of Wendel's 2,739 commline entries across
                # all 4 books onto a single early card per book. commline's
                # own @n never has this problem (it's already book-relative,
                # e.g. "23-25a" for book 1 line 23), so check it FIRST now and
                # only fall back to @corresp for non-commline (e.g. "section")
                # anchors, which don't carry a reliable @n of their own.
                n_anchor_set = False
                corresp_anchor = None
                corresp = elem.get("corresp") or ""
                if ":" in corresp:
                    rng = corresp.split()[0].rsplit(":", 1)[-1].strip()
                    book_prefix = f"{cur_bk}."
                    if rng.startswith(book_prefix):
                        rng = rng[len(book_prefix):]
                    m = _LEAD_NUM_RE.match(rng)
                    if m:
                        corresp_anchor = m.group(1)
                        cur_reference_display = _display_label(rng)
                if subtype == "commline" and n_val:
                    m = _LEAD_NUM_RE.match(n_val)
                    if m:
                        cur_anchor = (corresp_anchor if anchor_axis == "corresp" and corresp_anchor
                                      else m.group(1))
                        cur_anchor_display = _display_label(n_val)
                        n_anchor_set = True
                if not n_anchor_set:
                    if ":" in corresp:
                        rng = corresp.rsplit(":", 1)[-1].strip()
                        # Belt-and-suspenders for the corresp fallback itself:
                        # strip a leading "CURRENT_BOOK." component if present,
                        # so even a section-level (non-commline) corresp on a
                        # multi-book work doesn't repeat the same book/line
                        # collision this fix was written for.
                        book_prefix = f"{cur_bk}."
                        if rng.startswith(book_prefix):
                            rng = rng[len(book_prefix):]
                        m = _LEAD_NUM_RE.match(rng)
                        if m:
                            cur_anchor = m.group(1)         # section line-range start, for binning
                            cur_anchor_display = _display_label(rng)   # full range, for the badge
                # NB: a section's @n is an ordinal (1,2,3...), never a line number.

                # Bare <seg type="lemma">/<seg type="comment"> pairs sitting
                # directly under THIS commline div (no <p> wrapper) -- see
                # _render_bare_commline_pairs's docstring. Returns [] for
                # every already-working <p>-wrapped commline, so this is
                # additive only.
                if subtype == "commline":
                    bare_html_list = _render_bare_commline_pairs(elem)
                    if bare_html_list:
                        _maybe_emit_lineno_badge()
                        for html in bare_html_list:
                            _emit(cur_bk, cur_anchor, html)
            for ch in elem:
                _walk(ch)
            return
        if tag == "head":
            h = extract_text_recursive(elem, strip_paragraphs=True).strip()
            if h:
                m = re.match(r"\s*(\d+(?:[-\u2013]\d+)?)", h)     # heads like "117-253: Parodos"
                if m:
                    cur_anchor_display = _display_label(m.group(1))
                    cur_anchor = _LEAD_NUM_RE.match(m.group(1)).group(1)
                _maybe_emit_lineno_badge()
                _emit(cur_bk, cur_anchor, f'<div class="comm-head">{h}</div>')
            return
        if tag == "pb":
            page = (elem.get("n") or "").strip()
            facs = (elem.get("facs") or "").strip()
            parsed = urlsplit(facs)
            safe_facs = parsed.scheme in ("http", "https") and bool(parsed.netloc)
            page_key = (page, facs)
            if safe_facs and page_key not in emitted_source_pages:
                emitted_source_pages.add(page_key)
                _maybe_emit_lineno_badge()
                label = f"Source page {page}" if page else "Source page"
                _emit(
                    cur_bk,
                    cur_anchor,
                    '<div class="comm-source-page">'
                    f'<a href="{escape(facs, quote=True)}" target="_blank" '
                    f'rel="noopener noreferrer" title="Open {escape(label)} scan">'
                    f'{escape(label)} <span aria-hidden="true">↗</span></a></div>',
                )
            return
        if tag == "p":
            _maybe_emit_lineno_badge()
            entry_html = _render_p(elem)
            entry_reference = _entry_reference(elem)
            if entry_reference and entry_reference != cur_reference_display:
                prefix = f"{reference_sigil} " if reference_sigil else "reference "
                entry_html = (
                    '<div class="comm-entry-reference">'
                    f'→ {escape(prefix + entry_reference)}</div>{entry_html}'
                )
            _emit(cur_bk, cur_anchor, entry_html)
            return
        for ch in elem:
            _walk(ch)

    _walk(text_entry)

    for (bk, label), snips in buffer_map.items():
        combined = "".join(snips)
        if combined.strip():
            data.setdefault(bk, OrderedDict())[label] = {"1": combined}
    return data
