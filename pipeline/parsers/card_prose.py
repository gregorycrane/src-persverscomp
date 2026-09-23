"""doc_type: card_prose. Relocated from Cell 4."""
import os
from collections import OrderedDict
import re
from pipeline.core.xml_utils import (
    NS, safe_parse, find_text_root, extract_text_recursive,
    leading_card_milestone_after_speaker,
)

def parse_card_prose_tei(path, master_intervals, lineno_sigil=None):
    if not os.path.exists(path): return None
    root = find_text_root(safe_parse(path).getroot())
    if root is None: return None
    
    data = OrderedDict()
    for bk in master_intervals: data[bk] = OrderedDict()
    
    card_n_to_label, first_label = {}, None
    flat_intervals = []
    for bk, ivs in master_intervals.items():
        for iv in ivs:
            card_n_to_label[(bk, iv["card_n"])] = iv["label"]
            flat_intervals.append(iv)
            if first_label is None: first_label = iv["label"]

    def _find_interval_for_line(bk, ln):
        """Card whose [start_line, end_line] contains ln in book bk -- same
        two-pass lookup parse_poetry_cards_tei uses for its own line-number
        fallback (exact containment, then first interval at/after ln, then
        just the first interval overall)."""
        for iv in flat_intervals:
            if iv["book"] == bk and iv["start_line"] <= ln <= iv["end_line"]:
                return iv
        for iv in flat_intervals:
            if iv["book"] == bk and iv["start_line"] <= ln:
                return iv
        # Book-scoped fallback -- never fall through to the first interval
        # in the WHOLE flattened list (a different book's), which would
        # silently reassign current_book across a book boundary. See the
        # matching note in parse_poetry_cards_tei's own copy of this helper.
        for iv in flat_intervals:
            if iv["book"] == bk: return iv
        return flat_intervals[0] if flat_intervals else None

    current_book = next(iter(master_intervals))
    cur_label = first_label
    buf = []
    in_p = False   # True while walk() is inside a <p> we're actively building --
                    # suppresses the milestone-triggered flush below so an
                    # embedded card milestone (commonly the first child of a
                    # card's opening <p>, right after <pb/>) can't split that
                    # paragraph's just-emitted line-badge from its own text.
                    # cur_label still updates normally either way.

    def flush():
        nonlocal buf
        html = " ".join(t.strip() for t in buf if t and t.strip())
        html = re.sub(r'[ \t\r\n]{2,}', ' ', html)
        if html:
            d = data.setdefault(current_book, OrderedDict())
            # Wrap chunks in a proper prose-para block to relieve crowding
            formatted_html = f'<div class="prose-para">{html}</div>'
            if cur_label in d and "1" in d[cur_label]:
                d[cur_label]["1"] += " " + formatted_html
            else:
                d.setdefault(cur_label, OrderedDict())["1"] = formatted_html
        buf = []

    def emit(s):
        if s and s.strip(): buf.append(s)

    def walk(elem):
        nonlocal cur_label, current_book, in_p
        tag = elem.tag.split('}')[-1]

        # Defensive handling for <sp><speaker>NAME</speaker><milestone
        # unit="card" .../>...</sp>.  Advance before walking <speaker>, or
        # its label is flushed into the preceding card.  Flush any genuinely
        # pending material first, under the old card.
        if tag == 'sp':
            opening_milestone = leading_card_milestone_after_speaker(elem)
            if opening_milestone is not None:
                nv = (opening_milestone.get('n') or '').strip()
                next_label = card_n_to_label.get((current_book, nv))
                if next_label and next_label != cur_label:
                    flush()
                    cur_label = next_label
        
        if tag == 'div':
            st = (elem.get('subtype') or elem.get('type') or '').lower()
            if st == 'book' and elem.get('n'):
                flush()
                current_book = elem.get('n').strip()
                _ivs = master_intervals.get(current_book)        # ← add
                if _ivs:                                         # ← add
                    cur_label = _ivs[0]["label"]                 # ← add  (kill stale carry-over)
            elif st == 'card' and elem.get('n'):
                next_label = card_n_to_label.get((current_book, elem.get('n').strip()))
                if next_label and next_label != cur_label:
                    flush()
                    cur_label = next_label
        elif tag == 'milestone':
            u = elem.get('unit') or ''
            nv = (elem.get('n') or '').strip()
            if u == 'card':
                if nv and (current_book, nv) in card_n_to_label:
                    next_label = card_n_to_label[(current_book, nv)]
                    if next_label != cur_label:
                        if not in_p:
                            flush()
                        cur_label = next_label
            elif u == 'line' and nv:
                emit(f'<span class="inline-line-milestone" title="Line Milestone {nv}">{nv}</span>')
            elif u == 'page' and nv:
                rp = (elem.get('resp') or '').strip()
                emit(f'<span class="milestone bekker-page" data-resp=\"{rp}\" title=\"{(rp + chr(32) + nv).strip()}\">{nv}</span>')

        elif tag == 'p':
            # Poetry-derived prose translations (card_prose) carry a @corresp
            # per <p> giving the exact verse line-range it renders, e.g.
            # corresp=".../seaton1900-grc2:1.57-1.64" -- but until now that
            # was never read: every <p> just fell through to the generic
            # text/tail walk below with no per-paragraph break at all, so an
            # entire card's worth of paragraphs (often a dozen+) flattened
            # into ONE undifferentiated blob with no line numbers and no
            # paragraph boundaries. Fixed to flush() around each <p> (so it
            # becomes its own .prose-para block, restoring real paragraph
            # breaks for every card_prose work, not just ones with @corresp)
            # and, when @corresp is present, prefix the paragraph with a
            # bracketed line-range badge.
            #
            # The first numeric component may be either BOOK (the usual
            # multi-book shape, ``1.57-1.64``) or CARD (single-book carded
            # poetry, e.g. Beowulf ``53.53-53.58``).  Prefer an actual card
            # number in the current book.  This both keeps the paragraph in
            # that card and strips the correct prefix from the visible badge.
            corresp = elem.get('corresp') or ''
            line_label = None
            _m_bl = re.search(r':(\d+)\.(\d+)', corresp)
            corresp_card_label = None
            corresp_prefix = None
            if _m_bl:
                corresp_prefix = _m_bl.group(1)
                corresp_card_label = card_n_to_label.get((current_book, corresp_prefix))
            if ':' in corresp:
                rng = corresp.rsplit(':', 1)[-1].strip()
                display_prefix = f"{corresp_prefix if corresp_card_label else current_book}."
                parts = [p.strip() for p in rng.split('-')]
                parts = [p[len(display_prefix):] if p.startswith(display_prefix) else p for p in parts]
                rng = '-'.join(p for p in parts if p).replace('_', '-')
                if rng:
                    line_label = rng
            # Route THIS paragraph to its own card via @corresp's starting
            # BOOK.LINE, for card_prose translations with no embedded
            # <milestone unit="card"> (e.g. Rouse on Nonnus) -- without this,
            # cur_label never advances past the book's first card and the
            # entire book's translation collapses into one card. The
            # line_label badge above is cosmetic only; this is what actually
            # buckets the content. flush() first commits whatever preceded
            # this <p> under the OLD cur_label, then cur_label advances.
            if _m_bl:
                if corresp_card_label:
                    if not in_p:
                        flush()
                    cur_label = corresp_card_label
                else:
                    _iv = _find_interval_for_line(_m_bl.group(1), int(_m_bl.group(2)))
                    if _iv:
                        if not in_p:
                            flush()
                        cur_label = _iv["label"]
                        current_book = _iv["book"]
            flush()  # close out whatever preceded this <p> as its own block
            if line_label:
                emit(f'<span class="prose-lineno">[{line_label}]</span>')
            if elem.text and elem.text.strip():
                emit(elem.text)
            in_p = True
            for ch in elem:
                walk(ch)
            in_p = False
            if elem.tail and elem.tail.strip():
                emit(elem.tail)
            flush()  # close THIS paragraph out before the next one starts
            return

        elif tag == 'speaker':
            nm = (elem.text or '').strip()
            if nm: 
                flush() # Isolate block context when a new character speaks
                emit(f'<strong class="speaker-attr">{nm}: </strong>')
            # Skip treating inner children as text nodes to prevent duplication
            if elem.tail and elem.tail.strip():
                emit(elem.tail)
            return

        elif tag == 'stage':
            emit(f' <span class="stage-direction">({extract_text_recursive(elem, strip_paragraphs=True).strip()})</span> ')
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return
        elif tag == 'foreign':
            lang = (elem.get('{http://www.w3.org/XML/1998/namespace}lang') or '').strip()
            cls  = f'foreign foreign-{lang}' if lang else 'foreign'
            emit(f'<span class="{cls}" lang="{lang}">{"".join(elem.itertext())}</span>')
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return

        elif tag == 'seg':
            rend = (elem.get('rend') or '').strip()
            cls  = f'seg seg-{rend}' if rend else 'seg'
            emit(f'<span class="{cls}">{"".join(elem.itertext())}</span>')
            if elem.tail and elem.tail.strip(): emit(elem.tail)
            return
        elif tag == 'choice':
            # Keep choice handling identical across parser modes: show the
            # normalized reading/expansion and retain the diplomatic form in
            # tooltip metadata.  Rendering both <abbr> and <expan> produced
            # strings such as ``q;que``.
            emit(extract_text_recursive(elem, strip_paragraphs=True))
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
