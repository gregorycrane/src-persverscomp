from pipeline.ingest_work import missing_required_cards


INTERVALS = {
    "1": [
        {"label": "1-2"},
        {"label": "3-4"},
        {"label": "5-6"},
    ]
}


def test_required_card_coverage_accepts_complete_edition():
    parsed = {
        "1": {
            "1-2": {"1": "alpha"},
            "3-4": {"1": "beta"},
            "5-6": {"1": "gamma"},
        }
    }
    assert missing_required_cards(parsed, INTERVALS) == []


def test_required_card_coverage_reports_absent_and_empty_cards():
    parsed = {"1": {"1-2": {"1": "alpha"}, "3-4": {"1": "  "}}}
    assert missing_required_cards(parsed, INTERVALS) == [
        ("1", "3-4"),
        ("1", "5-6"),
    ]
