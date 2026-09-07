import json

from pipeline.core.storage import init_storage_engine
from pipeline.sharding import split_corpus_by_work


def test_incremental_sharding_rewrites_only_requested_work(tmp_path):
    db = tmp_path / "monolith.db"
    conn = init_storage_engine(db)
    for work in ("tlg001", "tlg002"):
        urn = f"urn:cts:greekLit:tlg9999.{work}:1.1"
        conn.execute(
            "INSERT INTO text_units VALUES (?,?,?,?,?,?,?,?)",
            (f"tlg9999_{work}_ed1", f"urn:cts:greekLit:tlg9999.{work}.ed1",
             f"Edition {work}", "greek-text", "tlg9999", work, "ed1", "poetry_cards"))
        conn.execute(
            "INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
            (urn, "tlg9999", work, "1", "1", "1", None, None, 1))
        conn.execute("INSERT INTO text_segments VALUES (?,?,?)", (urn, "ed1", work))
    conn.commit(); conn.close()

    site = tmp_path / "site"
    untouched_dir = site / "data" / "tlg9999" / "tlg002"
    untouched_dir.mkdir(parents=True)
    untouched = untouched_dir / "tlg9999.tlg002.part1.db"
    sentinel = b"do not rewrite this unrelated shard"
    untouched.write_bytes(sentinel)
    (site / "catalog.json").write_text(json.dumps({
        "authors": {"legacy": "Legacy"},
        "works": {"tlg9999.tlg002": {"sentinel": True}},
    }), encoding="utf-8")

    split_corpus_by_work(db, site, only_work_keys=["tlg9999.tlg001"])

    assert untouched.read_bytes() == sentinel
    assert (site / "data" / "tlg9999" / "tlg001" / "tlg9999.tlg001.part1.db").exists()
    catalog = json.loads((site / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["works"]["tlg9999.tlg002"] == {"sentinel": True}
    assert "tlg9999.tlg001" in catalog["works"]
