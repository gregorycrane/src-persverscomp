"""Canonical line/milestone interval builders. Relocated from Cell 4."""
import os
import re
from pipeline.core.xml_utils import safe_parse, find_text_root

def build_poetry_canonical_intervals(editions_dict):
    base_cfg = editions_dict.get("perseus-grc2") or list(editions_dict.values())[0]
    tree = safe_parse(base_cfg["path"])
    text_entry = find_text_root(tree.getroot())

    has_card_milestones = any(
        e.tag.split("}")[-1] == "milestone" and e.get("unit") == "card"
        for e in text_entry.iter())

    book_intervals = {}
    current_book = "1"

    if has_card_milestones:
        # ── existing milestone-carded logic (Homer / Vergil / Aeschylus etc.) ──
        landmarks = []
        for elem in text_entry.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "div":
                subtype = (elem.get("subtype") or elem.get("type") or "").lower()
                if subtype == "book" and elem.get("n"):
                    current_book = elem.get("n").strip()
            elif tag == "milestone" and elem.get("unit") == "card":
                card_n = (elem.get("n") or "").strip()
                if card_n:
                    landmarks.append({"val": card_n, "book": current_book, "lines": []})
            elif tag == "l":
                ln = (elem.get("n") or "").strip()
                if ln and landmarks:
                    m = re.match(r'^(\d+)', ln)
                    # Keep the raw @n string (e.g. "354a") alongside its leading
                    # digit value -- some editions (Eumenides' binding song,
                    # 354-359 / 354a-359a and 372-376 / 372a-376a) re-print a
                    # stanza a second time under lettered line numbers that
                    # digit-strip to the SAME range as the first printing. If
                    # the label below is built purely from the digit value,
                    # both cards compute the identical label string, and since
                    # per-edition content is bucketed by label, the second
                    # (lettered) card's content silently overwrites the first's
                    # -- real text loss in the baseline edition itself, not
                    # just a display quirk. Preserving the suffix keeps their
                    # labels ("354-359" vs "354a-359a") distinct.
                    if m: landmarks[-1]["lines"].append((int(m.group(1)), ln))

        for idx, item in enumerate(landmarks):
            bk = item["book"]
            card_n = item["val"]

            if item["lines"]:
                first_l, first_str = min(item["lines"], key=lambda t: t[0])
                last_l, last_str = max(item["lines"], key=lambda t: t[0])
            else:
                m = re.match(r'^(\d+)', card_n)
                first_l = int(m.group(1)) if m else 1
                first_str = str(first_l)
                if idx + 1 < len(landmarks) and landmarks[idx+1]["book"] == bk:
                    next_card = landmarks[idx+1]["val"]
                    m2 = re.match(r'^(\d+)', next_card)
                    last_l = (int(m2.group(1)) - 1) if m2 else first_l
                else:
                    last_l = first_l
                last_str = str(last_l)

            book_intervals.setdefault(bk, []).append({
                "card_n": card_n,
                "label": f"{first_str}-{last_str}",
                "book": bk,
                "start_line": first_l,
                "end_line": last_l
            })

        return book_intervals

    # ── NEW: div-carded works (elegy / letter-collection style, e.g. Propertius) ──
    # No <milestone unit="card"> exists; instead each <div subtype="poem"> IS the
    # card. card_n/label are the poem's own @n taken VERBATIM (never digit-
    # stripped), so lettered sub-poems -- 8a, 8b, 13a -- stay distinct cards
    # rather than colliding on a shared leading-digit line lookup.
    for elem in text_entry.iter():
        tag = elem.tag.split("}")[-1]
        if tag != "div":
            continue
        subtype = (elem.get("subtype") or elem.get("type") or "").lower()
        n_val = (elem.get("n") or "").strip()
        if subtype == "book" and n_val:
            current_book = n_val
        elif subtype in ("poem", "card") and n_val:
            lines = []
            for l in elem.iter():
                if l.tag.split("}")[-1] == "l":
                    ln = (l.get("n") or "").strip()
                    m = re.match(r'^(\d+)', ln)
                    if m: lines.append(int(m.group(1)))
            first_l = min(lines) if lines else 1
            last_l = max(lines) if lines else first_l
            # A numbered poem is itself the reader-facing citation. Legacy
            # Perseus ``card`` divs instead mark a run of continuous verse
            # lines, so expose their actual line range in the navigation.
            label = n_val if subtype == "poem" or not lines else f"{first_l}-{last_l}"
            book_intervals.setdefault(current_book, []).append({
                "card_n": n_val,
                "label": label,
                "book": current_book,
                "start_line": first_l,
                "end_line": last_l
            })

    if book_intervals:
        return book_intervals

    # ── NEW: ottava-rima epics (Ariosto, Orlando Furioso) ──
    # <div subtype="canto" n="C"> ... <lg type="stanza" n="S"> <l n="1">..
    # <l n="8"> ... </lg> ... </div>. Canto is the book; each stanza <lg>
    # is a card whose label is the bare stanza number (poem-carded style,
    # so parse_poetry_cards_tei's is_poem_carded check fires and its line-
    # range fallback stays off -- <l n> resets 1..8 every stanza).
    current_book = "1"
    for elem in text_entry.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "div":
            subtype = (elem.get("subtype") or elem.get("type") or "").lower()
            if subtype == "canto" and elem.get("n"):
                current_book = elem.get("n").strip()
        elif tag == "lg" and (elem.get("type") or "").lower() == "stanza":
            n_val = (elem.get("n") or "").strip()
            if not n_val:
                continue
            lines = []
            for l in elem.iter():
                if l.tag.split("}")[-1] == "l":
                    m = re.match(r'^(\d+)', (l.get("n") or "").strip())
                    if m:
                        lines.append(int(m.group(1)))
            book_intervals.setdefault(current_book, []).append({
                "card_n": n_val,
                "label": n_val,
                "book": current_book,
                "start_line": min(lines) if lines else 1,
                "end_line": max(lines) if lines else 1,
            })

    if book_intervals:
        return book_intervals

    # ── NEW: derive card intervals from a companion translation's @corresp
    # anchors, when the base edition has neither milestones nor poem-divs
    # (e.g. Nonnus/Rouse). Rouse's own TEI paragraphs carry
    # corresp="urn:cts:...:BOOK.LINE" marking the Greek line each paragraph
    # begins at -- reusing THAT editorial segmentation gives human-scale
    # cards (Rouse's own sense-paragraphs) instead of one card per line, and
    # keeps the canonical Greek edition free of synthetic milestones it
    # never had in print. Only fires for a "card_prose" edition entry (the
    # translations dict is folded into editions_dict at both call sites);
    # requires >=1 usable corresp anchor per book to activate for that book.
    corresp_re = re.compile(r':(\d+)\.(\d+)\s*$')
    for _v_id, _cfg in editions_dict.items():
        if _cfg.get("parse_mode") != "card_prose":
            continue
        _cpath = _cfg.get("path")
        if not _cpath or not os.path.exists(_cpath):
            continue
        _ctree = safe_parse(_cpath)
        _ctext_entry = find_text_root(_ctree.getroot())
        _anchors = []  # [(book, line), ...] in document order
        _cur_book = "1"
        for elem in _ctext_entry.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "div":
                subtype = (elem.get("subtype") or elem.get("type") or "").lower()
                if subtype == "book" and elem.get("n"):
                    _cur_book = elem.get("n").strip()
            elif tag == "p":
                m = corresp_re.search(elem.get("corresp") or "")
                if m:
                    _anchors.append((_cur_book, int(m.group(2))))
        if not _anchors:
            continue

        # Max line per book of the BASE edition (already parsed above as
        # text_entry) -- needed to close out each book's final paragraph,
        # which has no following anchor to derive an end line from.
        _max_line_per_book = {}
        _mb = "1"
        for elem in text_entry.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "div":
                subtype = (elem.get("subtype") or elem.get("type") or "").lower()
                if subtype == "book" and elem.get("n"):
                    _mb = elem.get("n").strip()
            elif tag == "l":
                ln = (elem.get("n") or "").strip()
                m = re.match(r'^(\d+)', ln)
                if m:
                    v = int(m.group(1))
                    if v > _max_line_per_book.get(_mb, -1):
                        _max_line_per_book[_mb] = v

        _corresp_intervals = {}
        for i, (bk, ln) in enumerate(_anchors):
            if i + 1 < len(_anchors) and _anchors[i + 1][0] == bk:
                end = _anchors[i + 1][1] - 1
            else:
                end = _max_line_per_book.get(bk, ln)
            _corresp_intervals.setdefault(bk, []).append({
                "card_n": str(ln),
                "label": f"{ln}-{end}",
                "book": bk,
                "start_line": ln,
                "end_line": end
            })
        if _corresp_intervals:
            return _corresp_intervals

    # ── NEW: plain line-numbered epic -- no <milestone unit="card"> and no
    # <div subtype="poem"> (e.g. Nonnus, Dionysiaca). Every single <l> becomes
    # its own one-line "card", keyed off its own @n. The label MUST stay in
    # the hyphenated "start-end" shape the milestone-carded path produces
    # (even though start==end here): parse_poetry_cards_tei's is_poem_carded
    # check treats an all-hyphen-free label set as evidence of poem/elegy
    # numbering and DISABLES its per-line lookup fallback -- a bare "5"
    # instead of "5-5" would silently collapse the whole book into one card.
    current_book = "1"
    for elem in text_entry.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "div":
            subtype = (elem.get("subtype") or elem.get("type") or "").lower()
            if subtype == "book" and elem.get("n"):
                current_book = elem.get("n").strip()
        elif tag == "l":
            ln = (elem.get("n") or "").strip()
            if not ln:
                continue
            m = re.match(r'^(\d+)', ln)
            line_num = int(m.group(1)) if m else 0
            book_intervals.setdefault(current_book, []).append({
                "card_n": ln,
                "label": f"{line_num}-{line_num}",
                "book": current_book,
                "start_line": line_num,
                "end_line": line_num
            })

    return book_intervals

def build_line_remap(tsv_path):
    """From an edition-alignment crosswalk TSV, build {target_line(str): base_line(int)}
    so a NON-baseline edition is binned onto the baseline edition's card structure by
    its TRUE counterpart line, not its own raw line number.
      - split / merge  -> first base (baseline) line of the group
      - target_only    -> preceding base line (attach to the preceding card)
    Returns (base_version, target_version, remap_dict)."""
    base_v = target_v = None
    header, rows = None, []
    with open(tsv_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("#"):
                if (m := re.match(r"#\s*base[^:]*:\s*([\w-]+)", line)) and not base_v:   base_v = m.group(1)
                if (m := re.match(r"#\s*target:\s*([\w-]+)", line))      and not target_v: target_v = m.group(1)
                continue
            if not line.strip():
                continue
            cells = line.split("\t")
            if header is None:
                header = cells; continue
            rows.append(dict(zip(header, cells)))
    _lst = lambda c: [x.strip() for x in (c or "").split(",") if x.strip()]
    remap, last_s = {}, None
    for r in rows:
        base = _lst(r.get("base")); tgt = _lst(r.get("target"))
        s = int(base[0]) if base and base[0].isdigit() else None   # first baseline line; None for target_only
        eff = s if s is not None else last_s                       # target_only -> preceding baseline line
        for b in tgt:
            remap[b] = eff
        if s is not None:
            last_s = s
    return base_v, target_v, remap

def build_milestone_remap(xml_path):
    """For a translation/edition that carries embedded baseline (Storr) card
    milestones <milestone unit='card' edRef='Storr' n='S'/>, map each of its own
    <l n='G'> lines to the Storr line S of the most recent such milestone. This
    bins the text onto Storr's cards by editorial milestone rather than by its
    own (independent) line numbers. Returns {G(str): S(int)}; lines before the
    first card milestone are left unmapped (they fall back to their own number)."""
    root = find_text_root(safe_parse(xml_path).getroot())
    remap, cur_s = {}, None
    for elem in root.iter():
        tag = elem.tag.split('}')[-1]
        if tag == 'milestone' and elem.get('unit') == 'card':
            nv = (elem.get('n') or '').strip()
            if nv.isdigit():
                cur_s = int(nv)
        elif tag == 'l':
            gl = (elem.get('n') or '').strip()
            if gl and cur_s is not None:
                remap[gl] = cur_s
    return remap
