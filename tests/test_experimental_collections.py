import json
import sqlite3

from pipeline.core.storage import init_storage_engine
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
                 if v.get("experimental_fragment")}
    assert result == {"fragment_works": 71, "claudel_versions": 3}
    assert len(fragments) == 71
    assert sum(len(v["parts"][0]["chapters"]) for v in fragments.values()) == 466
    assert (site / "fragment-collections.json").exists()

    athamas = site / "data" / "tlg0085" / "frag_athamas" / "tlg0085.frag_athamas.part1.db"
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
