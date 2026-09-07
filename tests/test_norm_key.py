from pipeline.treebank.norm_key import norm_key


def test_strips_greek_diacritics_and_folds_final_sigma():
    assert norm_key("λόγος") == norm_key("λογος")
    # norm_key folds ALL sigmas (including word-final ς) to medial σ, so the
    # normalized key ends in σ even though the real word ends in ς.
    assert norm_key("ἀγαθός") == "αγαθοσ"


def test_case_insensitive():
    assert norm_key("Odysseus") == norm_key("odysseus")


def test_none_passthrough():
    assert norm_key(None) is None
    assert norm_key("") is None
