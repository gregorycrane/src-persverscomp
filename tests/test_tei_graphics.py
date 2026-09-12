from lxml import etree
from pipeline.core.xml_utils import extract_text_recursive

def test_metrical_facsimile_survives_inside_a_translation_note():
    elem=etree.fromstring('<l xmlns="http://www.tei-c.org/ns/1.0">Verse<note><figure><graphic url="/site/images/metre.png" n="Metrical scheme"/><figDesc>Source page 76</figDesc></figure></note></l>')
    rendered=extract_text_recursive(elem)
    assert '<img src="/site/images/metre.png" alt="Metrical scheme"' in rendered
    assert 'Source page 76' in rendered
    assert rendered.count('<a ')==rendered.count('</a>')==1

def test_graphic_attribute_values_are_escaped():
    elem=etree.Element('graphic',url='/site/metre.png?x="&y=2',n='A "quoted" caption')
    rendered=extract_text_recursive(elem)
    assert 'x=&quot;&amp;y=2' in rendered
    assert 'alt="A &quot;quoted&quot; caption"' in rendered

def test_executable_graphic_urls_are_not_rendered():
    for url in ['javascript:alert(1)','data:text/html,test','file:///etc/passwd','//unknown.example/image.png']:
        assert '<img' not in extract_text_recursive(etree.Element('graphic',url=url))
