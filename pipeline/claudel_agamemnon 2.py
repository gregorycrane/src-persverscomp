"""Build a reversible PMV preview layer from Claudel's 1896 Agamemnon OCR."""
import html
import json
import shutil
import sqlite3
from pathlib import Path

from pipeline.claudel_translation import align_pages, extract_pages
from pipeline.core.storage import init_storage_engine

TEXTGROUP = 'tlg0085'
WORK = 'tlg005'
VERSION = 'claudel1896-fra1'
URN = 'urn:cts:greekLit:tlg0085.tlg005.' + VERSION
CANONICAL_ID = 'tlg0085_tlg005_claudel_1896_translation'
LABEL = 'French (Paul Claudel, 1896; OCR, approximate alignment)'
RANGES = ((1, 60, 0, 1673),)


def _render(lines, first=False):
    chunks, current_page = [], None
    for page, line in lines:
        if page != current_page:
            if current_page is not None:
                chunks.append('</div>')
            chunks.append('<div class="claudel-page"><div class="claudel-page-number">Claudel p. %d</div>' % page)
            current_page = page
        chunks.append('<div class="claudel-line">%s</div>' % html.escape(line))
    if current_page is not None:
        chunks.append('</div>')
    note = ('<div class="claudel-alignment-note"><strong>OCR preview.</strong> '
            'The source has no Aeschylean line numbers; its printed pages are aligned approximately '
            'to the Greek passage cards. Source: <cite>L\'Agamemnon d\'Eschyle</cite>, '
            'trans. Paul Claudel (Fou Tcheou: Foochow Printing Press, 1896), pp. 1–60; '
            '<a href="https://hdl.handle.net/2027/chi.084972221" target="_blank" '
            'rel="noopener">HathiTrust scan</a>.</div>')
    return (note if first else '') + ''.join(chunks)


def build_translation(source, output, existing):
    """Create an aggregate layer and a shadow copy of the Agamemnon shard."""
    source, output, existing = Path(source), Path(output), Path(existing)
    original = existing / 'site/data' / TEXTGROUP / WORK / (TEXTGROUP + '.' + WORK + '.part1.db')
    shadow = output / 'site/data' / TEXTGROUP / WORK / original.name
    shadow.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, shadow)

    with sqlite3.connect(original.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        grid = conn.execute(
            'SELECT passage_urn,chapter,sort_order FROM alignment_grid ORDER BY sort_order').fetchall()
    pages = extract_pages(source, 1, 60, ('AGAMEMNON', "L'AGAMEMNON"))
    aligned = align_pages(pages, grid, RANGES)
    unit = (CANONICAL_ID, URN, LABEL, 'french-text', TEXTGROUP, WORK, VERSION, 'translation')
    segments = [(urn, VERSION, _render(aligned[urn], first=index == 0))
                for index, (urn, _, _) in enumerate(grid)]
    order = [(TEXTGROUP, WORK, VERSION, None, chapter, index)
             for index, (_, chapter, _) in enumerate(grid)]

    aggregate = output / 'claudel-agamemnon-translation.db'
    if aggregate.exists():
        aggregate.unlink()
    for database in (aggregate, shadow):
        conn = init_storage_engine(database) if database == aggregate else sqlite3.connect(str(database))
        try:
            conn.execute('INSERT OR REPLACE INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type) VALUES (?,?,?,?,?,?,?,?)', unit)
            conn.executemany('INSERT OR REPLACE INTO text_segments VALUES (?,?,?)', segments)
            conn.executemany('INSERT OR REPLACE INTO edition_chapter_order VALUES (?,?,?,?,?,?)', order)
            conn.commit()
        finally:
            conn.close()

    catalog_path = output / 'site/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf8'))
    versions = catalog['works'][TEXTGROUP + '.' + WORK]['versions']
    versions[:] = [version for version in versions if version.get('short_id') != VERSION]
    versions.append({'short_id': VERSION, 'urn': URN, 'label': LABEL,
                     'doc_type': 'translation', 'text_class': 'french-text'})
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf8')

    audit = {
        'source': str(source),
        'source_url': 'https://hdl.handle.net/2027/chi.084972221',
        'version_urn': URN,
        'label': LABEL,
        'alignment': 'approximate across the whole play',
        'printed_pages_with_text': sorted(pages),
        'missing_ocr_pages': sorted(set(range(1, 61)) - set(pages)),
        'passage_cards': len(segments),
    }
    (output / 'site/claudel1896-agamemnon-alignment.json').write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    return aggregate
