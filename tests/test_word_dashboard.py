from collections import Counter

from pipeline.word_dashboard import nfc, parse_misc, reliability_summary, top


def test_dashboard_normalizes_polytonic_greek_and_misc_keys():
    assert nfc("λο\u0301γος") == "λόγος"
    assert parse_misc("Ref=43b|gloss=spoken-account") == {
        "ref": "43b", "gloss": "spoken-account"
    }


def test_dashboard_top_is_json_ready():
    assert top(Counter({"λόγος": 3, "ἔργον": 1})) == [
        {"label": "λόγος", "count": 3},
        {"label": "ἔργον", "count": 1},
    ]


def test_reliability_compares_only_shared_works_and_rates():
    primary = {"id": "oga", "works": [
        {"id": "001", "tokens": 100, "hits": {"λόγος": 2}},
        {"id": "002", "tokens": 100, "hits": {"λόγος": 99}},
    ]}
    control = {"id": "glaux", "works": [
        {"id": "001", "tokens": 200, "hits": {"λόγος": 2}},
        {"id": "003", "tokens": 100, "hits": {"λόγος": 99}},
    ]}
    report = reliability_summary(primary, control)
    row = next(row for row in report["rows"] if row["lemma"] == "λόγος")
    assert report["shared_works"] == ["001"]
    assert row["primary_count"] == row["control_count"] == 2
    assert row["primary_rate"] == 200.0
    assert row["control_rate"] == 100.0
