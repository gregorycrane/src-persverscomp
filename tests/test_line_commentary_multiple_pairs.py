from pathlib import Path

from pipeline.parsers.line_commentary import parse_line_commentary_tei


def test_multiple_lemma_comment_pairs_render_without_gaps(tmp_path: Path):
    source = tmp_path / "commentary.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0">
          <text><body><div type="commentary">
            <div type="commline" n="398">
              <p>Preface
                <seg type="lemma" ana="#n1">γῆν καταφθατουμένη</seg>
                <seg type="comment" xml:id="n1">first explanation ending by translating</seg>
                <seg type="lemma" ana="#n2">καταφθατουμένη</seg>
                <seg type="comment" xml:id="n2">, <gloss>occupying</gloss>, hasting to
                  claim the land. <emph>Important distinction.</emph></seg>
              </p>
            </div>
          </div></body></text>
        </TEI>""",
        encoding="utf-8",
    )
    intervals = {
        "": [{"book": "", "label": "390-410", "start_line": 390, "end_line": 410}]
    }

    parsed = parse_line_commentary_tei(str(source), intervals)
    html = parsed[""]["390-410"]["1"]

    assert "Preface" in html
    assert html.count('class="lemma"') == 2
    assert "γῆν καταφθατουμένη" in html
    assert "first explanation ending by translating" in html
    assert "καταφθατουμένη" in html
    assert "occupying" in html
    assert "hasting to" in html
    assert "claim the land" in html
    assert '<span class="tei-gloss">occupying</span>' in html
    assert '<em class="tei-emph">Important distinction.</em>' in html
    assert html.index("first explanation") < html.index("occupying")
