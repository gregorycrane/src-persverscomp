from pathlib import Path

from pipeline.parsers.line_commentary import parse_line_commentary_tei


def test_standalone_appcrit_lemmas_are_highlighted(tmp_path: Path):
    source = tmp_path / "apparatus.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="apparatus"><div type="textpart" subtype="commline" n="12"
          corresp="urn:cts:greekLit:tlg0085.tlg003.hermann1852-grc2:12">
          <p><app><lem corresp="urn:cts:greekLit:tlg0085.tlg003.hermann1852-grc2:12">Κράτος Βία τε</lem></app>:
          Libri aliter legunt.</p>
        </div></div></body></text></TEI>""",
        encoding="utf-8",
    )
    intervals = {"1": [{"book": "1", "start_line": 1, "end_line": 20, "label": "1-20"}]}
    parsed = parse_line_commentary_tei(str(source), intervals)
    html = parsed["1"]["1-20"]["1"]
    assert '<span class="lemma">Κράτος Βία τε</span>' in html
    assert "Libri aliter legunt." in html
    assert html.count("Κράτος Βία τε") == 1


def test_appcrit_bins_by_reference_but_displays_both_lines(tmp_path: Path):
    source = tmp_path / "apparatus.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="apparatus"><div type="textpart" subtype="commline" n="1525"
          source="urn:cts:greekLit:tlg0085.tlg005.hermann1852-grc2:1525"
          corresp="urn:cts:greekLit:tlg0085.tlg005.perseus-grc2:1558">
          <p><app><lem>ἀχέων</lem></app> Ven. Explicant.</p>
        </div></div></body></text></TEI>""",
        encoding="utf-8",
    )
    intervals = {"1": [
        {"book": "1", "start_line": 1500, "end_line": 1549, "label": "1500-1549"},
        {"book": "1", "start_line": 1550, "end_line": 1599, "label": "1550-1599"},
    ]}
    parsed = parse_line_commentary_tei(
        str(source), intervals, lineno_sigil="H.", anchor_axis="corresp",
        reference_sigil="Smyth", show_reference_line=True,
    )
    assert "1500-1549" not in parsed["1"]
    html = parsed["1"]["1550-1599"]["1"]
    assert "H. 1525" in html
    assert "Smyth 1558" in html
    assert "ἀχέων" in html
