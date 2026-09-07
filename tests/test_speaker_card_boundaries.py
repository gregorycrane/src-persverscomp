from collections import OrderedDict

from pipeline.parsers.card_prose import parse_card_prose_tei
from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


MASTER_INTERVALS = OrderedDict({
    "1": [
        {"book": "1", "card_n": "1", "label": "1-2", "start_line": 1, "end_line": 2},
        {"book": "1", "card_n": "3", "label": "3-4", "start_line": 3, "end_line": 4},
    ]
})


def _write_tei(tmp_path, body):
    path = tmp_path / "speech-boundary.xml"
    path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        f'{body}'
        '</body></text></TEI>',
        encoding="utf-8",
    )
    return str(path)


def test_poetry_speaker_before_opening_milestone_joins_new_card(tmp_path):
    path = _write_tei(tmp_path, '''
      <div type="edition" subtype="book" n="1">
        <milestone unit="card" n="1"/>
        <sp><speaker>Chorus</speaker><l n="1">old card</l></sp>
        <sp><speaker>Iolaus</speaker><milestone unit="card" n="3"/>
          <l n="3">new card</l></sp>
      </div>
    ''')
    parsed = parse_poetry_cards_tei(path, MASTER_INTERVALS)
    old = parsed["1"]["1-2"]["1"]
    new = parsed["1"]["3-4"]["1"]

    assert "Chorus" in old
    assert "Iolaus" not in old
    assert "Iolaus" in new
    assert "new card" in new


def test_prose_speaker_before_opening_milestone_joins_new_card(tmp_path):
    path = _write_tei(tmp_path, '''
      <div type="translation" subtype="book" n="1">
        <milestone unit="card" n="1"/>
        <sp><speaker>Chorus</speaker><p>old card</p></sp>
        <sp><speaker>Iolaus</speaker><milestone unit="card" n="3"/>
          <p>new card</p></sp>
      </div>
    ''')
    parsed = parse_card_prose_tei(path, MASTER_INTERVALS)
    old = parsed["1"]["1-2"]["1"]
    new = parsed["1"]["3-4"]["1"]

    assert "Chorus" in old
    assert "Iolaus" not in old
    assert "Iolaus" in new
    assert "new card" in new
