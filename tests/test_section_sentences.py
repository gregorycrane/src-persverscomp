from pipeline.parsers.section_sentences import parse_section_sentences_tei


def test_section_sentences_preserves_card_and_sentence_refs(tmp_path):
    source = tmp_path / "crito.xml"
    source.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
        '<div type="translation"><div type="textpart" subtype="section" n="43a">'
        '<p n="1">First sentence.</p><p n="2">Second <hi>sentence</hi>.</p>'
        '</div></div></body></text></TEI>',
        encoding="utf-8",
    )

    parsed = parse_section_sentences_tei(str(source))

    assert list(parsed) == ["1"]
    assert list(parsed["1"]) == ["43a"]
    assert parsed["1"]["43a"] == {
        "1": "First sentence.",
        "2": 'Second <span class="render-italic">sentence</span>.',
    }
