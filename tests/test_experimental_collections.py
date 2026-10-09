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
    assert result == {"fragment_works": 81, "fragment_authors": 55,
                      "claudel_versions": 3}
    assert len(fragments) == 82  # 81 work views plus the author-level corpus
    assert len(sophocles) == 119
    assert sum(len(v["parts"][0]["chapters"]) for v in fragments.values()) == 1404
    assert sum(len(v["parts"][0]["chapters"]) for v in sophocles.values()) == 3692
    assert (site / "fragment-collections.json").exists()
    assert (site / "tlg0085-fragment-concordance.json").exists()
    assert (site / "tlg0011-fragment-concordance.json").exists()
    concordance = json.loads(
        (site / "tlg0011-fragment-concordance.json").read_text(encoding="utf-8")
    )
    assert len(concordance["matches"]) == 1268
    aigeys_meta = rebuilt["works"]["tlg0011.aigeys"]
    assert [v["short_id"] for v in aigeys_meta["versions"]] == [
        "dindorf1893-grc1", "nauck1889grc1", "pearson1917-grc1"
    ]
    assert aigeys_meta["parts"][0]["chapters"][:2] == ["N18=P19", "N19=P20"]
    assert "N31=P34" in rebuilt["works"]["tlg0011.aichmalotides"]["parts"][0]["chapters"]
    with sqlite3.connect(site / "data/tlg0011/aigeys/tlg0011.aigeys.part1.db") as conn:
        rows = conn.execute(
            "SELECT version_short_id FROM text_segments "
            "WHERE passage_urn LIKE '%:N18-P19.1' ORDER BY version_short_id"
        ).fetchall()
        assert rows == [("nauck1889grc1",), ("pearson1917-grc1",)]
    assert "tlg0303.fragmenta" in rebuilt["works"]
    assert "tlg0303.aigyptioi" in rebuilt["works"]
    assert rebuilt["authors"]["tlg0303"] == "Phrynichus"
    assert rebuilt["works"]["tlg0331.iphigeneia"]["evidence_only"] is True
    assert rebuilt["works"]["tlg0331.iphigeneia"]["parts"][0]["chapters"] == []
    phrynichus = site / "data/tlg0303/fragmenta/tlg0303.fragmenta.part1.db"
    with sqlite3.connect(phrynichus) as conn:
        assert conn.execute("SELECT count(*) FROM alignment_grid").fetchone()[0] == 24
        assert "ΑΙΓΥΠΤΙΟΙ" in conn.execute(
            "SELECT content_html FROM text_segments ORDER BY passage_urn LIMIT 1"
        ).fetchone()[0]
    assert rebuilt["works"]["tlg0303.aigyptioi"]["object_urn"] == (
        "urn:cite2:perseus:fragmentaryplays.v1:tlg0303_aigyptioi"
    )

    assert "tlg0085.athamas" in fragments
    assert "tlg0085.frag_athamas" not in rebuilt["works"]
    assert rebuilt["works"]["tlg0085.fragmenta"]["fragment_corpus"] is True
    assert fragments["tlg0085.athamas"]["object_urn"] == "urn:cite2:perseus:fragmentaryplays.v1:athamas"
    assert [v["short_id"] for v in fragments["tlg0085.athamas"]["versions"]] == [
        "dindorf1893-grc1", "nauck1889grc1"
    ]
    assert fragments["tlg0085.athamas"]["parts"][0]["chapters"][:3] == [
        "D1=N1", "D2=N3", "D3=N4"
    ]
    athamas = site / "data" / "tlg0085" / "athamas" / "tlg0085.athamas.part1.db"
    with sqlite3.connect(athamas) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM alignment_grid").fetchone()[0] == 5
        fragment_html = conn.execute(
            "SELECT content_html FROM text_segments ORDER BY passage_urn LIMIT 1"
        ).fetchone()[0]
        assert "Τὸν μὲν τρίπους" in fragment_html
        assert '<l n="1" lang="grc">' in fragment_html
        assert 'class="fc-line"' not in fragment_html

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
    source = athamas["fragment_editions"]["nauck1889grc1"]
    assert source["path"].endswith("tlg0085.fragmenta.nauck1889grc1.xml")
    assert source["format"] == "tei_fragment_collection"
    assert registry["tlg0085.fragmenta"]["fragment_editions"]["nauck1889grc1"]["path"] == source["path"]
    assert registry["tlg0085.incertae"]["fragment_collection"] is True
    assert registry["tlg0085.dubia_spuria"]["fragment_collection"] is True
    assert "tlg0085.frag_athamas" not in registry
    assert set(registry["tlg0011.aigeys"]["fragment_editions"]) == {
        "dindorf1893-grc1", "nauck1889grc1", "pearson1917-grc1"
    }


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
