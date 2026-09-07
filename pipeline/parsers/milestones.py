"""doc_type: milestone. Relocated from Cell 4."""
from collections import OrderedDict
import os
import re
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

def parse_milestone_tei(path, milestone_unit="bekker", lineno_sigil=None,
                        milestone_scheme="chapter_section"):
    """Bin running prose by embedded <milestone unit='...' n='...'/> anchors.
    For translations (e.g. Twining's Poetics) whose own div hierarchy
    (Part/Section) does NOT match the canonical chapter:section citation scheme,
    but which carry inline milestone anchors keyed to it. The run of text following
    a milestone n='10.1' is binned into data[book]['10']['1'] until the next anchor,
    so the column aligns to the baseline chapter:section grid. Text before the first
    anchor (part/section heads) is dropped, matching the other parsers.

    `milestone_scheme` controls how a dotted milestone @n is split:
      - "chapter_section" (default): n="CHAPTER.SECTION" -- e.g. Twining's
        Bekker-style anchors. The current book comes from the enclosing
        <div subtype="book">.
      - "book_chapter": n="BOOK.CHAPTER" -- e.g. Sadler's Heike translation,
        whose milestones are redundant with the enclosing book div (both say
        book 1) and only actually subdivide down to the CHAPTER level, with
        no finer section anchors at all. The book half of the milestone is
        discarded (the div already supplies it) and section is fixed to "1"
        since this scheme has no section-level granularity to offer.
    """
    if not os.path.exists(path): return None
    root = find_text_root(safe_parse(path).getroot())
    if root is None: return None

    data = OrderedDict()
    current_book = "1"
    cur_ch, cur_sec = None, None
    buf = []

    def flush():
        nonlocal buf
        if cur_ch is None or cur_sec is None:
            buf = []          # unanchored preamble (heads etc.) -> discard
            return
        html = " ".join(t.strip() for t in buf if t and t.strip())
        html = re.sub(r'[ \t\r\n]{2,}', ' ', html).strip()
        if html:
            d = data.setdefault(current_book, OrderedDict())
            ch = d.setdefault(cur_ch, OrderedDict())
            ch[cur_sec] = (ch[cur_sec] + " " + html) if cur_sec in ch else html
        buf = []

    def emit(s):
        if s and s.strip(): buf.append(s)

    def walk(elem):
        nonlocal cur_ch, cur_sec, current_book
        tag = elem.tag.split('}')[-1]

        if tag == 'head':
            # Ordinary structural heads remain hidden, but commentary files may
            # encode the passage being discussed as a TEI lemma quotation in
            # the head.  Dropping that quotation made Pye's recovered note
            # boundaries visible only in the XML, not in the viewer.
            lemma_quotes = [q for q in elem.iter()
                            if q.tag.split('}')[-1] == 'quote'
                            and (q.get('type') or '').lower() == 'lemma']
            for q in lemma_quotes:
                value = extract_text_recursive(q, strip_paragraphs=True).strip()
                if value:
                    emit(f'<span class="lemma">{value}</span>')
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return

        if tag == 'div':
            st = (elem.get('subtype') or elem.get('type') or '').lower()
            if st == 'book' and elem.get('n'):
                flush(); current_book = elem.get('n').strip()

        elif tag == 'milestone':
            u = elem.get('unit') or ''
            nv = (elem.get('n') or '').strip()
            if u == milestone_unit and '.' in nv:
                flush()
                if milestone_scheme == "book_chapter":
                    _, c = nv.split('.', 1)
                    cur_ch, cur_sec = c.strip(), "1"
                else:
                    c, s = nv.split('.', 1)
                    cur_ch, cur_sec = c.strip(), s.strip()
            elif u == 'page' and nv:
                rp = (elem.get('resp') or '').strip()
                emit(f'<span class="milestone bekker-page" data-resp="{rp}" title="{(rp + chr(32) + nv).strip()}">{nv}</span>')
            # other milestone units (line, etc.): no display, no split
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return

        elif tag == 'hi':
            emit(extract_text_recursive(elem, strip_paragraphs=True))
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return

        elif tag == 'note':
            note_text = extract_text_recursive(elem, strip_paragraphs=True).strip()
            if note_text: emit(f'<span class="note">[{note_text}]</span>')
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return

        if elem.text and elem.text.strip():
            emit(elem.text)
        for ch in elem:
            walk(ch)
        if elem.tail and elem.tail.strip():
            emit(elem.tail)

    walk(root)
    flush()
    return data
