import json
import sqlite3
from pathlib import Path

from pipeline.core.storage import init_storage_engine
from pipeline import experimental_collections
from pipeline.experimental_collections import publish


def test_publish_recovers_fragments_and_claudel(tmp_path):
    site = tmp_path / "site"
    catalog = {"works": {}}
    for work in ("tlg005", "tlg006", "tlg007"):
        folder = site / "data" / "tlg0085" / work
        folder.mkdir(parents=True)
        db_name = f"tlg0085.{work}.part1.db"
        init_storage_engine(folder / db_name).close()
        catalog["works"][f"tlg0085.{work}"] = {
            "textgroup": "tlg0085", "work": work, "title": work,
            "parts": [{"part": 1, "file": db_name, "books": [],
                       "chapters": [], "bytes": 0}],
            "versions": [],
        }
    (site / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    result = publish(site)

    rebuilt = json.loads((site / "catalog.json").read_text(encoding="utf-8"))
    fragments = {k: v for k, v in rebuilt["works"].items()
                 if v.get("fragmentary") and v.get("textgroup") == "tlg0085"}
    sophocles = {k: v for k, v in rebuilt["works"].items()
                 if v.get("fragmentary") and v.get("textgroup") == "tlg0011"}
    assert result == {"fragment_works": 71, "claudel_versions": 3}
    assert len(fragments) == 71
    assert len(sophocles) == 102
    assert sum(len(v["parts"][0]["chapters"]) for v in fragments.values()) == 466
    assert sum(len(v["parts"][0]["chapters"]) for v in sophocles.values()) == 1128
    assert (site / "fragment-collections.json").exists()

    assert "tlg0085.athamas" in fragments
    assert "tlg0085.frag_athamas" not in rebuilt["works"]
    assert rebuilt["works"]["tlg0085.fragmenta"]["fragment_corpus"] is True
    assert fragments["tlg0085.athamas"]["object_urn"] == "urn:cite2:perseus:fragmentaryplays.v1:athamas"
    assert fragments["tlg0085.athamas"]["versions"][0]["urn"] == "urn:cts:greekLit:tlg0085.fragmenta.nauck1889grc1"
    athamas = site / "data" / "tlg0085" / "athamas" / "tlg0085.athamas.part1.db"
    with sqlite3.connect(athamas) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM alignment_grid").fetchone()[0] == 4
        assert "τὸν μὲν τρίπους" in conn.execute(
            "SELECT content_html FROM text_segments ORDER BY passage_urn LIMIT 1"
        ).fetchone()[0]

    for work, short_id, count in (
        ("tlg005", "claudel1896-fra1", 99),
        ("tlg006", "claudel1920-fra1", 87),
        ("tlg007", "claudel1920-fra1", 72),
    ):
        db = site / "data" / "tlg0085" / work / f"tlg0085.{work}.part1.db"
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT count(*) FROM text_segments WHERE version_short_id=?", (short_id,)
            ).fetchone()[0] == count


def test_fragmentary_plays_are_registered_as_stable_works():
    registry = json.loads((Path(__file__).parents[1] / "work_registry.json").read_text())
    athamas = registry["tlg0085.athamas"]
    assert athamas["fragmentary"] is True
    assert "nauck1889grc1" in athamas["fragment_editions"]
    assert "tlg0085.frag_athamas" not in registry


def test_one_fragmentary_play_accepts_multiple_editorial_versions(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    source = {
        "schema_version": 4,
        "versions": [
            {"short_id": "editorA-grc1", "edition_urn": "urn:cts:greekLit:tlg0085.fragmenta.editorA-grc1", "label": "Editor A"},
            {"short_id": "editorB-grc1", "edition_urn": "urn:cts:greekLit:tlg0085.fragmenta.editorB-grc1", "label": "Editor B"},
        ],
        "fragments": [
            {"number": "1", "edition": "editorA-grc1", "source_fragment_urn": "urn:cts:greekLit:tlg0085.fragmenta.editorA-grc1:1", "same_as": [], "lines": [{"ref": "1", "text": "Α"}], "context": ""},
            {"number": "1", "edition": "editorB-grc1", "source_fragment_urn": "urn:cts:greekLit:tlg0085.fragmenta.editorB-grc1:1", "same_as": ["urn:cts:greekLit:tlg0085.fragmenta.editorA-grc1:1"], "lines": [{"ref": "1", "text": "Β"}], "context": ""},
        ],
        "works": {"aeschylus-athamas": {
            "id": "aeschylus-athamas", "work": "athamas", "title": "Athamas",
            "object_urn": "urn:cite2:perseus:fragmentaryplays.v1:athamas",
        }},
        "attributions": [
            {"id": "a-athamas", "urn": "urn:cite2:perseus:fragmentattributions.v1:a-athamas", "resp": "Editor A", "edition": "editorA-grc1", "play_urn": "urn:cite2:perseus:fragmentaryplays.v1:athamas", "corresp": ["urn:cts:greekLit:tlg0085.fragmenta.editorA-grc1:1"]},
            {"id": "b-athamas", "urn": "urn:cite2:perseus:fragmentattributions.v1:b-athamas", "resp": "Editor B", "edition": "editorB-grc1", "play_urn": "urn:cite2:perseus:fragmentaryplays.v1:athamas", "corresp": ["urn:cts:greekLit:tlg0085.fragmenta.editorB-grc1:1"]},
        ],
    }
    source_path = tmp_path / "fragments.json"
    source_path.write_text(json.dumps(source))
    monkeypatch.setattr(experimental_collections, "FRAGMENTS_PATH", source_path)
    catalog = {"works": {}}
    assert experimental_collections._publish_fragments(site, catalog) == 1
    db = site / "data/tlg0085/athamas/tlg0085.athamas.part1.db"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM text_units").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM text_segments").fetchone()[0] == 2
    assert len(catalog["works"]["tlg0085.athamas"]["versions"]) == 2
