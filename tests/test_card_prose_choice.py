from pipeline.parsers.card_prose import parse_card_prose_tei


def test_card_prose_choice_displays_only_expansion(tmp_path):
    source = tmp_path / "translation.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="translation"><milestone unit="card" n="1"/>
        <p>amplúſ<choice><abbr>q;</abbr><expan>que</expan></choice></p>
        </div></body></text></TEI>''',
        encoding="utf-8",
    )
    intervals = {"1": [{"book": "1", "card_n": "1", "label": "1", "start_line": 1, "end_line": 1}]}

    parsed = parse_card_prose_tei(str(source), intervals)
    html = parsed["1"]["1"]["1"]

    assert '>que</span>' in html
    assert 'data-original="q;"' in html
    assert 'amplúſq;que' not in html
