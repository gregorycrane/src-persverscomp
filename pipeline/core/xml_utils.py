"""Shared XML/TEI helpers used by every parser. Relocated from Cell 4."""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from pipeline.config import NS, _LXML
from pipeline.core.storage import TEXTGROUP_NAMESPACE
try:
    import lxml.etree as LET
except ImportError:
    pass

def _ns(work_key):
    """Derive the CTS namespace from the textgroup prefix, e.g. tlg0012 → greekLit.
    Extend TEXTGROUP_NAMESPACE for other collections (stoa, etc.)."""
    _tg = work_key.split(".")[0]
    _m = re.match(r"[A-Za-z]+", _tg)
    _val = TEXTGROUP_NAMESPACE.get(_m.group(0).lower() if _m else "")
    if _val is None:
        print(f"  \u26a0 unknown textgroup prefix in '{work_key}'; defaulting to greekLit")
        _val = "greekLit"
    return _val

def safe_parse(path):
    if _LXML:
        parser = LET.XMLParser(recover=True)
        tree = LET.parse(path, parser=parser)
        import io
        buf = io.BytesIO()
        tree.write(buf)
        buf.seek(0)
        return ET.parse(buf)
    return ET.parse(path)

def find_text_root(root):
    # Only treat a translation/commentary div as THE text root when it's a
    # direct child of <body> -- i.e. the whole document genuinely IS a
    # translation or commentary edition. Previously this scanned the ENTIRE
    # tree in document order and returned the first type="translation"/
    # "commentary" div found anywhere -- which, for critical editions like
    # Wilamowitz that embed small <div type="commentary"> wrappers around
    # individual scholia/testimonia quotes deep inside the apparatus, meant
    # find_text_root latched onto a three-line scholion instead of the whole
    # play (zero <l>, zero milestones under it), so every card silently had
    # no content to bin and the client showed "Not divided separately in
    # this edition" almost everywhere. Restricting the scan to body's direct
    # children fixes that while still handling genuine whole-document
    # translation/commentary editions correctly.
    body = root.find('.//{http://www.tei-c.org/ns/1.0}body')
    if body is None:
        body = root.find('.//body')
    if body is not None:
        for div in body:
            tag = div.tag.split('}')[-1]
            if tag != 'div':
                continue
            if div.get('type') in ('translation', 'commentary'):
                return div
        return body
    return root.find('.//{http://www.tei-c.org/ns/1.0}body') or root.find('.//body') or root.find('.//*body')


def leading_card_milestone_after_speaker(elem):
    """Return a card milestone that opens a TEI speech.

    Some dramatic texts serialize a new card boundary as::

        <sp><speaker>...</speaker><milestone unit="card" .../> ...</sp>

    A streaming parser otherwise emits the speaker under the previous card
    before it encounters the milestone.  Only recognize the tightly scoped
    leading pattern: the milestone must be a direct child of ``sp`` and must
    immediately follow its ``speaker`` (apart from non-textual page/line-break
    markers).  A milestone after authored speech content is a real mid-speech
    boundary and must not be pulled forward.
    """
    if elem.tag.split("}")[-1] != "sp":
        return None

    saw_speaker = False
    for child in elem:
        tag = child.tag.split("}")[-1]
        if not saw_speaker:
            if tag == "speaker":
                saw_speaker = True
                continue
            if tag in ("pb", "lb"):
                continue
            return None

        if tag == "milestone" and child.get("unit") == "card":
            return child
        if tag in ("pb", "lb"):
            continue
        return None
    return None

def _plain(html):
    """Collapse rendered-HTML markup + whitespace to bare text, for use
    inside a title="" attribute (which can't hold tags)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _attr(s):
    """Escape a string for an HTML double-quoted attribute value."""
    return (s.replace("&", "&amp;").replace('"', "&quot;")
             .replace("<", "&lt;").replace(">", "&gt;"))


def render_page_break(pb_elem):
    """Render a TEI page boundary, linking a safe published facsimile.

    Page numbers remain visible even while an edition has only ``@n``.  When
    a later cleanup supplies an absolute HTTP(S) ``@facs`` URL, the same
    marker becomes a link without requiring another parser change.
    """
    number = (pb_elem.get("n") or "").strip()
    facs = (pb_elem.get("facs") or "").strip()
    label = f"[p. {number}]" if number else "[page]"
    title = f"View source page {number}" if number else "View source page"
    attrs = f'class="tei-page-break" data-page="{_attr(number)}"'
    parsed = urlparse(facs) if facs else None
    if parsed and parsed.scheme in {"http", "https"} and parsed.netloc:
        return (
            f'<a {attrs} href="{_attr(facs)}" target="_blank" '
            f'rel="noopener noreferrer" title="{_attr(title)}">{label}</a>'
        )
    return f'<span {attrs} title="Source page {_attr(number)}">{label}</span>'


def render_app_crit(app_elem, show_lemma=True):
    """TEI critical apparatus <app> rendered *inline*: the <lem> reading
    stays in the running text (so the line still scans, and alignment /
    tokenization / lexicon lookups see exactly the words the editor
    printed); the <rdg> variants and any <note> ride along in data-app /
    data-lem / title attributes -- NOT visible text -- so they never
    pollute the token stream, and app.js turns them into a hover/click
    popover. An empty <lem/> (apparatus about an omission/addition) or a
    note-only <app> renders as a bare dagger marker.

    Returns an HTML string. Mirrors the standalone end-of-poem apparatus
    note treatment in parse_poetry_cards_tei.
    """
    lem_html = ""
    lem_src = ""
    pieces = []
    for ch in app_elem:
        t = ch.tag.split("}")[-1]
        inner = extract_text_recursive(ch, strip_paragraphs=True, _nested=True).strip()
        if t == "lem":
            lem_html = inner
            # @source / @resp attribute the *adopted* reading to an editor
            # (e.g. source="#Elmsl_corr") -- worth carrying into the tip.
            lem_src = (ch.get("source") or ch.get("resp") or "").lstrip("#").strip()
        elif t == "rdg":
            txt = _plain(inner)
            wits = [w.lstrip("#") for w in (ch.get("wit") or "").split()]
            wits = [w for w in wits if w and w not in txt]
            if not txt and (ch.get("type") or "") == "omission":
                txt = "om."
            if txt and wits:
                pieces.append(f"{txt} ({' '.join(wits)})")
            elif txt:
                pieces.append(txt)
            elif wits:
                pieces.append(" ".join(wits))
        elif t == "note":
            n = _plain(inner)
            if n:
                pieces.append(n)

    lem_text = _plain(lem_html)
    if lem_text and lem_src:
        lem_text = f"{lem_text} ({lem_src})"
    note = " | ".join(p for p in pieces if p)
    if not note:
        return lem_html  # nothing to report -> just the reading (or "")

    # Structured data-* attributes drive the JS popover (app.js); title=""
    # is kept as a no-JS / assistive-tech fallback. data-app keeps the
    # readings pipe-separated so the popover can list them one per line.
    data = (f'data-lem="{_attr(lem_text)}" data-app="{_attr(note)}"'
            if lem_text else f'data-app="{_attr(note)}"')
    tip = _attr(f"{lem_text}] {note}" if lem_text else note)

    if lem_html and show_lemma:
        return f'<span class="app-crit" {data} title="{tip}">{lem_html}</span>'
    extra = " app-crit-standoff" if not show_lemma else ""
    return f'<span class="app-crit app-crit-empty{extra}" {data} title="{tip}"></span>'


def extract_text_recursive(elem, strip_paragraphs=False, lineno_sigil=None,
                           _nested=False, citation_prefix=None,
                           footnote_lookup=None):
    element_tag = elem.tag.split("}")[-1]
    if element_tag == "app":
        return render_app_crit(elem)
    if element_tag == "choice":
        children = {child.tag.split("}")[-1]: child for child in elem}
        preferred = next((children[name] for name in ("expan", "corr", "reg")
                          if name in children), None)
        original = next((children[name] for name in ("abbr", "sic", "orig")
                         if name in children), None)
        if preferred is None:
            preferred = next(iter(elem), None)
        if preferred is None:
            return elem.text or ""
        rendered = extract_text_recursive(
            preferred, strip_paragraphs=strip_paragraphs, _nested=True,
            footnote_lookup=footnote_lookup
        )
        original_text = "" if original is None else "".join(original.itertext()).strip()
        if not original_text:
            return rendered
        return (f'<span class="tei-expan" data-original="{_attr(original_text)}" '
                f'title="Original: {_attr(original_text)}">{rendered}</span>')
    # _nested: True whenever this call is reached by recursing INTO a
    # parent element's children (see the `for child in elem` loop and the
    # note-handling branch below), as opposed to being the original,
    # direct call a caller makes on an <l> element it already knows is
    # one of the work's own numbered verse lines. Every genuine top-level
    # verse-line call site in this notebook calls extract_text_recursive(l, ...)
    # directly on the <l> itself, so it naturally gets _nested's default of
    # False; an <l> only reached via recursion is, by construction, a
    # quotation embedded inside something else (a note, a lemma, a <quote>)
    # -- see the tag == 'l' handling below for why that distinction matters.
    # (NOTE: this replaces an earlier version of this fix that keyed off
    # strip_paragraphs=True instead -- wrong, because the genuine top-level
    # verse-line call sites ALSO pass strip_paragraphs=True, so that version
    # suppressed the line-num-cell/line-text-cell grid for real verse lines
    # too, breaking the Focus column's own line numbers and the alignment
    # grid that depends on them.)
    parts = []
    link_ref = False
    tag = element_tag
    inline_translation = (
        elem.get('type') == 'translation'
        and tag in ('mentioned', 'foreign', 'quote')
    )

    def open_inline_translation(source_tag):
        lang = (elem.get('{http://www.w3.org/XML/1998/namespace}lang') or '').strip()
        attrs = [
            f'class="tei-inline-translation translation-{source_tag}"',
            'title="Translation of the preceding text"',
        ]
        if lang:
            attrs.append(f'lang="{_attr(lang)}"')
        corresp = (elem.get('corresp') or '').strip()
        if corresp:
            attrs.append(f'data-corresp="{_attr(corresp)}"')
        parts.append(f'<span {" ".join(attrs)}>[')
    
    if tag == 'l':
        # An <l> reached via recursion (_nested=True) is a quotation of
        # verse embedded INSIDE prose -- e.g. Mooney's commentary notes
        # quoting Homer or Catullus for comparison -- not the work's own
        # numbered text. The line-num-cell/line-text-cell pair below is the
        # marker the FRONT END uses to detect "this column is a real verse
        # edition, wrap it in the 2-column poetry grid". Emitting that same
        # marker for a quoted line buried inside an ordinary comm-note span
        # made a commentary card that merely quoted one line of verse
        # anywhere in its notes look exactly like a genuine verse column to
        # that check, so the whole card got wrapped in the 45px/1fr poetry
        # grid and its ordinary comm-lineno/comm-entry blocks were
        # auto-placed alternately into the narrow and wide tracks -- the
        # 'squeezed into a tiny column' look, regardless of the actual
        # column width. A quoted line just needs its own line break (see
        # the matching close below), not a grid cell.
        if not _nested:
            line_num = (elem.get('n') or '').strip()
            if line_num:
                cite_attr = (f' data-cite="{_attr(f"{citation_prefix}.{line_num}")}"'
                             if citation_prefix else '')
                if lineno_sigil:
                    parts.append(f'<div class="line-num-cell" data-n="{line_num}"{cite_attr}>'
                                 f'<span class="src-lineno">[{line_num} {lineno_sigil}]</span></div>')
                else:
                    # data-n is the stable hook used by range navigation and
                    # poetry token alignment.  It belongs on every numbered
                    # line, not only editions with an alternate line sigil.
                    parts.append(f'<div class="line-num-cell" data-n="{_attr(line_num)}"{cite_attr}>{line_num}</div>')
            else:
                parts.append('<div class="line-num-cell\">&nbsp;</div>')
            parts.append('<div class="line-text-cell">')
    
    elif tag == 'sic':
        parts.append('<span class="tei-sic">[')
    elif tag == 'corr':
        parts.append(' <span class="tei-corr">')
    elif tag == 'speaker': 
        parts.append('<strong class="speaker-attr">')
    elif tag == 'stage':
        parts.append('<div class=\"stage-direction\">')
    elif tag == 'hi':
        rend = elem.get('rend', 'italic')
        parts.append(f'<span class="render-{rend}">')
    elif tag == 'mentioned':
        if inline_translation:
            open_inline_translation('mentioned')
        else:
            parts.append('<span class="lemma render-bold">')
    elif tag == 'emph':
        # TEI <emph> is authored rhetorical emphasis, distinct from a
        # lexicographic/translation <gloss>.  It was previously unwrapped,
        # so its text appeared with no visible emphasis at all.
        parts.append('<em class="tei-emph">')
    elif tag == 'gloss':
        parts.append('<span class="tei-gloss">')
    elif tag == 'term':
        lang = (elem.get('{http://www.w3.org/XML/1998/namespace}lang') or '').strip()
        key = (elem.get('key') or '').strip()
        ana = (elem.get('ana') or '').strip()
        attrs = ['class="tei-term"']
        if lang: attrs.extend([f'lang="{_attr(lang)}"', f'data-lang="{_attr(lang)}"'])
        if key: attrs.append(f'data-term-key="{_attr(key)}"')
        if ana: attrs.append(f'data-ana="{_attr(ana)}"')
        parts.append(f'<span {" ".join(attrs)}>')
    elif tag == 's':
        parts.append('<span class="lemma">')
    elif tag == 'del':
        parts.append('<span class="tei-del">[')
    elif tag == 'add':
        parts.append('<span class="tei-add">\u27e8')   # ⟨
    elif tag == 'quote':
        if inline_translation:
            open_inline_translation('quote')
        else:
            # TEI <quote> is phrase-level as well as block-level. Treat explicit
            # blockquotes and verse quotations as blocks; prose quotations inside
            # <cit> remain inline and receive normal quotation marks from HTML <q>.
            is_block_quote = (
                elem.get('rend') == 'blockquote'
                or elem.get('type') == 'blockquote'
                or any(ch.tag.split('}')[-1] == 'l' for ch in elem)
            )
            if is_block_quote:
                q_type = elem.get('type', 'blockquote')
                parts.append(f'<div class="quote-block type-{q_type}">')
            else:
                parts.append('<q class="tei-quote">')
    elif tag == 'cit':
        # CHS prose translations use a block citation to keep the quoted
        # passage and its source attribution together.  Phrase-level TEI
        # citations remain transparent so existing commentary keeps flowing.
        if elem.get('type') == 'block':
            parts.append('<div class="tei-cit tei-cit-block">')
    elif tag == 'bibl':
        cref = (elem.get('corresp') or elem.get('cRef') or '').strip()
        n = (elem.get('n') or '').strip()
        rend = (elem.get('rend') or '').strip()
        attrs = ['class="tei-bibl"']
        if rend == 'right': attrs[0] = 'class="tei-bibl tei-bibl-right"'
        if cref: attrs.append(f'data-cref="{_attr(cref)}"')
        if n: attrs.append(f'data-label="{_attr(n)}"')
        parts.append(f'<cite {" ".join(attrs)}>')
    elif tag == 'graphic':
        # Preserve source facsimiles (e.g. metrical schemes) as images.  Restrict
        # URLs to web/local asset paths; never emit executable URL schemes.
        from urllib.parse import urlsplit
        src = (elem.get('url') or '').strip()
        parsed = urlsplit(src)
        safe = bool(src) and parsed.scheme in ('', 'http', 'https') and not src.startswith('//')
        if safe:
            label = elem.get('n') or 'Source facsimile'
            parts.append(f'<a class="tei-facsimile" href="{_attr(src)}" target="_blank" rel="noopener noreferrer">'
                         f'<img src="{_attr(src)}" alt="{_attr(label)}" loading="lazy" '
                         'style="max-width:100%;max-height:26rem;height:auto;object-fit:contain;display:block"/></a>')
    elif tag == 'ref':
        target = (elem.get('target') or '').strip()
        ref_type = (elem.get('type') or '').strip()
        note = (footnote_lookup or {}).get(target.lstrip('#')) if ref_type == 'note' else None
        note_text = re.sub(r'\s+', ' ', ''.join(note.itertext())).strip() if note is not None else ''
        attrs = ['class="tei-ref tei-note-ref"' if note_text else 'class="tei-ref"']
        if target: attrs.append(f'data-cref="{_attr(target)}"')
        if ref_type: attrs.append(f'data-ref-type="{_attr(ref_type)}"')
        if note_text:
            number = ''.join(elem.itertext()).strip() or (note.get('n') or '').strip()
            attrs.extend([
                f'data-note="{_attr(note_text)}"',
                f'data-note-label="{_attr(number)}"',
                f'aria-label="Footnote {_attr(number)}: {_attr(note_text)}"',
                'role="button"', 'tabindex="0"',
                f'title="Footnote {_attr(number)}: {_attr(note_text)}"',
            ])
        from urllib.parse import urlsplit
        parsed = urlsplit(target)
        link_ref = (target.startswith('/site/') or
                    (parsed.scheme in ('http', 'https') and bool(parsed.netloc)))
        if link_ref:
            attrs.extend([f'href="{_attr(target)}"', 'target="_blank"',
                          'rel="noopener noreferrer"'])
        parts.append(f'<{"a" if link_ref else "span"} {" ".join(attrs)}>')
    elif tag == 'p' and not strip_paragraphs:
        parts.append('<div class="prose-para">')
    elif tag == 'milestone' and elem.get('unit') == 'line':
        ln_num = (elem.get('n') or '').strip()
        if ln_num:
            parts.append(f'<span class="inline-line-milestone" title="Line Milestone {ln_num}">{ln_num}</span>')
    elif tag == 'milestone' and elem.get('unit') == 'page':
        pg = (elem.get('n') or '').strip()
        resp = (elem.get('resp') or '').strip()
        if pg:
            tip = (resp + ' ' + pg).strip()
            parts.append(f'<span class="milestone bekker-page" data-resp="{resp}" title="{tip}">{pg}</span>')
    elif tag == 'q':
        parts.append('\u201c')
    elif tag == 'foreign':
        if inline_translation:
            open_inline_translation('foreign')
        else:
            lang = (elem.get('{http://www.w3.org/XML/1998/namespace}lang') or '').strip()
            cls  = f'foreign foreign-{lang}' if lang else 'foreign'
            parts.append(f'<span class="{cls}" lang="{lang}">')
    elif tag == 'seg' and elem.get('type') == 'metrical-part':
        part_n = elem.get('n', '')
        parts.append(f'<span class="metrical-part metrical-part-{part_n}">')
    elif tag == 'seg':
        rend = (elem.get('rend') or '').strip()
        seg_type = (elem.get('type') or '').strip()
        xml_id = (elem.get('{http://www.w3.org/XML/1998/namespace}id') or '').strip()
        ana = (elem.get('ana') or '').strip()
        classes = ['seg']
        if rend: classes.append(f'seg-{rend}')
        if seg_type: classes.append(f'seg-type-{seg_type}')
        if '#alignment-unresolved' in ana: classes.append('seg-alignment-unresolved')
        attrs = [f'class="{_attr(" ".join(classes))}"']
        if xml_id: attrs.append(f'data-xml-id="{_attr(xml_id)}"')
        if ana: attrs.append(f'data-ana="{_attr(ana)}"')
        if elem.get('n'): attrs.append(f'data-cue="{_attr(elem.get("n"))}"')
        parts.append(f'<span {" ".join(attrs)}>')
    if elem.text: 
        parts.append(elem.text)
        
    for child in elem:
        child_tag = child.tag.split('}')[-1]
        if child_tag == 'note':
            note_text = extract_text_recursive(
                child, strip_paragraphs, _nested=True,
                footnote_lookup=footnote_lookup).strip()
            # A note linked to a mentioned lemma is the commentary itself,
            # not a footnote inserted into that commentary.
            note_id = child.get('{http://www.w3.org/XML/1998/namespace}id')
            linked_commentary = child.get('type') == 'commentary' and note_id and any(
                sibling.tag.split('}')[-1] == 'mentioned'
                and ('#' + note_id) in (sibling.get('ana') or '').split()
                for sibling in elem if isinstance(sibling.tag, str))
            if note_text:
                if linked_commentary:
                    parts.append(f'<span class="commentary-note">{note_text}</span>')
                else:
                    parts.append(f'<span class="note">[{note_text}]</span>')
        elif child_tag == 'lb':
            # <lb/> marks a physical line break in the PRINTED PAGE layout
            # (these commentary/apparatus files were transcribed line-for-line
            # off a narrow printed column), not a semantic break. Rendering it
            # as a hard <br/> forced every prose/commentary note to wrap at the
            # *original* page's line width instead of reflowing to fill the
            # reading pane -- that's what produced the 'squeezed into a tiny
            # column' look (e.g. Mooney's Apollonius commentary), regardless of
            # how wide the CSS column actually was. Treat it as a soft join
            # (a space) so text reflows normally; verse <l> lines still get
            # their own line-num-cell/line-text-cell grid above and are
            # unaffected by this.
            if parts and not parts[-1].endswith((' ', chr(10))):
                parts.append(' ')
        else: 
            parts.append(extract_text_recursive(
                child, strip_paragraphs, _nested=True,
                footnote_lookup=footnote_lookup))
            # A TEI <s> boundary is a word boundary even when the source XML
            # serializes adjacent sentence elements as </s><s> with no tail
            # whitespace. Without this fallback, rendered prose joins the
            # final punctuation of one sentence directly to the first word
            # of the next. Authored tail whitespace still wins below.
            if child_tag == 's' and child.tail is None:
                parts.append(' ')
        # Tail text after a block-level child must go in its own div,
        # not raw text, to avoid invalid HTML and browser reflow bugs.
        if child.tail and child.tail.strip():
            child_is_block = child_tag in ('quote', 'stage')
            if child_tag == 'quote':
                child_is_block = (
                    child.get('rend') == 'blockquote'
                    or child.get('type') == 'blockquote'
                    or any(grand.tag.split('}')[-1] == 'l' for grand in child)
                )
            elif child_tag == 'cit':
                child_is_block = any(
                    descendant.tag.split('}')[-1] == 'quote'
                    and (
                        descendant.get('rend') == 'blockquote'
                        or descendant.get('type') == 'blockquote'
                        or any(grand.tag.split('}')[-1] == 'l' for grand in descendant)
                    )
                    for descendant in child.iter()
                )
            if child_is_block:
                parts.append(f'<div class="prose-continuation">{child.tail}</div>')
            else:
                parts.append(child.tail)
        elif child.tail:
            parts.append(child.tail)
            
    if tag == 'l':
        # Matches the open above: a genuine top-level verse line closes its
        # line-text-cell div; a quoted line inside prose just gets a real
        # line break so multi-line quotations still read as separate lines,
        # without the grid markup that trips the front end's poetry-grid
        # detection for the whole surrounding column.
        parts.append('</div>' if not _nested else '<br/>')
    elif tag == 'sic': parts.append(']</span>')
    elif tag == 'corr': parts.append('</span>')
    elif tag == 'speaker': parts.append(': </strong>')
    elif tag == 'stage': parts.append('</div>')
    elif tag == 'hi': parts.append('</span>')
    elif tag == 'mentioned': parts.append(']</span>' if inline_translation else '</span>')
    elif tag == 'emph': parts.append('</em>')
    elif tag == 'gloss': parts.append('</span>')
    elif tag == 'term': parts.append('</span>')
    elif tag == 's': parts.append('</span>')
    elif tag == 'del': parts.append(']</span>')
    elif tag == 'add': parts.append('\u27e9</span>')
    elif tag == 'quote':
        if inline_translation:
            parts.append(']</span>')
        else:
            is_block_quote = (
                elem.get('rend') == 'blockquote'
                or elem.get('type') == 'blockquote'
                or any(ch.tag.split('}')[-1] == 'l' for ch in elem)
            )
            parts.append('</div>' if is_block_quote else '</q>')
    elif tag == 'cit':
        if elem.get('type') == 'block':
            parts.append('</div>')
    elif tag == 'bibl':
        parts.append('</cite>')
    elif tag == 'ref':
        parts.append('</a>' if link_ref else '</span>')
    elif tag == 'p' and not strip_paragraphs: parts.append('</div>')
    elif tag == 'q':
        parts.append('\u201d')
    elif tag == 'foreign':
        parts.append(']</span>' if inline_translation else '</span>')
    elif tag == 'seg' and elem.get('type') == 'metrical-part':
        parts.append('</span>')
    elif tag == 'seg':
        parts.append('</span>')        
    return ''.join(parts)
