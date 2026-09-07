"""AGDT/Prague-format treebank parser. Relocated from Cell 4."""
import os
import re
import xml.etree.ElementTree as ET
from pipeline.core.xml_utils import NS, safe_parse

AGDT_POS_MAP = {
    'n': 'NOUN', 'v': 'VERB', 't': 'VERB',
    'a': 'ADJ', 'd': 'ADV', 'l': 'DET', 'g': 'PART',
    'r': 'ADP', 'p': 'PRON', 'm': 'NUM', 'c': 'CCONJ',
    'i': 'INTJ', 'e': 'INTJ', 'u': 'PUNCT',
}

def _agdt_upos(postag):
    """First letter of an AGDT 9-position postag -> a UD-style UPOS label,
    so app.js's PUNCT filtering and TB_POS_COLORS coloring work unchanged.
    Anything unrecognized (including '-' for fragmentary/untagged lyric text
    and 'x' for indeclinables) falls through to 'X'."""
    if not postag:
        return None
    return AGDT_POS_MAP.get(postag[0], 'X')

def _ref_from_cite(cite):
    """'urn:cts:greekLit:tlg0085.tlg001:1' -> '1'"""
    if not cite:
        return None
    tail = cite.rsplit(':', 1)[-1]
    return tail or None

def parse_agdt_treebank(path, version_short_id, tg, wk, card_intervals=None):
    """Parse a Perseus/AGDT Prague-XML treebank file (<sentence subdoc=...>
    <word .../></sentence>) into the same (sentences, doc_credits) shape
    produced by parse_conllu_treebank, so everything downstream (treebank_
    sentences ingestion, Cell 1b's flatten step, app.js rendering) is
    format-agnostic and needs no changes for this input type.

    Field mapping from the Prague-XML attributes to the shared schema:
      relation -> deprel   cite -> ref   postag[0] -> upos (see AGDT_POS_MAP)
      postag (whole)  -> xpos
      translation attribute (the gloss-composed literal rendering already
      verified sentence-by-sentence to be self-consistent) -> literal
    """
    if not os.path.exists(path):
        print(f"  ✗ Treebank not found: {path}")
        return [], {'annotators': []}

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"  ✗ XML parse error in {path}: {e}")
        return [], {'annotators': []}
    root = tree.getroot()

    # Document-level annotator credits from the header's respStmt blocks.
    # Cosmetic metadata only -- falls back to an empty list if the header
    # is absent or shaped differently.
    doc_annotators = []
    seen_names = set()
    for resp_stmt in root.iter('respStmt'):
        name_el = resp_stmt.find('persName')
        name = None
        if name_el is not None:
            name = (name_el.text or '').strip()
            if not name:
                n_el = name_el.find('n')
                if n_el is not None:
                    name = (n_el.text or '').strip()
        resp_el = resp_stmt.find('resp')
        resp = (resp_el.text or '').strip() if resp_el is not None else None
        if name and name not in seen_names:
            seen_names.add(name)
            doc_annotators.append({'name': name, 'address': resp})

    line_to_card = {}
    if card_intervals:
        for interval in card_intervals:
            try:
                bk = str(interval['book'])
                start = int(interval['label'].split('-')[0])
                end = int(interval['label'].split('-')[1])
                for ln in range(start, end + 1):
                    line_to_card[f"{bk}.{ln}"] = interval['label']
                    line_to_card[str(ln)] = interval['label']
            except (ValueError, KeyError):
                continue

    def _lookup_card(ref):
        if ref in line_to_card:
            return line_to_card[ref]
        m = re.match(r'^(\d+)', ref)
        if m and m.group(1) in line_to_card:
            return line_to_card[m.group(1)]
        return None

    sentences = []
    for sent_el in root.iter('sentence'):
        subdoc = sent_el.get('subdoc')
        sid = sent_el.get('id')
        translation = sent_el.get('translation')  # gloss-composed literal translation
        annotator_el = sent_el.find('annotator')
        annotator_name = (annotator_el.text or '').strip() if annotator_el is not None else None

        tokens = []
        for w in sent_el.findall('word'):
            wid = w.get('id')
            if wid is None or not wid.isdigit():
                continue
            postag = w.get('postag') or ''
            head_val = w.get('head') or '0'
            tokens.append({
                'id': int(wid),
                'form': w.get('form') or '',
                'lemma': w.get('lemma'),
                'upos': _agdt_upos(postag),
                'xpos': postag or None,
                'feats': None,
                'head': int(head_val) if head_val.isdigit() else 0,
                'deprel': w.get('relation'),
                'gloss': w.get('gloss'),
                'ref': _ref_from_cite(w.get('cite')),
                'translit': None,
                'ltranslit': None,
            })

        if not tokens or not subdoc:
            continue

        first_ref = subdoc.split('-')[0]
        ref_parts = first_ref.split('.')
        book_part = ref_parts[0]
        if card_intervals:
            chapter = _lookup_card(first_ref) or book_part
            section = str(sid) if sid else '1'
        else:
            # Prose, book.chapter.section addressing (e.g. Thucydides
            # "1.89.3"). treebank_sentences has no separate book column, and
            # the client (app.js's _hydrateTreebank) groups sentences purely
            # by this chapter string -- so collapsing to book_part alone
            # would merge every chapter of a book under one key, and even
            # a bare chapter number would collide across different books
            # (book 2 chapter 1 vs book 3 chapter 1 are NOT the same
            # chapter). Encode book into the chapter key itself ("book.chapter",
            # e.g. "1.89") to keep it globally unique -- app.js's lookup
            # constructs this same compound key from payload.book/chapter.
            # The genuine section (the passage/sentence number) is the LAST
            # segment, not ref_parts[1] -- a 2-level "book.section" ref (no
            # chapter subdivision) doesn't have a middle level at all.
            if len(ref_parts) >= 3:
                chapter = f"{ref_parts[0]}.{ref_parts[1]}"
                section = '.'.join(ref_parts[2:])
            elif len(ref_parts) == 2:
                chapter = f"{ref_parts[0]}.1"
                section = ref_parts[1]
            else:
                chapter = f"{book_part}.1"
                section = str(sid) if sid else '1'

        credits = [{'name': annotator_name, 'address': None, 'role': 'primary'}] if annotator_name else None

        sentences.append({
            'subdoc': subdoc,
            'chapter': chapter,
            'section': section,
            'tokens': tokens,
            'prose': None,
            'literal': translation,
            'translit': None,
            'sent_id': sid,
            'credits': credits,
        })

    doc_credits = {'annotators': doc_annotators, 'source': None}
    return sentences, doc_credits
