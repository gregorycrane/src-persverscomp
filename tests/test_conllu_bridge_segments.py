from pathlib import Path

from pipeline.treebank.conllu import parse_conllu_treebank


def test_blank_between_sentence_metadata_and_tokens_is_not_data_loss(tmp_path: Path):
    source = tmp_path / "bridge.conllu"
    source.write_text(
        "# sent_id = 2274106a\n"
        "# text = ἣ ἔθηκε\n"
        "# literal_translation = It caused.\n"
        "\n"
        "8\tἣ\tὅς\tPRON\tp-s---fn-\tCase=Nom\t12\tnsubj\t_\tRef=1.2|gloss=who\n"
        "12\tἔθηκε\tτίθημι\tVERB\tv3saia---\tMood=Ind\t0\troot\t_\tRef=1.2|gloss=placed\n"
        "\n",
        encoding="utf-8",
    )

    sentences, _credits = parse_conllu_treebank(
        source, "daphne_perstb-grc1", "tlg0012", "tlg001", has_books=True
    )

    assert len(sentences) == 1
    assert [token["form"] for token in sentences[0]["tokens"]] == ["ἣ", "ἔθηκε"]
    assert sentences[0]["tokens"][1]["stable_id"] == (
        "urn:perseus:treebank:tlg0012.tlg001.daphne_perstb-grc1:2274106a.12"
    )
