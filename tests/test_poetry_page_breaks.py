from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


INTERVALS = {
    "1": [
        {
            "book": "1",
            "card_n": "1",
            "label": "1",
            "start_line": 1,
            "end_line": 2,
        }
    ]
}


def _parse(tmp_path, facs=""):
    source = tmp_path / "edition.xml"
    facs_attr = f' facs="{facs}"' if facs else ""
    source.write_text(
        f'''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="edition"><milestone unit="card" n="1"/>
        <l n="1">first line</l><pb n="12"{facs_attr}/><l n="2">second line</l>
        </div></body></text></TEI>''',
        encoding="utf-8",
    )
    return parse_poetry_cards_tei(str(source), INTERVALS)["1"]["1"]["1"]


def test_numbered_page_break_is_visible_without_facsimile(tmp_path):
    html = _parse(tmp_path)
    assert '<span class="tei-page-break" data-page="12"' in html
    assert "[p. 12]" in html
    assert html.index("first line") < html.index("[p. 12]") < html.index("second line")


def test_page_break_links_http_facsimile(tmp_path):
    html = _parse(tmp_path, "https://example.org/scan/12.jpg")
    assert '<a class="tei-page-break" data-page="12"' in html
    assert 'href="https://example.org/scan/12.jpg"' in html
    assert 'rel="noopener noreferrer"' in html


def test_page_break_does_not_link_unsafe_facsimile(tmp_path):
    html = _parse(tmp_path, "javascript:alert(1)")
    assert '<span class="tei-page-break" data-page="12"' in html
    assert "href=" not in html


def test_cast_list_is_metadata_not_running_text(tmp_path):
    source = tmp_path / "edition.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div type="edition"><castList><castItem><role xml:id="athena">Athena</role>
        <roleDesc>goddess</roleDesc></castItem></castList>
        <milestone unit="card" n="1"/><sp who="#athena"><speaker>Athena</speaker>
        <l n="1">spoken verse</l></sp></div></body></text></TEI>''',
        encoding="utf-8",
    )
    html = parse_poetry_cards_tei(str(source), INTERVALS)["1"]["1"]["1"]
    assert "spoken verse" in html
    assert "goddess" not in html
