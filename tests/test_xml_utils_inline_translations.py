from lxml import etree

from pipeline.core.xml_utils import extract_text_recursive


def test_inline_translations_are_bracketed_and_identified():
    p = etree.fromstring(
        b'''<p xmlns="http://www.tei-c.org/ns/1.0">
          <mentioned xml:lang="grc">protos</mentioned>
          <mentioned type="translation" xml:lang="eng" corresp="#m1">first</mentioned>;
          <foreign xml:lang="grc">de</foreign>
          <foreign type="translation" xml:lang="eng" corresp="#m2">but</foreign>;
          <quote xml:lang="grc">tis gar</quote>
          <quote type="translation" xml:lang="eng" corresp="#m3">for who?</quote>
        </p>'''
    )

    html = extract_text_recursive(p)

    assert '<span class="lemma render-bold">protos</span>' in html
    assert '<span class="foreign foreign-grc" lang="grc">de</span>' in html
    assert '<q class="tei-quote">tis gar</q>' in html
    for source, corresp, text in (
        ('mentioned', '#m1', 'first'),
        ('foreign', '#m2', 'but'),
        ('quote', '#m3', 'for who?'),
    ):
        assert f'tei-inline-translation translation-{source}' in html
        assert f'data-corresp="{corresp}"' in html
        assert f'>[{text}]</span>' in html


def test_ordinary_quote_rendering_is_unchanged():
    quote = etree.fromstring(b'<quote>ordinary quotation</quote>')
    assert extract_text_recursive(quote) == '<q class="tei-quote">ordinary quotation</q>'
