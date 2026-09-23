"""doc_type: book_chapter_section. Relocated from Cell 4."""
from collections import OrderedDict
import os
import re
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

def parse_book_chapter_section_tei(path):
    """Parses a strict book > chapter > section hierarchy where each level is
    its OWN <div type="textpart" subtype="book|chapter|section" n="..."> and
    a section's text is spread across one or more <s> sentences bundled
    inside a single <p> -- e.g. the Heike Monogatari's book.chapter.section
    citation scheme (heike.tokyo1933.perseus-*), which also matches the
    3-part `Ref=` MISC field its CoNLL-U treebank carries per token (multiple
    sentences sharing one Ref -> one treebank_sentences row's sentence_json
    array), so this parser's granularity is deliberately the SECTION, not the
    sentence, to align 1:1 with that.

    Deliberately does NOT use xml:base the way parse_hierarchical_tei does:
    Heike's chapter divs carry xml:base pointing at their BOOK's URN, and its
    section divs carry xml:base pointing at their CHAPTER's URN (a dotted
    "book.chapter" string) -- parse_hierarchical_tei's base-injection
    heuristic treats every base-bearing div the same way and ends up
    clobbering the real chapter number with that dotted book.chapter string
    by the time a section's <p> is reached (last-value-wins in its key_map
    dict). Tracking (book, chapter) purely through recursive div-nesting
    order sidesteps that entirely and is more robust for any similarly
    CTS-URN-annotated 3-level hierarchy.

    Returns data[book][chapter][section] = concatenated sentence text
    (whitespace-normalized), matching every other parser's return shape.
    """
    if not os.path.exists(path):
        return None
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())
    if text_entry is None:
        return None

    data = OrderedDict()

    def walk(node, book, chapter):
        tag = node.tag.split('}')[-1]
        if tag == 'div':
            subtype = node.get('subtype') or node.get('type')
            n_val = (node.get('n') or '').strip()
            if subtype == 'book' and n_val:
                book, chapter = n_val, None
            elif subtype == 'chapter' and n_val:
                chapter = n_val
            elif subtype == 'section' and n_val and book and chapter:
                s_elements = (node.findall('.//{http://www.tei-c.org/ns/1.0}s')
                              or node.findall('.//s'))
                if s_elements:
                    sent_txt = ' '.join(
                        extract_text_recursive(s_el, strip_paragraphs=False).strip()
                        for s_el in s_elements
                    )
                else:
                    # No <s> children at all (stray prose) -- preserve every
                    # direct paragraph.  This includes nested block citations
                    # such as CHS Pausanias <cit><quote/><bibl/></cit> pairs.
                    ps = (node.findall('{http://www.tei-c.org/ns/1.0}p')
                              or node.findall('p'))
                    sent_txt = ' '.join(
                        extract_text_recursive(p_el, strip_paragraphs=False).strip()
                        for p_el in ps
                    )
                sent_txt = re.sub(r'\s+', ' ', sent_txt).strip()
                if sent_txt:
                    bk_dict = data.setdefault(book, OrderedDict())
                    ch_dict = bk_dict.setdefault(chapter, OrderedDict())
                    if n_val in ch_dict:
                        ch_dict[n_val] += " " + sent_txt
                    else:
                        ch_dict[n_val] = sent_txt
        for child in node:
            walk(child, book, chapter)

    walk(text_entry, None, None)
    return data
