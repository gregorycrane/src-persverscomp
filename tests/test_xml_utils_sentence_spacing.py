from lxml import etree

from pipeline.core.xml_utils import extract_text_recursive


def test_adjacent_tei_sentences_render_with_a_word_boundary():
    paragraph = etree.fromstring(
        '<p xmlns="http://www.tei-c.org/ns/1.0">'
        '<s>First sentence.</s><s>Second sentence.</s>'
        '</p>'
    )
    html = extract_text_recursive(paragraph)
    assert 'First sentence.</span> <span class="lemma">Second sentence.' in html
