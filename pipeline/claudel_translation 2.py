"""Build a reversible PMV preview layer from the Claudel HathiTrust OCR."""
import html
import json
import re
import shutil
import sqlite3
from pathlib import Path

from pipeline.core.storage import init_storage_engine

TEXTGROUP = 'tlg0085'
WORK = 'tlg007'
VERSION = 'claudel1920-fra1'
URN = 'urn:cts:greekLit:tlg0085.tlg007.' + VERSION
CANONICAL_ID = 'tlg0085_tlg007_claudel_1920_translation'
LABEL = 'French (Paul Claudel, 1920; OCR, approximate alignment)'
ACTS = ((11, 23, 1, 234), (25, 39, 235, 565), (41, 62, 566, 1047))
PAGE_MARKER = re.compile(r'^## p\.\s*(?:(\d+)\s*)?\(#(\d+)\)\s*#+\s*$', re.M)
SCORE_GAP_PAGES = {
    30: [
        'Veulent que pas à pas',
        'Les Furies à chaque bras',
        "Tiennent et suivent l'insensé qui a fait œuvre de mal",
        "Jusqu'il trouve sous la terre la mort,",
        'La mort,',
        'Non point la mort qui libère.',
        'Autour, tout autour',
        'De ce veau pour notre table,',
        'Strident et sourd, corde et tambour,',
        'Que chant de fou, chant du diable,',
        'Repli pour le dévorer',
        'Tourne mon hymne ensorcelé !',
        'Cette tâche nous fut donnée,',
        'Pour elle nous fûmes créées.',
        'Vous Immortels, bas les mains,',
        'Rien entre nous de commun.',
        'Robes blanches,',
        "Nous n'avons point de part avec vous,",
        "Nous n'avons point notre séjour avec vous.",
    ],
    31: [
        'Le meurtre filial,',
        'Le crime familial,',
        'Le sang frais qui nous fascine,',
        'Nous fait de haut',
        'Fondre sur la tête assassine !',
        'Cette passion est la nôtre,',
        "Ce soin nous l'épargnons à d'autres.",
        "Aux dieux selon qu'il sied",
        'Ce droit de nous le confirmer,',
        'Zeus a privé de lui-même cette race de blasphème.',
        'Le meurtre filial,',
        'Le crime familial,',
        'Le sang frais qui nous fascine,',
        'Nous fait de haut',
        'Fondre sur la tête assassine,',
        'La gloire humaine avec toute son aile déployée',
        'Et réduite en poudre et cendre,',
        'Au souffle de notre voile noir,',
        'Au trépignement de notre danse.',
    ],
}


def extract_pages(source, first_page=11, final_page=62, running_titles=('LES EUMÉNIDES',)):
    """Return cleaned dramatic-text lines keyed by printed page number."""
    raw = Path(source).read_text(encoding='utf8')
    markers = list(PAGE_MARKER.finditer(raw))
    pages, last_page = {}, None
    for i, marker in enumerate(markers):
        explicit = marker.group(1)
        if explicit:
            last_page = int(explicit)
        elif last_page is not None:
            last_page += 1
        if last_page is None or not first_page <= last_page <= final_page:
            continue
        end = markers[i + 1].start() if i + 1 < len(markers) else len(raw)
        lines = []
        for raw_line in raw[marker.end():end].replace('\f', '').splitlines():
            line = ' '.join(raw_line.strip().split())
            if not line or line == str(last_page) or line in running_titles:
                continue
            if lines and re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]-$', lines[-1]) and re.match(r'^[a-zà-öø-ÿ]', line):
                lines[-1] = lines[-1][:-1] + line
            else:
                lines.append(line)
        if lines:
            pages[last_page] = lines
    return pages


def extract_score_gap(source):
    """Reconstruct the gap from score OCR split across staves and syllables."""
    raw = Path(source).read_text(encoding='utf8')
    anchors = ('Lachesis Atropos', "m'emportent dans les flancs", 'Le meurtre fi')
    if not all(anchor in raw for anchor in anchors):
        raise ValueError('The supplemental score does not contain the expected Claudel passage')
    return {page: list(lines) for page, lines in SCORE_GAP_PAGES.items()}


def _bounds(chapter):
    numbers = re.findall(r'\d+', chapter)
    return int(numbers[0]), int(numbers[-1])


def align_pages(pages, grid, ranges=ACTS):
    """Distribute OCR lines across Greek cards within three explicit acts.

    This is deliberately described as approximate alignment. The act anchors
    are secure; allocation within an act follows the amount of Greek verse
    covered by each existing PMV card.
    """
    aligned = {row[0]: [] for row in grid}
    for first_page, last_page, first_line, last_line in ranges:
        source_lines = [(page, line) for page in range(first_page, last_page + 1)
                        for line in pages.get(page, [])]
        targets = []
        for passage_urn, chapter, _ in grid:
            start, end = _bounds(chapter)
            overlap = max(0, min(end, last_line) - max(start, first_line) + 1)
            if overlap:
                targets.append((passage_urn, overlap))
        total = sum(weight for _, weight in targets)
        used = 0
        for index, (passage_urn, weight) in enumerate(targets):
            next_used = len(source_lines) if index == len(targets) - 1 else round(
                sum(w for _, w in targets[:index + 1]) * len(source_lines) / total)
            aligned[passage_urn].extend(source_lines[used:next_used])
            used = next_used
    return aligned


def _render(lines, first=False, patched=False):
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
    gap_note = ("Printed pp. 30–31 have been reconstructed from Claudel's text "
                'in the 1927 Milhaud vocal score. ' if patched else
                'The supplied OCR has no extracted text for printed pp. 30–31. ')
    note = ('<div class="claudel-alignment-note"><strong>OCR preview.</strong> '
            'The source has no Aeschylean line numbers; its three acts are aligned approximately '
            'to the Greek passage cards. ' + gap_note +
            'Source: <cite>Les Euménides d\'Eschyle</cite>, trans. Paul Claudel '
            '(Paris: Nouvelle revue française, 1920), pp. 11–62; '
            '<a href="https://hdl.handle.net/2027/wu.89013526876" target="_blank" rel="noopener">HathiTrust scan</a>.</div>')
    return (note if first else '') + ''.join(chunks)


def build_translation(source, output, existing, score=None):
    """Create an aggregate layer and a shadow copy of the Eumenides shard."""
    source, output, existing = Path(source), Path(output), Path(existing)
    original = existing / 'site/data' / TEXTGROUP / WORK / (TEXTGROUP + '.' + WORK + '.part1.db')
    shadow = output / 'site/data' / TEXTGROUP / WORK / original.name
    shadow.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, shadow)

    with sqlite3.connect(original.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        grid = conn.execute(
            'SELECT passage_urn,chapter,sort_order FROM alignment_grid ORDER BY sort_order').fetchall()
    pages = extract_pages(source)
    patched = bool(score)
    if score:
        pages.update(extract_score_gap(score))
    aligned = align_pages(pages, grid)
    unit = (CANONICAL_ID, URN, LABEL, 'french-text', TEXTGROUP, WORK, VERSION, 'translation')
    segments = [(urn, VERSION, _render(aligned[urn], first=index == 0, patched=patched))
                for index, (urn, _, _) in enumerate(grid)]
    order = [(TEXTGROUP, WORK, VERSION, None, chapter, index)
             for index, (_, chapter, _) in enumerate(grid)]

    aggregate = output / 'claudel-translation.db'
    if aggregate.exists():
        aggregate.unlink()
    for database in (aggregate, shadow):
        conn = init_storage_engine(database) if database == aggregate else sqlite3.connect(str(database))
        try:
            conn.execute('INSERT OR REPLACE INTO text_units VALUES (?,?,?,?,?,?,?,?)', unit)
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
        'source': str(source), 'source_url': 'https://hdl.handle.net/2027/wu.89013526876',
        'version_urn': URN, 'label': LABEL, 'alignment': 'approximate within act boundaries',
        'supplemental_score': str(score) if score else None,
        'supplemental_score_url': 'https://hdl.handle.net/2027/uc1.31822002779502' if score else None,
        'printed_pages_with_text': sorted(pages),
        'missing_ocr_pages': [] if patched else [30, 31],
        'patched_pages': [30, 31] if patched else [],
        'passage_cards': len(segments),
    }
    (output / 'site/claudel1920-alignment.json').write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    return aggregate
