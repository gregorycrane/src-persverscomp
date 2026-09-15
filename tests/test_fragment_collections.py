from pathlib import Path
import xml.etree.ElementTree as ET
from pipeline.fragment_collections import build,materialize_work_views,NS

SOURCE=Path(__file__).parent/'fixtures/nauck-collection-sample.xml'

def test_shared_source_separate_works_and_collection_membership():
    raw=build(SOURCE); d=materialize_work_views(raw)
    a=d['works']['aeschylus-athamas']; b=d['works']['aeschylus-danaides']
    assert a['source']==b['source'] and a['selector']!=b['selector']
    assert a['object_urn']!=b['object_urn']
    assert a['object_urn']=='urn:cite2:perseus:fragmentaryplays.v1:athamas'
    assert a['fragments'][0]['same_as']==[]
    assert a['fragments'][0]['source_fragment_urn']=='urn:cts:greekLit:tlg0085.fragmenta.nauck1889grc1:1'
    assert a['versions'][0]['edition_urn']=='urn:cts:greekLit:tlg0085.fragmenta.nauck1889grc1'
    assert 'fragments' not in raw['works']['aeschylus-athamas']
    assert raw['attributions'][0]['corresp'][0]==raw['fragments'][0]['source_fragment_urn']
    assert raw['attributions'][0]['urn'].startswith(
        'urn:cite2:perseus:fragmentattributions.v1:')
    assert all('aeschylus-athamas' in c['members'] for c in d['collections'])

def test_context_exclusion_and_no_fabricated_text():
    d=materialize_work_views(build(SOURCE))
    a=d['works']['aeschylus-athamas']; empty=d['works']['aeschylus-atalante']
    assert a['fragments'][0]['lines'][0]['text']=='τρίπους'
    assert 'λέβητας' in a['fragments'][0]['context']
    assert empty['versions']==[] and empty['line_count']==0
    assert empty['introduction']=='Vide catalogum.'

def test_source_unchanged_and_fragment_number_preserved():
    before=SOURCE.read_bytes(); raw=build(SOURCE); d=materialize_work_views(raw)
    assert SOURCE.read_bytes()==before
    assert d['works']['aeschylus-danaides']['fragments'][0]['number']=='44'
    assert d['scope']['outside_play_containers']==2
    assert d['scope']['included_fragments']==4
    assert d['works']['aeschylus-incertae']['fragments'][0]['number']=='999'
    assert d['works']['aeschylus-dubia-spuria']['fragments'][0]['number']=='1000'
    assert d['scope']['uncertain_fragments']==1
    assert d['scope']['dubious_spurious_fragments']==1


def test_explicit_corresp_routes_an_editorial_attribution(tmp_path):
    source = tmp_path / 'corresp.xml'
    source.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div subtype="play" xml:id="aeschylus-athamas"><div type="fragment" n="1"
        corresp="#aeschylus-danaides"><lg><l>λόγος</l></lg></div></div>
      <div subtype="play" xml:id="aeschylus-danaides"/>
    </body></text></TEI>''')
    raw = build(source); data = materialize_work_views(raw)
    assert data['works']['aeschylus-athamas']['fragments'] == []
    fragment = data['works']['aeschylus-danaides']['fragments'][0]
    assert fragment['source_fragment_urn'].endswith(':1')
    assert raw['attributions'][0]['play_urn'] == 'urn:cite2:perseus:fragmentaryplays.v1:danaides'
    assert raw['attributions'][0]['corresp'] == [fragment['source_fragment_urn']]
