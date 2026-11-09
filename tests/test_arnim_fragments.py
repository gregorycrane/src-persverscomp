import json
from pathlib import Path

from pipeline.play_level_fragments import build


REPO = Path(__file__).resolve().parents[1]
DATA = Path("/Users/gcrane/github/grcnewfragments/data")


def test_arnim_registry_has_all_author_collections_and_resolvable_sources():
    registry = json.loads((REPO / "work_registry.json").read_text(encoding="utf-8"))
    records = {
        key: value for key, value in registry.items()
        if value.get("source_edition") == "arnim1903-grc1"
    }
    assert len(records) == 21
    assert {"tlg0635.svf001", "tlg1264.svf001", "svfincerti.svf001"} <= set(records)
    for record in records.values():
        edition = record["fragment_editions"]["arnim1903-grc1"]
        assert edition["format"] == "tei_fragment_work"
        assert edition["corresp_axis"] == "volume.fragment"
        assert Path(edition["path"]).is_file()


def test_nested_arnim_volumes_become_composite_fragment_cards():
    model = build(
        DATA / "tlg1264", "tlg1264", "arnim1903-grc1", "Chrysippus",
        "Arnim SVF", "Hans von Arnim",
    )
    fragments = model["fragments"]
    assert len(fragments) == 1881
    assert fragments[0]["number"] == "2.1"
    assert fragments[-1]["number"] == "3.777"
    assert {fragment["volume"] for fragment in fragments} == {"2", "3"}
    assert fragments[0]["source_fragment_urn"].endswith(":2.1")
    assert fragments[0]["citation_label"] == "SVF II 1"
    assert fragments[0]["pages"]
    assert model["attributions"][0]["play_urn"].endswith("tlg1264_svf001")
