from pathlib import Path
from lxml import etree
from pipeline.parsers.line_commentary import parse_line_commentary_tei

FIXTURE = Path(__file__).parent / 'fixtures' / 'wecklein1888_commentary.xml'
NS = {'t': 'http://www.tei-c.org/ns/1.0'}


def test_wecklein_notes_render_under_reference_cards_with_source_labels():
    intervals = {'': [
        {'book': '', 'label': '1-10', 'start_line': 1, 'end_line': 10},
        {'book': '', 'label': '890-899', 'start_line': 890, 'end_line': 899},
        {'book': '', 'label': '900-910', 'start_line': 900, 'end_line': 910},
        {'book': '', 'label': '1660-1673', 'start_line': 1660, 'end_line': 1673},
    ]}
    result = parse_line_commentary_tei(
        str(FIXTURE), intervals, lineno_sigil='Weck.',
        anchor_axis='corresp', reference_sigil='Smyth', show_reference_line=True,
    )['']
    assert '890-899' not in result
    middle = result['900-910']['1']
    assert 'Weck. 895' in middle and 'Smyth 904' in middle
    assert 'Überma' in middle
    assert 'Man erblickt' in result['1-10']['1']
    assert 'θήσομεν' in result['1660-1673']['1']
    joined = ''.join(v['1'] for v in result.values())
    assert 'tei-sic' in joined
    assert 'Reference alignment provisional' in joined
    assert 'babel.hathitrust.org' in joined
    assert 'ANHANG' not in joined


def test_wecklein_fixture_preserves_provenance_and_resolvable_local_pointers():
    tree = etree.parse(str(FIXTURE), etree.XMLParser(recover=False))
    assert tree.xpath('//t:citeStructure', namespaces=NS)
    assert tree.xpath('//t:cRefPattern', namespaces=NS)
    assert tree.xpath('//t:pb[@facs]', namespaces=NS)
    assert not tree.xpath('//t:app', namespaces=NS)
    ids = tree.xpath('//@xml:id', namespaces=NS)
    assert len(ids) == len(set(ids))
    for node in tree.xpath('//*[@source or @resp]'):
        for name in ('source', 'resp'):
            for pointer in node.get(name, '').split():
                if pointer.startswith('#'):
                    assert pointer[1:] in ids
