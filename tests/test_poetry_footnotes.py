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


def test_card_milestone_prose_keeps_linked_buckley_note_payload(tmp_path):
    source = tmp_path / "buckley-prose-notes.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body><div type="translation"><sp><speaker>PRIESTESS</speaker><p>
          <milestone unit="card" n="34"/>Certainly dreadful things
          <ref n="180.3" target="#app-fn-180.3">3</ref> appear.
        </p></sp></div></body><back><div type="apparatus"><listApp>
          <app n="180.3" xml:id="app-fn-180.3"><note>The shrine was wreathed with garlands.</note></app>
        </listApp></div></back></text></TEI>''',
        encoding="utf-8",
    )
    cards = parse_poetry_cards_tei(
        str(source), {None: [{"card_n": "34", "label": "34", "start_line": 34, "end_line": 63}]})
    html = cards[None]["34"]["1"]
    assert 'class="tei-ref tei-note-ref"' in html
    assert 'data-note="The shrine was wreathed with garlands."' in html
    assert '>3</span>' in html


def test_buckley_prose_preserves_numbered_speaker_turns_as_blocks(tmp_path):
    source = tmp_path / "buckley-speakers.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body><div type="translation">
          <sp corresp="urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:198-200">
            <speaker>CHORUS</speaker><p><milestone unit="card" n="178"/>Royal Apollo, hear our reply.</p>
          </sp>
          <sp corresp="urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:201">
            <speaker>APOLLO</speaker><p>How now?</p>
          </sp>
        </div></body></text></TEI>''',
        encoding="utf-8",
    )
    cards = parse_poetry_cards_tei(
        str(source), {None: [{"card_n": "178", "label": "178-212", "start_line": 178, "end_line": 212}]})
    html = cards[None]["178-212"]["1"]
    assert html.count('class="speaker-attr pmv-speech-heading"') == 2
    assert '<span class="speech-line-range">198–200</span>' in html
    assert '<span class="speech-speaker-name">CHORUS</span>' in html
    assert '<span class="speech-line-range">201</span>' in html
    assert html.index("CHORUS") < html.index("Royal Apollo") < html.index("APOLLO")


def test_buckley_speaker_moves_with_card_milestone_nested_in_opening_paragraph(tmp_path):
    source = tmp_path / "buckley-card-boundary.xml"
    source.write_text(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0">
        <text><body><div type="translation">
          <sp corresp="urn:cts:x:198"><speaker>CHORUS</speaker><p><milestone unit="card" n="179"/>Old card.</p></sp>
          <sp corresp="urn:cts:x:213"><speaker>APOLLO</speaker><p><milestone unit="card" n="213"/>New card.</p></sp>
        </div></body></text></TEI>''', encoding="utf-8")
    cards = parse_poetry_cards_tei(str(source), {None: [
        {"card_n": "179", "label": "179-212", "start_line": 179, "end_line": 212},
        {"card_n": "213", "label": "213-253", "start_line": 213, "end_line": 253},
    ]})
    old_html = cards[None]["179-212"]["1"]
    new_html = cards[None]["213-253"]["1"]
    assert "CHORUS" in old_html and "APOLLO" not in old_html
    assert "APOLLO" in new_html and "New card." in new_html
