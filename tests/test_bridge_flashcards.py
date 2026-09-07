import json
from pathlib import Path

from lxml import etree

from pipeline.bridge.flashcards import _cloze_line, build_cards


def test_cloze_preserves_context_and_blanks_only_selected_segment():
    line = etree.fromstring(
        b'<l xmlns="http://www.tei-c.org/ns/1.0" n="1">'
        b'<seg xml:id="a">Sing</seg>, <seg xml:id="b">goddess</seg>.</l>'
    )
    assert _cloze_line(line, ["a"]) == "[…], goddess."


def test_flashcard_identity_comes_from_alignment_metadata(tmp_path):
    tei = tmp_path / "bridge.xml"
    tei.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><l n="1">'
        '<seg xml:id="target">Dawn</seg></l></body></text></TEI>',
        encoding="utf-8",
    )
    alignment = tmp_path / "alignment.json"
    alignment.write_text(json.dumps({
        "alignment_meta": {
            "target_urn": "urn:cts:greekLit:tlg0012.tlg002.parrish2023-eng1",
            "flashcard_id_prefix": "parrish-odyssey5",
            "flashcard_title": "Odyssey Book 5 flashcards",
        },
        "segments": {"5.1-49": {"alignments": [{
            "tgt_tokens": ["Dawn"],
            "meta": {
                "target_ids": ["target"],
                "source_lines": ["5.1"],
                "tokens": [{"form": "Ἠώς", "stable_id": "token-1"}],
            },
        }]}},
    }), encoding="utf-8")

    result = build_cards(tei, alignment)

    assert result["title"] == "Odyssey Book 5 flashcards"
    assert result["source_translation"].endswith("parrish2023-eng1")
    assert result["cards"][0]["id"] == "parrish-odyssey5-00001"
    assert result["cards"][0]["work"] == "urn:cts:greekLit:tlg0012.tlg002"
