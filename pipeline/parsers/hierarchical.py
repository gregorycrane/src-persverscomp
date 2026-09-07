"""doc_type: hierarchical. Relocated from Cell 4."""
from collections import OrderedDict
import os
import re
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

def parse_hierarchical_tei(path):
    if not os.path.exists(path): return None
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())
    if text_entry is None: return None
    data = OrderedDict()

    def walk_divisions(node, current_path):
        tag = node.tag.split('}')[-1]
        subtype = node.get('subtype') or node.get('type')
        n_val = node.get('n')
        base_val = node.get('xml:base') or node.get('{http://www.w3.org/XML/1998/namespace}base')
        
        key_map_so_far = {t: v for t, v in current_path}
        if tag == 'div' and subtype in ('book', 'chapter', 'section', 'subchapter', 'part', 'textpart') and n_val:
            if subtype in ('part', 'textpart') and n_val.isdigit():
                resolved_subtype = 'chapter'
            elif subtype == 'subchapter':
                resolved_subtype = 'section'
            else:
                resolved_subtype = subtype
            
            # Some editions carry non-narrative editorial matter as a
            # 'chapter'-subtype div rather than a real citation number:
            # - a non-numeric @n, e.g. C. F. Smith's 1st1K-eng1 introduction
            #   to Book VIII: <div subtype="chapter" n="comment"><head>
            #   INTRODUCTION</head>...
            # - @n="0", a convention (e.g. 1st1K-ger2) for a per-book
            #   chapter-argument/synopsis preceding chapter 1, e.g. <div
            #   subtype="chapter" n="0"><head>Inhalt des ersten Buches.
            #   </head>... -- correctly nested under its own book, unlike
            #   the orphaned 'comment' case, but still not a real chapter 1.
            # Showing the literal @n as a TOC label is meaningless either
            # way -- prefer the div's own <head> text in both cases.
            n_str = str(n_val).strip()
            label_val = n_str
            if resolved_subtype == 'chapter' and (n_str == '0' or not re.fullmatch(r'\d+(\.\d+)*', n_str)):
                head_el = node.find('{http://www.tei-c.org/ns/1.0}head')
                if head_el is None:
                    head_el = node.find('head')
                if head_el is not None:
                    head_text = ' '.join(head_el.itertext()).strip()
                    if head_text:
                        label_val = head_text[:60]
            
            # BACKWARD COMPATIBILITY (older cRefPattern-style refsDecl,
            # pre-citeStructure EpiDoc): xml:base on a nested book/chapter/
            # section div encodes the PARENT's own citation depth -- a book
            # div's base is the bare edition URN, a chapter div's base ends
            # in just the book number, a section div's base ends in
            # "book.chapter" -- NOT this div's own full ref. Blindly taking
            # base_val.split(':')[-1] and writing it into 'chapter' on every
            # div lets a deeper section-level base clobber a chapter value a
            # shallower chapter-level div already got right (e.g. Thucydides'
            # perseus-grc2: the chapter div sets chapter='1' correctly from
            # its own base, then the section div underneath overwrites it
            # with '1.1' from ITS OWN base -- book.chapter, not section).
            # Two guards: only trust a base-derived value that's actually
            # citation-shaped (digits/dots -- rules out an edition-level
            # base like ".../perseus-grc2" with no ref at all, or a stray
            # non-citation base some translations carry), AND only use it
            # to FILL a 'chapter' slot that's still empty, never to override
            # one a shallower div already set from its own n_val.
            if base_val and ':' in base_val and 'chapter' not in key_map_so_far:
                ch_from_base = base_val.split(':')[-1].strip()
                if re.fullmatch(r'\d+(\.\d+)*', ch_from_base):
                    extra = [('chapter', ch_from_base)]
                    # An orphaned chapter-level div (no ancestor 'book' yet)
                    # whose own @n isn't a real citation -- like the
                    # Introduction-to-Book-VIII case above -- would otherwise
                    # silently default to book '1' downstream. When its base
                    # gives a bare book-shaped number (no dot), use that as
                    # the book instead of losing the association entirely.
                    if ('book' not in key_map_so_far
                            and not re.fullmatch(r'\d+(\.\d+)*', n_str)
                            and '.' not in ch_from_base):
                        extra = [('book', ch_from_base), ('chapter', ch_from_base)]
                    new_path = current_path + extra + [(resolved_subtype, label_val)]
                else:
                    new_path = current_path + [(resolved_subtype, label_val)]
            else:
                new_path = current_path + [(resolved_subtype, label_val)]
        else:
            if base_val and ':' in base_val and 'chapter' not in key_map_so_far:
                ch_from_base = base_val.split(':')[-1].strip()
                if re.fullmatch(r'\d+(\.\d+)*', ch_from_base):
                    new_path = current_path + [('chapter', ch_from_base)]
                else:
                    new_path = current_path
            else:
                new_path = current_path

        paragraphs = node.findall('{http://www.tei-c.org/ns/1.0}p') or node.findall('p')
        if paragraphs and new_path:
            key_map = {t: v for t, v in new_path}
            bk = key_map.get('book', '1')
            ch = key_map.get('chapter', key_map.get('part', '1'))
            sec = key_map.get('section', n_val or '1')

            if bk not in data: data[bk] = OrderedDict()
            if ch not in data[bk]: data[bk][ch] = OrderedDict()
            
            combined_txt = ' '.join(extract_text_recursive(p, strip_paragraphs=False).strip() for p in paragraphs)
            if combined_txt:
                if sec in data[bk][ch]:
                    data[bk][ch][sec] += " " + combined_txt
                else:
                    data[bk][ch][sec] = combined_txt

        for child in node: 
            walk_divisions(child, new_path)

    walk_divisions(text_entry, [])
    return data
