from pathlib import Path
import xml.etree.ElementTree as ET
from pipeline.fragment_collections import build,NS

SOURCE=Path(__file__).parent/'fixtures/nauck-collection-sample.xml'

def test_shared_source_separate_works_and_collection_membership():
    d=build(SOURCE)
    a=d['works']['aeschylus-athamas']; b=d['works']['aeschylus-danaides']
    assert a['source']==b['source'] and a['selector']!=b['selector']
    assert a['work_urn']!=b['work_urn']
    assert all('aeschylus-athamas' in c['members'] for c in d['collections'])

def test_context_exclusion_and_no_fabricated_text():
    d=build(SOURCE)
    a=d['works']['aeschylus-athamas']; empty=d['works']['aeschylus-atalante']
    assert a['fragments'][0]['lines'][0]['text']=='τρίπους'
    assert 'λέβητας' in a['fragments'][0]['context']
    assert empty['edition_urn'] is None and empty['line_count']==0
    assert empty['introduction']=='Vide catalogum.'

def test_source_unchanged_and_fragment_number_preserved():
    before=SOURCE.read_bytes(); d=build(SOURCE)
    assert SOURCE.read_bytes()==before
    assert d['works']['aeschylus-danaides']['fragments'][0]['number']=='44'
    assert d['scope']['outside_play_containers']==1
