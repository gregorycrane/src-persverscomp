from pipeline.parsers.speech_collection import parse_speech_collection_tei


def test_heading_page_break_is_not_exposed_as_navigation_html(tmp_path):
    source = tmp_path / "speeches.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="edition"><div subtype="speech" n="1">
          <head><num><pb n="7"/>I.</num> Rede am <date when="1858-07-08">8. Juli 1858</date>.</head>
          <head>Zur Begrüßung.</head>
          <p n="1"><s n="1">Guten Tag.</s></p>
        </div></div>
        </body></text></TEI>""",
        encoding="utf-8",
    )

    data, titles, summaries = parse_speech_collection_tei(source, ("speech",))

    assert titles == {"1": "I. Rede am 8. Juli 1858."}
    assert summaries == {"1": "Zur Begrüßung."}
    assert "tei-page-break" not in titles["1"]
    assert "Guten Tag." in data["1"]["1"]["1"]
