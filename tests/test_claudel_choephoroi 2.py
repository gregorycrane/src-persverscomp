import json
import sqlite3

from pipeline.claudel_choephoroi import build_translation
from pipeline.core.storage import init_storage_engine


def test_claudel_choephoroi_excludes_notes_and_builds_translation(tmp_path):
    source = tmp_path / 'choephoroi.txt'
    source.write_text('''## p. 8 (#12) ####
PERSONNAGES
ORESTE
## p. 9 (#13) ####
9
LES CHOÉPHORES
ORESTE. Premier texte.
## p. 56 (#60) ####
56
Dernier texte.
FIN
## p. 57 (#61) ####
ESSAI DE MISE EN SCÈNE
Texte critique exclu.
''')
    existing = tmp_path / 'existing'
    (existing / 'site').mkdir(parents=True)
    (existing / 'site/catalog.json').write_text('{"works":{"tlg0085.tlg006":{"versions":[]}}}')
    preview = tmp_path / 'preview'
    (preview / 'site').mkdir(parents=True)
    (preview / 'site/catalog.json').write_text((existing / 'site/catalog.json').read_text())
    shard = existing / 'site/data/tlg0085/tlg006/tlg0085.tlg006.part1.db'
    shard.parent.mkdir(parents=True)
    conn = init_storage_engine(shard)
    rows = [('urn:cts:greekLit:tlg0085.tlg006:1-21.1', '1-21', 1),
            ('urn:cts:greekLit:tlg0085.tlg006:22-1076.1', '22-1076', 2)]
    conn.executemany('INSERT INTO alignment_grid VALUES (?,"tlg0085","tlg006",NULL,?,"1",NULL,NULL,?)', rows)
    conn.commit()
    conn.close()

    aggregate = build_translation(source, preview, existing)
    with sqlite3.connect(str(aggregate)) as conn:
        content = ''.join(row[0] for row in conn.execute(
            'SELECT content_html FROM text_segments ORDER BY passage_urn'))
        assert 'Premier texte.' in content
        assert 'Dernier texte.' in content
        assert 'Texte critique exclu.' not in content
        assert conn.execute('SELECT doc_type FROM text_units').fetchone() == ('translation',)
    audit = json.loads((preview / 'site/claudel1920-choephoroi-alignment.json').read_text())
    assert audit['dramatic_text_pages'] == [9, 56]
    assert audit['passage_cards'] == 2
    assert 'claudel1920-fra1' in (preview / 'site/catalog.json').read_text()
