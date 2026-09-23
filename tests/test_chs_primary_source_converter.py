import importlib.util
from pathlib import Path

from lxml import etree
from pipeline.core.xml_utils import extract_text_recursive


MODULE_PATH = Path(__file__).parents[1] / "tools" / "chs_primary_sources" / "convert.py"
spec = importlib.util.spec_from_file_location("chs_converter", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_bold_and_plain_lines_terms_and_stage(tmp_path):
    canonical = tmp_path / "base.xml"
    canonical.write_text("""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div>
      <sp><speaker>Πυθιάς</speaker><l n="1">x</l><l n="6">x</l></sp>
      <sp><speaker>Πυθιάς</speaker><l n="34">x</l><l n="40">x</l></sp>
    </div></body></text></TEI>""", encoding="utf8")
    html = b"""<article><div class="contentMain"><h1>Eumenides</h1>
      <p>By Aeschylus Translated by Herbert Weir Smyth Revised by Cynthia Bannon Further Revised by Gregory Nagy</p>
      <p><strong>Pythia</strong><br/>First seer [<em>mantis</em>]. <strong>5</strong> More.</p>
      <p><em>She exits.</em></p>
      <p>Horrors <strong>40</strong> text.</p>
      <div class="Paragraph">Notes</div>
    </div></article>"""
    tree, index = mod.convert(html, canonical, "https://example.test", "urn:test")
    ns = {"t": mod.TEI}
    assert tree.xpath("//t:sp[1]/t:l/@n", namespaces=ns) == ["1", "5"]
    assert tree.xpath("//t:sp[2]/t:l/@n", namespaces=ns) == ["34", "40"]
    assert tree.xpath("string(//t:term)", namespaces=ns) == "mantis"
    assert index["terms"][0]["occurrences"][0]["gloss"] == "seer"
    assert index["terms"][0]["occurrences"][0]["gloss_context"] == "First seer"
    assert tree.xpath("string(//t:stage)", namespaces=ns) == "She exits."
    rendered = extract_text_recursive(tree.xpath("//t:l[1]", namespaces=ns)[0])
    assert 'class="tei-term"' in rendered
    assert 'data-term-key="mantis"' in rendered


def test_plain_consecutive_line_numbers(tmp_path):
    canonical = tmp_path / "base.xml"
    canonical.write_text("""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div>
      <sp><speaker>Ἀθηνᾶ</speaker><l n="681">x</l><l n="710">x</l></sp>
    </div></body></text></TEI>""", encoding="utf8")
    html = b"""<article><div class="contentMain"><h1>x</h1><p><strong>Athena</strong>
      Start. 696 Neither anarchy 697 nor tyranny. <strong>700</strong> End.</p>
      <div class="Paragraph">Notes</div></div></article>"""
    tree, _ = mod.convert(html, canonical, "https://example.test", "urn:test")
    ns = {"t": mod.TEI}
    assert tree.xpath("//t:l/@n", namespaces=ns) == ["681", "696", "697", "700"]
