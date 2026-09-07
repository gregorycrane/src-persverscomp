"""doc_type: speech_collection (e.g. Boeckh orations). Relocated from Cell 4.

Populates work_book_metadata (book title/summary read straight off the
TEI's own <head> elements) -- see core/storage.py's table comment.
"""
from collections import OrderedDict
import os
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

def parse_speech_collection_tei(path, book_div_types=("edition",)):
    """Parses a COLLECTION of speeches/orations in one TEI file, where each
    speech is its own top-level <div> (Boeckh's Orationes: <div type="edition"
    n="1" xml:id="oratio1">), directly containing <p n="paragraph"> paragraphs,
    each directly containing <s n="sentence"> sentences -- i.e. the file's own
    CTS citation scheme (oration.paragraph.sentence) IS the book/chapter/section
    hierarchy, with no separate wrapping div needed per paragraph or sentence.

    Unlike parse_hierarchical_tei (which requires each book/chapter/section
    level to be its own <div> with a recognized subtype, and only reads whole
    <p> blocks as single undivided units), this parser drills all the way to
    SENTENCE granularity: book=oration, chapter=paragraph, section=sentence,
    matching how a CoNLL-U treebank keyed by the same 3-part sent_id scheme
    aligns row-for-row against the reading text.

    `book_div_types` matches against a div's `type` OR `subtype` attribute
    (checked in that order) to decide what counts as a "book"-level division --
    Boeckh's files use type="edition" for this, hence the default, but this is
    configurable per edition via work_registry.json's "book_div_type" key
    (see dispatch below) since a different speech/oration collection might
    label its top-level divs differently.

    Each oration div carries TWO literal <head> children -- the first is
    the title/date, the second is a one-line topic summary, e.g.:
        <head><num value="1">...</num> Oratio nataliciis...</head>
        <head>De Sparta et Athenis, rebus publicis...</head>
    Both Latin and English editions use this same shape. The first head ->
    book_titles (wired into catalog.json's book_titles / the client's
    getBookTitle); the second -> book_summaries (wired into catalog.json's
    book_summaries / the client's getBookSummary -- shown as a nav-list
    tooltip and as a subtitle under the rail title).

    Returns (data, book_titles, book_summaries):
      data[bk][ch][sec]   = sentence HTML (bk/ch/sec are all string keys)
      book_titles[bk]     = display title string, or absent if no <head> found
      book_summaries[bk]  = one-line topic summary, or absent if the oration
                             div has neither a second <head> nor a contents-div
    """
    if not os.path.exists(path):
        return None, {}, {}
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())
    if text_entry is None:
        return None, {}, {}

    data = OrderedDict()
    book_titles = {}
    book_summaries = {}

    def _div_kind(div):
        return (div.get("type") or "", div.get("subtype") or "")

    def _clean_text(el):
        return " ".join(extract_text_recursive(el, strip_paragraphs=True).split())

    for div in text_entry.iter():
        tag = div.tag.split("}")[-1]
        if tag != "div":
            continue
        dtype, dsubtype = _div_kind(div)
        if not ((dtype in book_div_types) or (dsubtype in book_div_types)):
            continue
        bk = (div.get("n") or "").strip()
        if not bk:
            continue

        # --- title (1st <head>) and summary (2nd <head>, or a sibling
        # contents-div's <p> when there's only one <head>) ---
        heads = div.findall("{http://www.tei-c.org/ns/1.0}head")
        if not heads:
            heads = div.findall("head")

        if heads:
            title_txt = _clean_text(heads[0])
            if title_txt:
                book_titles[bk] = title_txt
        if len(heads) >= 2:
            summary_txt = _clean_text(heads[1])
            if summary_txt:
                book_summaries[bk] = summary_txt

        if bk not in data:
            data[bk] = OrderedDict()

        # --- paragraphs directly under this book div (any depth, but not
        # inside a NESTED book-level div -- e.g. skip the contents/toc div) ---
        for p_el in div.findall("{http://www.tei-c.org/ns/1.0}p") or div.findall("p"):
            ch = (p_el.get("n") or "").strip()
            if not ch:
                continue
            if ch not in data[bk]:
                data[bk][ch] = OrderedDict()

            s_elements = p_el.findall("{http://www.tei-c.org/ns/1.0}s") or p_el.findall("s")
            if s_elements:
                for s_el in s_elements:
                    sec = (s_el.get("n") or "").strip()
                    if not sec:
                        continue
                    sent_html = extract_text_recursive(s_el, strip_paragraphs=False).strip()
                    if sent_html:
                        data[bk][ch][sec] = sent_html
            else:
                # Paragraph has no <s> children at all (e.g. a stray prose
                # paragraph outside the sentence-tagged body, such as the
                # editor's preface) -- fall back to the whole paragraph as
                # section "1" so nothing silently disappears.
                whole = " ".join(extract_text_recursive(p_el, strip_paragraphs=False).split())
                if whole:
                    data[bk][ch]["1"] = whole

    return data, book_titles, book_summaries
