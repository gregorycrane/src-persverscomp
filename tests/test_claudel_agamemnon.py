import json
import sqlite3

from pipeline.claudel_agamemnon import build_translation
from pipeline.core.storage import init_storage_engine


def test_claudel_agamemnon_builds_complete_translation_layer(tmp_path):
    source = tmp_path / 'agamemnon.txt'
    source.write_text('''## p. 1 (#5) ####
1
AGAMEMNON
Le Veilleur
Premier texte.
## p. 60 (#64) ####
60
Dernier texte.
''')
    existing = tmp_path / 'existing'
    (existing / 'site').mkdir(parents=True)
    (existing / 'site/catalog.json').write_text('{"works":{"tlg0085.tlg005":{"versions":[]}}}')
    preview = tmp_path / 'preview'
    (preview / 'site').mkdir(parents=True)
    (preview / 'site/catalog.json').write_text((existing / 'site/catalog.json').read_text())
    shard = existing / 'site/data/tlg0085/tlg005/tlg0085.tlg005.part1.db'
    shard.parent.mkdir(parents=True)
    conn = init_storage_engine(shard)
    rows = [('urn:cts:greekLit:tlg0085.tlg005:0-39.1', '0-39', 1),
            ('urn:cts:greekLit:tlg0085.tlg005:40-1673.1', '40-1673', 2)]
    conn.executemany('INSERT INTO alignment_grid VALUES (?,"tlg0085","tlg005",NULL,?,"1",NULL,NULL,?)', rows)
    conn.commit()
    conn.close()

    aggregate = build_translation(source, preview, existing)
    with sqlite3.connect(str(aggregate)) as conn:
        assert conn.execute('SELECT doc_type FROM text_units').fetchone() == ('translation',)
        content = ''.join(row[0] for row in conn.execute(
            'SELECT content_html FROM text_segments ORDER BY passage_urn'))
        assert 'Premier texte.' in content
        assert 'Dernier texte.' in content
        assert 'approximate' in content
    audit = json.loads((preview / 'site/claudel1896-agamemnon-alignment.json').read_text())
    assert audit['passage_cards'] == 2
    assert 'claudel1896-fra1' in (preview / 'site/catalog.json').read_text()
