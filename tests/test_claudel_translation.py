import sqlite3

from pipeline.claudel_translation import build_translation, extract_pages
from pipeline.core.storage import init_storage_engine


def test_claudel_ocr_builds_translation_layer(tmp_path):
    source = tmp_path / 'claudel.txt'
    source.write_text('''## p. 11 (#19) ####
11
LES EUMÉNIDES
ACTE I
Une succes-
sion.
## p. 25 (#33) ####
ACTE II
Texte <deux>.
## p. 41 (#47) ####
ACTE III
Texte trois.
''')
    existing = tmp_path / 'existing'
    (existing / 'site').mkdir(parents=True)
    (existing / 'site/catalog.json').write_text('{"works":{"tlg0085.tlg007":{"versions":[]}}}')
    preview = tmp_path / 'preview'
    (preview / 'site').mkdir(parents=True)
    (preview / 'site/catalog.json').write_text((existing / 'site/catalog.json').read_text())
    shard = existing / 'site/data/tlg0085/tlg007/tlg0085.tlg007.part1.db'
    shard.parent.mkdir(parents=True)
    conn = init_storage_engine(shard)
    rows = [('urn:cts:greekLit:tlg0085.tlg007:1-234.1', '1-234', 1),
            ('urn:cts:greekLit:tlg0085.tlg007:235-565.1', '235-565', 2),
            ('urn:cts:greekLit:tlg0085.tlg007:566-1047.1', '566-1047', 3)]
    conn.executemany('INSERT INTO alignment_grid VALUES (?,"tlg0085","tlg007",NULL,?,"1",NULL,NULL,?)', rows)
    conn.commit()
    conn.close()

    pages = extract_pages(source)
    assert pages[11] == ['ACTE I', 'Une succession.']
    aggregate = build_translation(source, preview, existing)
    with sqlite3.connect(str(aggregate)) as conn:
        assert conn.execute('SELECT doc_type FROM text_units').fetchone() == ('translation',)
        segments = conn.execute('SELECT content_html FROM text_segments ORDER BY passage_urn').fetchall()
        assert len(segments) == 3
        assert 'approximate' in segments[0][0]
        assert '&lt;deux&gt;' in ''.join(row[0] for row in segments)
    assert 'claudel1920-fra1' in (preview / 'site/catalog.json').read_text()
