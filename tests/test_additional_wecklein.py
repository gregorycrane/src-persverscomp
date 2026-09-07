from pathlib import Path
import pytest
from lxml import etree,html
from pipeline.parsers.line_commentary import parse_line_commentary_tei

N={'t':'http://www.tei-c.org/ns/1.0'}
@pytest.mark.parametrize('name,play,year,author,sigil',[
 ('suppliants','tlg001','1902','N. Wecklein','Weck.'),
 ('persians','tlg002','1886','W. S. Teuffel','Teuff.–Weck.'),
 ('seven','tlg004','1902','N. Wecklein','Weck.'),
])
def test_source_identity_and_provisional_commentary_rendering(name,play,year,author,sigil):
 path=Path(__file__).parent/'fixtures'/(name+'-wecklein.xml')
 t=etree.parse(str(path));urn=t.xpath('//t:body/t:div/@n',namespaces=N)[0]
 assert urn.startswith('urn:cts:greekLit:tlg0085.'+play+'.')
 assert t.xpath('//t:titleStmt/t:author/text()',namespaces=N)==[author]
 assert t.xpath('//t:bibl/t:date/text()',namespaces=N)==[year]
 if name=='persians':
  assert t.xpath('//t:titleStmt/t:editor[@role="reviser"]/text()',namespaces=N)==['N. Wecklein']
 assert not t.xpath('//t:app|//t:l',namespaces=N)
 intervals={'':[{'book':'','label':str(i),'start_line':i,'end_line':i} for i in range(1,1201)]}
 result=parse_line_commentary_tei(str(path),intervals,lineno_sigil=sigil,anchor_axis='corresp',reference_sigil='Smyth',show_reference_line=True)['']
 whole=''.join(x['1'] for x in result.values());dom=html.fragment_fromstring(whole,create_parent='div')
 expected=[sigil+' '+n for n in t.xpath('//t:div[@subtype="commline"]/@n',namespaces=N)]
 assert sorted(dom.xpath('//span[@class="comm-native-line"]/text()'))==sorted(expected)
 assert 'Single-witness OCR' in whole and 'Reference placement provisional' in whole
 assert 'babel.hathitrust.org' in whole and 'Smyth' in whole
