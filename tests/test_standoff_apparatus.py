import re
from collections import OrderedDict

from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


MASTER = OrderedDict({
    "1": [
        {"book": "1", "card_n": "1", "label": "1-2", "start_line": 1, "end_line": 2},
        {"book": "1", "card_n": "3", "label": "3-4", "start_line": 3, "end_line": 4},
    ]
})


def _visible(html):
    return re.sub(r"<[^>]+>", "", html)


def test_standoff_app_wraps_existing_lemma_and_targeted_note_joins_line(tmp_path):
    path = tmp_path / "standoff.xml"
    path.write_text('''
      <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div type="edition">
        <milestone unit="card" n="1"/>
        <l n="1" xml:id="l.1" corresp="urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:1">ὅπως γένοιτο τῶνδ᾽ ἐμοὶ λυτήριος.</l>
        <l n="2" xml:id="l.2" corresp="urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:2">δεύτερος στίχος</l>
        <div type="commentary"><note target="#l.1">τὸ ἑξῆς, ἔλθοι.</note></div>
        <div type="apparatus"><app loc="1" corresp="#l.1"><lem>τῶνδ᾽ ἐμοὶ</lem><rdg wit="h">τῶνδέ μοι</rdg></app></div>
      </div></body></text></TEI>''', encoding="utf-8")

    html = parse_poetry_cards_tei(str(path), MASTER, lineno_sigil="Weck.")["1"]["1-2"]["1"]
    visible = _visible(html)

    assert "[1 Weck.]" in visible
    assert visible.count("τῶνδ᾽ ἐμοὶ") == 1
    assert "τῶνδέ μοι" not in visible
    assert 'class="app-crit"' in html
    assert 'data-app="τῶνδέ μοι (h)"' in html
    assert "1 → Smyth 1" in visible
    assert visible.count("τὸ ἑξῆς, ἔλθοι.") == 1


def test_ranged_note_only_app_gets_one_marker_per_covered_card(tmp_path):
    path = tmp_path / "range.xml"
    path.write_text('''
      <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div type="edition">
        <milestone unit="card" n="1"/>
        <l n="1" xml:id="l.1">one</l><l n="2" xml:id="l.2">two</l>
        <milestone unit="card" n="3"/>
        <l n="3" xml:id="l.3">three</l><l n="4" xml:id="l.4">four</l>
        <div type="apparatus"><app from="#l.1" to="#l.4"><note>whole passage transposed</note></app></div>
      </div></body></text></TEI>''', encoding="utf-8")

    parsed = parse_poetry_cards_tei(str(path), MASTER)
    first = parsed["1"]["1-2"]["1"]
    second = parsed["1"]["3-4"]["1"]

    assert first.count("app-crit-standoff") == 1
    assert second.count("app-crit-standoff") == 1
    assert "whole passage transposed" not in _visible(first)
    assert "whole passage transposed" not in _visible(second)


def test_unlocated_apparatus_is_preserved_once_at_end_without_false_line_link(tmp_path):
    path = tmp_path / "colophon.xml"
    path.write_text('''
      <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div type="edition">
        <milestone unit="card" n="1"/><l n="1" xml:id="l.1">one</l><l n="2" xml:id="l.2">two</l>
        <milestone unit="card" n="3"/><l n="3" xml:id="l.3">three</l><l n="4" xml:id="l.4">four</l>
        <div type="apparatus"><app><rdg wit="M">Subscriptum in M.</rdg></app></div>
      </div></body></text></TEI>''', encoding="utf-8")

    parsed = parse_poetry_cards_tei(str(path), MASTER)
    first = parsed["1"]["1-2"]["1"]
    last = parsed["1"]["3-4"]["1"]

    assert "Unlocated apparatus" not in first
    assert last.count("Unlocated apparatus") == 1
    assert "Subscriptum in M." not in _visible(last)
