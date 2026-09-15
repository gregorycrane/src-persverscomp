import json
import sqlite3
from pathlib import Path
from pipeline.fragment_collections import build
from pipeline.fragment_shards import build_shards

def test_real_shards_have_one_edition_navigation_and_separate_context(tmp_path):
    source=Path(__file__).parent/'fixtures/nauck-collection-sample.xml'
    data=build(source)
    existing=tmp_path/'original';(existing/'site').mkdir(parents=True)
    catalog={'works':{'unchanged':{'title':'Existing work'}}}
    (existing/'site/catalog.json').write_text(json.dumps(catalog))
    out=tmp_path/'preview';(out/'site').mkdir(parents=True)
    aggregate=build_shards(data,out,existing)
    with sqlite3.connect(aggregate) as c:
        assert c.execute('select count(*) from text_units').fetchone()[0]==4
        assert c.execute('select count(*) from treebank_sentences').fetchone()[0]==0
        assert c.execute('select count(*) from text_units where doc_type="translation"').fetchone()[0]==0
        html=c.execute('select content_html from text_segments order by passage_urn').fetchone()[0]
        assert 'fc-verse' in html and 'fc-context' in html
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert 'pmv_work_key' not in data['works']['aeschylus-atalante']
    published=json.loads((out/'site/catalog.json').read_text())
    assert 'tlg0085.athamas' in published['works']
    assert json.loads((existing/'site/catalog.json').read_text())==catalog
    for file in (out/'site/data').rglob('*.db'):
        with sqlite3.connect(file) as c:
            assert c.execute('select count(distinct work) from text_units').fetchone()[0]==1
            assert c.execute('select count(*) from text_units').fetchone()[0]==1
