"""Ottava-rima (Ariosto, Orlando Furioso) reading-text carding:
<div subtype="canto"> is a book, each <lg type="stanza"> is a card whose
label is the bare stanza number. Covers both the interval builder and the
poetry_cards walker added for it."""
from pipeline.core.canonical_intervals import build_poetry_canonical_intervals
from pipeline.parsers.poetry_cards import parse_poetry_cards_tei

_TEI = '''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
  <div type="textpart" subtype="canto" n="1">
    <head>Canto 1</head>
    <lg type="stanza" n="1">
      <l n="1">alpha one</l><l n="2">alpha two</l>
    </lg>
    <lg type="stanza" n="2">
      <l n="1">beta one</l><l n="2">beta two</l>
    </lg>
  </div>
  <div type="textpart" subtype="canto" n="2">
    <lg type="argument"><l n="1">the argument line</l></lg>
    <lg type="stanza" n="1">
      <l n="1">gamma one</l><l n="2">gamma two</l>
    </lg>
  </div>
</body></text></TEI>'''


def _fixture(tmp_path):
    p = tmp_path / "of.xml"
    p.write_text(_TEI, encoding="utf-8")
    return str(p)


def test_stanza_intervals(tmp_path):
    path = _fixture(tmp_path)
    ivs = build_poetry_canonical_intervals({"e": {"path": path}})
    assert set(ivs) == {"1", "2"}
    assert [iv["label"] for iv in ivs["1"]] == ["1", "2"]          # bare -> poem-carded
    assert ivs["1"][0]["start_line"] == 1 and ivs["1"][0]["end_line"] == 2
    assert [iv["card_n"] for iv in ivs["2"]] == ["1"]


def test_poetry_cards_bins_by_stanza(tmp_path):
    path = _fixture(tmp_path)
    master = build_poetry_canonical_intervals({"e": {"path": path}})
    parsed = parse_poetry_cards_tei(path, master)

    assert "alpha one" in parsed["1"]["1"]["1"]
    assert "alpha two" in parsed["1"]["1"]["1"]
    assert "beta one" in parsed["1"]["2"]["1"]
    assert "alpha" not in parsed["1"]["2"]["1"]          # canto 1 stanza 2 is its own card
    # canto 2 is its own book; its stanza 1 must not collide with canto 1's
    assert "gamma one" in parsed["2"]["1"]["1"]
    assert "gamma" not in parsed["1"]["1"]["1"]
