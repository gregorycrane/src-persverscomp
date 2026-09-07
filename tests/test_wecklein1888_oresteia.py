import importlib.util
import json
from pathlib import Path

from lxml import etree
from pipeline.parsers.line_commentary import parse_line_commentary_tei

HERE = Path(__file__).parent
NS = {'t': 'http://www.tei-c.org/ns/1.0'}


def render(play):
    intervals = {'': [
        {'book': '', 'label': str(i), 'start_line': i, 'end_line': i}
        for i in range(1, 1101)
    ]}
    return parse_line_commentary_tei(
        str(HERE / 'fixtures' / f'wecklein1888_{play}.xml'), intervals,
        lineno_sigil='Weck.', anchor_axis='corresp',
        reference_sigil='Smyth', show_reference_line=True,
    )['']


def test_single_witness_choephoroi_keeps_flags_and_reference_placement():
    result = render('tlg006')
    assert 'Single-witness OCR' in result['1']['1']
    assert 'Weck. 587-588' in result['589']['1']
    assert 'Smyth 589-590' in result['589']['1']
    assert 'Reference alignment provisional' in result['589']['1']
    assert 'Weck. 1074' in result['1076']['1']
    whole = ''.join(x['1'] for x in result.values())
    assert 'tei-sic' in whole and 'babel.hathitrust.org' in whole
    assert 'Second-witness OCR is unavailable' not in whole


def test_eumenides_missing_scan_is_not_an_ancient_lacuna():
    result = render('tlg007')
    assert 'Second-witness OCR is unavailable' in result['590']['1']
    assert 'not a lacuna in the ancient text' in result['590']['1']
    assert 'Weck. 630-631' in result['627']['1']
    assert 'Weck. 1045-1046' in result['1044']['1']
    tree = etree.parse(str(HERE / 'fixtures' / 'wecklein1888_tlg007.xml'))
    gaps = tree.xpath('//t:gap', namespaces=NS)
    assert gaps and all(g.get('reason') == 'ocr-source-unavailable' for g in gaps)
    assert all(g.get('source') == '#hxjha8' for g in gaps)
    assert tree.xpath('//t:cit/t:quote', namespaces=NS)
    assert not tree.xpath('//t:app|//t:l', namespaces=NS)


def test_comparison_continuation_after_missing_pages_is_not_misattributed(tmp_path, monkeypatch):
    source = HERE.parent / 'tools' / 'wecklein1888' / 'oresteia' / 'extract.py'
    spec = importlib.util.spec_from_file_location('oresteia_extract', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'D', tmp_path)
    monkeypatch.setattr(module, 'CONFIG', {'tlg007': {
        'first': 293, 'last': 296, 'witnesses': ['hw42j8', 'hxjha8'],
    }})
    def page(lines):
        return {'seq': 1, 'lines': lines}
    pages = {
        'hw42j8': {
            '293': page(['592. previous note']),
            '294': page(['593. preserved base']),
            '295': page(['629. note before page break']),
            '296': page(['continuation of 629', '630. following note']),
        },
        'hxjha8': {
            '293': page(['592. previous note']),
            '296': page(['continuation of 629', '630. following note']),
        },
    }
    monkeypatch.setattr(module, 'parse_pages', lambda: pages)
    (tmp_path / 'boundaries.json').write_text(json.dumps({
        str(p): {'start': 0, 'second_start': 0} for p in range(293, 297)
    }))
    result = module.extract()['tlg007']
    previous = result['hxjha8'][0]
    assert 'continuation of 629' not in ' '.join(p['text'] for p in previous['parts'])
    orphans = json.loads((tmp_path / 'unanchored-comparison.json').read_text())
    assert orphans[0]['text'] == 'continuation of 629'
    assert len(result['hw42j8']) == 4
    assert result['hxjha8'][-1]['n'] == '630'
