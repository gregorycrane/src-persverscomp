from lxml import etree
from pipeline.core.xml_utils import extract_text_recursive

def test_source_reference_is_clickable_inside_translation_note():
    el=etree.fromstring('<l>Verse<note>Source: <ref target="/site/data/edition/gallery.html#p57">page 57</ref></note></l>')
    result=extract_text_recursive(el)
    assert 'href="/site/data/edition/gallery.html#p57"' in result
    assert '>page 57</a>' in result
    assert result.count('<a ')==result.count('</a>')==1

def test_remote_reference_attributes_are_escaped():
    el=etree.Element('ref',target='https://example.org/page?a="&b=2')
    el.text='source'
    assert 'href="https://example.org/page?a=&quot;&amp;b=2"' in extract_text_recursive(el)

def test_citation_and_non_web_targets_remain_non_navigating_references():
    for target in ['urn:cts:greekLit:tlg0006.tlg007:1','javascript:alert(1)','data:text/html,test','file:///private/file','//example.org/page']:
        el=etree.Element('ref',target=target);el.text='reference'
        result=extract_text_recursive(el)
        assert '<a ' not in result
        assert 'data-cref=' in result
        assert result.endswith('</span>')
