import json
from pathlib import Path

from pipeline.sophocles_fragment_collections import build

SOURCES = [Path('/Users/gcrane/github/grcnewxml/data/tlg0011/fragments/source') /
           f'sophocles.fragments.jebbetal1917v{i}-mul1.xml' for i in (1, 2, 3)]


def test_pearson_fragments_preserve_volume_and_page_provenance():
    data = build(SOURCES)
    assert len(data['fragments']) == 1128
    assert data['scope']['play_headings'] == 104
    assert [f['number'] for f in data['fragments'] if f['number'] == '314'] == []
    assert {f['volume'] for f in data['fragments']} == {'1', '2', '3'}
    assert all(f['page'] and f['pages'] and f['page_refs'] for f in data['fragments'])
    assert all(f['page'] == f['pages'][0] for f in data['fragments'])


def test_ichneutae_is_linked_instead_of_duplicated():
    data = build(SOURCES)
    linked = [w for w in data['works'].values() if w.get('external_work_urn')]
    assert len(linked) == 1
    assert linked[0]['external_work_urn'] == 'urn:cts:greekLit:tlg0011.tlg008'
    assert linked[0]['external_fragment'] == '314'


def test_checked_in_collection_matches_sources():
    checked = json.loads((Path(__file__).parents[1] /
                          'experimental/sophocles/fragment-collections.json').read_text())
    rebuilt = build(SOURCES)
    assert checked['source_sha256'] == rebuilt['source_sha256']
    assert checked['scope'] == rebuilt['scope']
