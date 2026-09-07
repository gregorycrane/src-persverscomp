"""doc_type: reading_lines (incl. RTL scripts: Arabic, Persian). Relocated from Cell 4."""
from collections import OrderedDict
import os
from pipeline.core.xml_utils import NS, safe_parse, find_text_root, extract_text_recursive

_RTL_LANG_CODES = {
    'ar', 'ara',            # Arabic
    'fa', 'per', 'fas',     # Persian/Farsi
    'he', 'heb',            # Hebrew
    'ur', 'urd',            # Urdu
    'ae', 'ave',            # Avestan
    'syc', 'syr',           # Syriac
}

def _bidi_dir_for_lang(lang_code):
    """Map an xml:lang value to 'ltr'/'rtl', defaulting to 'ltr' for anything
    not recognized as an RTL script (covers 2- and 3-letter codes, ignoring
    region subtags like 'fa-IR')."""
    if not lang_code:
        return None
    base = lang_code.strip().split('-')[0].lower()
    return 'rtl' if base in _RTL_LANG_CODES else 'ltr'

def _reading_prose_block(div_el, css_class):
    """Render an editorial prose child of a <div subtype="reading"> (intro,
    notes, ...) into one HTML block.

    Walks DIRECT children in document order so <quote> blocks interleaved
    between <p>s (a sibling of <p>, not nested inside one) aren't skipped —
    an earlier version only collected <p> via findall and silently dropped
    any <quote>. <head> becomes a heading; <quote> is handed to
    extract_text_recursive(strip_paragraphs=False) so its own nested <p> gets
    the existing .quote-block treatment (already styled in styles.css); any
    other block-level tag falls back to the same generic extraction rather
    than being dropped.

    Tags the wrapper with dir="ltr"/"rtl" + lang="..." from @xml:lang, since
    these are typically editorial English prose sitting inside a Persian
    (RTL) edition file and would otherwise silently inherit direction:rtl
    from the .persian-text column wrapper they render inside.
    """
    parts = []
    for child in list(div_el):
        ctag = child.tag.split('}')[-1]
        if ctag == 'head':
            if child.text and child.text.strip():
                parts.append(f'<h4 class="{css_class}-head">{child.text.strip()}</h4>')
        elif ctag == 'p':
            t = extract_text_recursive(child, strip_paragraphs=True).strip()
            if t:
                parts.append(f'<div class="prose-para">{t}</div>')
        elif ctag == 'quote':
            q = extract_text_recursive(child, strip_paragraphs=False).strip()
            if q:
                parts.append(q)
        else:
            t = extract_text_recursive(child, strip_paragraphs=False).strip()
            if t:
                parts.append(f'<div class="prose-para">{t}</div>')
    if not parts:
        return None
    lang = (div_el.get('{http://www.w3.org/XML/1998/namespace}lang') or '').strip()
    bidi = _bidi_dir_for_lang(lang)
    attrs = f' dir="{bidi}"' if bidi else ''
    attrs += f' lang="{lang}"' if lang else ''
    return f'<div class="{css_class}"{attrs}>{"".join(parts)}</div>'

def parse_reading_lines_tei(path):
    """Pizzi Shahnameh 'reading' selections.

    Each <div subtype="reading" n="N"> may hold an optional <div subtype="intro">
    (prose head + paragraphs/quotes introducing the passage) and/or a trailing
    <div subtype="notes"> (grammatical/apparatus notes), alongside the verse.
    The verse itself may live inside its own <div type="textpart" subtype="text">
    (or n="text") wrapper sibling of intro/notes, so <l> lines are no longer
    necessarily DIRECT children of the reading div — they're found recursively
    below so nesting depth and the wrapper's exact attributes don't matter.

    intro is emitted as pseudo-line "0intro" and notes as pseudo-line "notes".
    naturalSectionKeys() in app.js sorts numeric-prefixed keys first (by
    number) and any non-numeric-prefixed key after all of them — so "0intro"
    (numeric prefix 0) sorts ahead of "1", "2", ..., while "notes" (no digit
    prefix at all) sorts after every verse line regardless of the reading's
    line count. Neither block's HTML has a .line-num-cell, so the front end's
    poetry-grid detection falls back to plain prose rendering for both.
    """
    if not os.path.exists(path): return None
    tree = safe_parse(path)
    text_entry = find_text_root(tree.getroot())
    if text_entry is None: return None
    data = OrderedDict({"1": OrderedDict()})   # single pseudo-book -> flat structure

    for div in text_entry.iter():
        tag = div.tag.split('}')[-1]
        if tag == 'div' and (div.get('subtype') == 'reading') and div.get('n'):
            reading_n = div.get('n').strip()
            lines = OrderedDict()

            # Intro / notes: only DIRECT children of this reading (so we don't
            # accidentally pull in a sibling reading's apparatus).
            for child in list(div):
                if child.tag.split('}')[-1] != 'div':
                    continue
                st = (child.get('subtype') or child.get('type') or '').lower()
                if st == 'intro':
                    html = _reading_prose_block(child, 'reading-intro')
                    if html:
                        lines["0intro"] = html
                elif st == 'notes':
                    html = _reading_prose_block(child, 'reading-notes')
                    if html:
                        lines["notes"] = html

            # Verse lines: search recursively — no longer assumed to be direct
            # children, since the intro/notes divs forced them into a nested
            # wrapper.
            for l in div.iter():
                if l.tag.split('}')[-1] != 'l':
                    continue
                ln = l.get('n')
                if ln:

                    lines[ln] = extract_text_recursive(l, strip_paragraphs=True)

            data["1"][reading_n] = lines
    return data
