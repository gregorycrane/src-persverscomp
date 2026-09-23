from pipeline.treebank.conllu import parse_conllu_treebank


def _parse(tmp_path, misc):
    source = tmp_path / "beowulf.conllu"
    source.write_text(
        "# sent_id = beowulf.00002\n"
        f"1\thronrāde\thron-rad\tNOUN\tf\tCase=Acc\t0\troot\t_\tRef=4-11|{misc}\n",
        encoding="utf-8",
    )
    sentences, _ = parse_conllu_treebank(
        str(source), "beowulf-test", "anon", "beowulf", has_books=False
    )
    return sentences[0]["tokens"][0]["gloss"]


def test_brunetti_dictionary_gloss_is_used_as_fallback(tmp_path):
    assert _parse(tmp_path, "BrunettiGloss=whale-road") == "whale-road"


def test_contextual_gloss_takes_precedence_over_brunetti_gloss(tmp_path):
    assert (
        _parse(tmp_path, "BrunettiGloss=hear|gloss=have-heard")
        == "have-heard"
    )
