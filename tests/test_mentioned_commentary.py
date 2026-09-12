from lxml import etree
from pipeline.core.xml_utils import extract_text_recursive

def test_linked_commentary_is_not_rendered_as_a_footnote():
    p=etree.fromstring('''<p xmlns="http://www.tei-c.org/ns/1.0"><mentioned ana="#n">ad familiares</mentioned><note type="commentary" xml:id="n">. Cp. <cit type="textual"><bibl>Gell. 17.9</bibl> <quote xml:lang="lat">libri sunt epistularum</quote></cit>.</note></p>''')
    html=extract_text_recursive(p)
    assert '<span class="lemma render-bold">ad familiares</span>' in html
    assert '<span class="commentary-note">. Cp.' in html
    assert '<span class="note">[' not in html
    assert '<cite class="tei-bibl">Gell. 17.9</cite>' in html
    assert '<q class="tei-quote">libri sunt epistularum</q>' in html

def test_an_unlinked_ordinary_note_keeps_footnote_rendering():
    p=etree.fromstring('<p>Text<note>A footnote</note>.</p>')
    assert '<span class="note">[A footnote]</span>' in extract_text_recursive(p)
