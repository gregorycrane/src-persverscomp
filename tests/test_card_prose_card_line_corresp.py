from pipeline.parsers.card_prose import parse_card_prose_tei


def test_single_book_card_line_corresp_routes_and_labels_each_card(tmp_path):
    source = tmp_path / "beowulf_translation.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="translation">
          <div type="textpart" subtype="card" n="1">
            <p corresp="urn:cts:angLit:anon.beowulf.perseus-ang1:1.1-1.3">First sentence.</p>
          </div>
          <div type="textpart" subtype="card" n="53">
            <p corresp="urn:cts:angLit:anon.beowulf.perseus-ang1:53.53-53.58">Second sentence.</p>
          </div>
        </div></body></text></TEI>''',
        encoding="utf-8",
    )
    intervals = {
        "1": [
            {"book": "1", "card_n": "1", "label": "1-52", "start_line": 1, "end_line": 52},
            {"book": "1", "card_n": "53", "label": "53-114", "start_line": 53, "end_line": 114},
        ]
    }

    parsed = parse_card_prose_tei(str(source), intervals)

    first = parsed["1"]["1-52"]["1"]
    second = parsed["1"]["53-114"]["1"]
    assert "[1-3]" in first and "First sentence." in first
    assert "[53-58]" in second and "Second sentence." in second
    assert "Second sentence." not in first
