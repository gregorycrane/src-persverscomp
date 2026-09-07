from lxml import etree

from pipeline.core.xml_utils import extract_text_recursive


TEI = "http://www.tei-c.org/ns/1.0"


def node(xml):
    return etree.fromstring(xml.format(ns=TEI).encode())


def test_inline_citation_preserves_bibl_and_quote_semantics():
    p = node(
        '<p xmlns="{ns}">See <cit><bibl n="Hom. Il. 1.1" '
        'corresp="urn:cts:greekLit:tlg0012.tlg001:1.1">Homer</bibl>: '
        '<quote xml:lang="eng">Sing, goddess</quote></cit>.</p>'
    )
    html = extract_text_recursive(p)
    assert '<cite class="tei-bibl"' in html
    assert 'data-cref="urn:cts:greekLit:tlg0012.tlg001:1.1"' in html
    assert '<q class="tei-quote">Sing, goddess</q>' in html


def test_greek_quote_before_bibl_preserves_order_and_cts_link():
    p = node(
        '<p xmlns="{ns}">compare <cit><quote xml:lang="grc">'
        'γυναικὸς ὢν δούλευμα</quote> '
        '<bibl n="Soph. Ant. 756" '
        'corresp="urn:cts:greekLit:tlg0011.tlg002:756">Ant. 756</bibl>'
        '</cit>.</p>'
    )
    html = extract_text_recursive(p)
    assert html.index('γυναικὸς') < html.index('Ant. 756')
    assert 'data-cref="urn:cts:greekLit:tlg0011.tlg002:756"' in html


def test_play_cross_reference_preserves_cts_targets():
    p = node(
        '<p xmlns="{ns}">see <ref type="cross-reference" '
        'target="urn:cts:greekLit:tlg0085.tlg007:243">l. 243</ref></p>'
    )
    html = extract_text_recursive(p)
    assert '<span class="tei-ref"' in html
    assert 'data-cref="urn:cts:greekLit:tlg0085.tlg007:243"' in html
    assert '>l. 243</span>' in html


def test_citation_with_block_quote_keeps_following_prose_in_a_block():
    p = node(
        '<p xmlns="{ns}"><cit><bibl n="Aesch. Eum. 1"/>'
        '<quote rend="blockquote"><l>Opening line</l></quote></cit>'
        'Following prose.</p>'
    )
    html = extract_text_recursive(p)
    assert '<div class="quote-block type-blockquote">' in html
    assert '<div class="prose-continuation">Following prose.</div>' in html
