from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


def test_standoff_footnote_is_attached_to_ref_and_not_dumped_at_end(tmp_path):
    source = tmp_path / "notes.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body><div type="translation">
          <sp><speaker>Pythia</speaker><l n="1">Earth<ref type="note" target="#n1">1</ref>.</l></sp>
          <div type="notes"><note xml:id="n1" n="1">The first seer.</note></div>
        </div></body></text></TEI>''',
        encoding="utf-8",
    )
    cards = parse_poetry_cards_tei(
        str(source), {None: [{"card_n": "1", "label": "1", "start_line": 1, "end_line": 1}]})
    html = cards[None]["1"]["1"]
    assert 'class="tei-ref tei-note-ref"' in html
    assert 'data-note="The first seer."' in html
    assert '<span class="note">' not in html


def test_app_wrapped_explanatory_note_is_attached_to_untyped_ref(tmp_path):
    source = tmp_path / "potter-notes.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body><div type="translation">
          <l n="1">Rich gifts<ref target="#app-note-a">a</ref>, in honour of the day.</l>
        </div></body><back><div type="apparatus"><listApp>
          <app xml:id="app-note-a" loc="1"><note>The custom of making presents.</note></app>
        </listApp></div></back></text></TEI>''',
        encoding="utf-8",
    )
    cards = parse_poetry_cards_tei(
        str(source), {None: [{"card_n": "1", "label": "1", "start_line": 1, "end_line": 1}]})
    html = cards[None]["1"]["1"]
    assert 'class="tei-ref tei-note-ref"' in html
    assert 'data-note="The custom of making presents."' in html
    assert 'app-crit' not in html
