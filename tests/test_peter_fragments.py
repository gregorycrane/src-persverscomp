import json
from pathlib import Path

from pipeline.play_level_fragments import build


REPO = Path(__file__).resolve().parents[1]
DATA = Path("/Users/gcrane/github/grcnewfragments/data")


def test_peter_registry_has_both_volumes_and_resolvable_sources():
    registry = json.loads((REPO / "work_registry.json").read_text(encoding="utf-8"))
    records = {
        key: value for key, value in registry.items()
        if str(value.get("source_edition", "")).startswith("peter")
    }
    assert len(records) == 143
    assert {value["source_edition"] for value in records.values()} == {
        "peter1914-grc1", "peter1906-grc1",
    }
    assert {"tlg2542.hrr1e002", "tlg2165.hrr2e001", "tlg2122.hrr2e077"} <= set(records)
    for record in records.values():
        edition = record["fragment_editions"][record["source_edition"]]
        assert edition["format"] == "tei_fragment_work"
        assert edition["corresp_axis"] == "fragment"
        assert Path(edition["path"]).is_file()


def test_peter_work_builds_fragment_cards_with_page_provenance():
    model = build(
        DATA / "tlg2542", "tlg2542", "peter1914-grc1",
        "Quintus Fabius Pictor", "Peter HRR I", "Hermann Peter",
    )
    fragments = [item for item in model["fragments"] if item["play_work"] == "hrr1e002"]
    assert fragments
    assert fragments[0]["number"] == "1"
    assert fragments[0]["pages"]
