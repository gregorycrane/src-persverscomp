from pathlib import Path

from pipeline.core.canonical_intervals import build_poetry_canonical_intervals
from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><div type="edition">
    <div type="textpart" subtype="canto" n="1">
      <l n="1">one</l><l n="2">two</l>
    </div>
    <div type="textpart" subtype="canto" n="2">
      <l n="1">three</l><l n="2">four</l><l n="3">five</l>
    </div>
  </div></body></text>
</TEI>
"""


def test_plain_line_numbered_cantos_are_independent_books(tmp_path: Path):
    source = tmp_path / "inferno.xml"
    source.write_text(TEI, encoding="utf-8")
    config = {"edition": {"path": str(source), "parse_mode": "poetry_cards"}}

    intervals = build_poetry_canonical_intervals(config)
    assert list(intervals) == ["1", "2"]
    assert [item["label"] for item in intervals["1"]] == ["1-1", "2-2"]
    assert [item["label"] for item in intervals["2"]] == ["1-1", "2-2", "3-3"]

    parsed = parse_poetry_cards_tei(str(source), intervals)
    assert "one" in parsed["1"]["1-1"]["1"]
    assert "three" in parsed["2"]["1-1"]["1"]
    assert "five" in parsed["2"]["3-3"]["1"]
