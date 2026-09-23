import importlib.util
from pathlib import Path

from pipeline.core.xml_utils import extract_text_recursive


MODULE_PATH = Path(__file__).parents[1] / "tools" / "chs_primary_sources" / "convert_pausanias.py"
spec = importlib.util.spec_from_file_location("chs_pausanias_converter", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_quotes_bibliography_terms_and_embedded_passage_boundary():
    html = b'''<article><div class="contentMain">
      <h2>Scroll IV. Messenia</h2>
      <div class="Paragraph">{4.14.5} Introduction [<em>dik\xc4\x93</em>]:
        <div class="inlineCitation"><div class="Paragraph">\xe2\x80\x9cFirst line.<br/>
        {4.14.6} Second section.\xe2\x80\x9d</div></div>
        <div class="bibl">Tyrtaeus, unknown location.</div>
      </div>
      <div class="Paragraph">An unnumbered continuation.</div>
      <div class="Paragraph">(4.14.7} A malformed but recoverable marker.</div>
      <h2>Inventory of terms and names</h2>
    </div></article>'''
    tree, index = mod.convert(html, "https://example.test", "urn:test")
    ns = {"t": mod.TEI}
    assert tree.xpath('//t:div[@subtype="section"]/@n', namespaces=ns) == ["5", "6", "7"]
    assert len(tree.xpath("//t:cit/t:quote", namespaces=ns)) == 2
    assert tree.xpath("string((//t:cit/t:bibl)[1])", namespaces=ns) == "Tyrtaeus, unknown location."
    assert tree.xpath("string(//t:term)", namespaces=ns) == "dik\u0113"
    assert index["term_count"] == 1
    assert "An unnumbered continuation." in tree.xpath(
        'string(//t:div[@subtype="section"][@n="6"])', namespaces=ns
    )
    rendered = extract_text_recursive(
        tree.xpath('//t:div[@subtype="section"][@n="6"]/t:p', namespaces=ns)[0]
    )
    assert 'class="tei-cit tei-cit-block"' in rendered
    assert 'class="quote-block type-blockquote"' in rendered
    assert 'class="tei-bibl tei-bibl-right"' in rendered
