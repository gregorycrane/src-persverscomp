from pathlib import Path
from lxml import etree,html
from pipeline.parsers.line_commentary import parse_line_commentary_tei
N={'t':'http://www.tei-c.org/ns/1.0'}

def test_wecklein_allen_provenance_and_visible_uncertainty():
 path=Path(__file__).parent/'fixtures'/'prometheus-wecklein-allen.xml'
 t=etree.parse(str(path))
 assert t.xpath('//t:text/@xml:lang',namespaces=N)==['eng']
 assert t.xpath('//t:titleStmt/t:editor[@role="translator"]/text()',namespaces=N)==['F. D. Allen']
 assert set(t.xpath('//t:bibl/t:date/text()',namespaces=N))=={'1891','1893'}
 intervals={'':[{'book':'','label':str(i),'start_line':i,'end_line':i} for i in range(1,1101)]}
 data=parse_line_commentary_tei(str(path),intervals,lineno_sigil='Weck.–Allen.',anchor_axis='corresp',reference_sigil='Smyth',show_reference_line=True)['']
 whole=''.join(x['1'] for x in data.values());dom=html.fragment_fromstring(whole,create_parent='div')
 assert len(dom.xpath('//span[@class="comm-native-line"]'))==len(t.xpath('//t:div[@subtype="commline"]',namespaces=N))
 assert 'Two-source OCR draft' in whole and 'Reference placement provisional' in whole
 assert 'reconstructed 1891 OCR' in whole
 assert 'oxu1.601566764' in whole and 'oxu1.601623131' in whole
 assert dom.xpath('//*[contains(@class,"tei-sic")]')
 assert 'Prometheus sinks into the depths' in whole
