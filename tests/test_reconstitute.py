import sqlite3

from pipeline.build_all import _ensure_monolith
from pipeline.core.storage import init_storage_engine
from pipeline.reconstitute import reconstitute_monolith


def _write_part(path, section):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_storage_engine(path)
    conn.execute(
        "INSERT INTO text_units VALUES (?,?,?,?,?,?,?,?)",
        ("tlg9999_tlg001_ed1", "urn:cts:greekLit:tlg9999.tlg001.ed1",
         "Test edition", "greek-text", "tlg9999", "tlg001", "ed1", "poetry_cards"),
    )
    urn = f"urn:cts:greekLit:tlg9999.tlg001:{section}"
    conn.execute(
        "INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
        (urn, "tlg9999", "tlg001", None, section, "1", None, None, int(section)),
    )
    conn.execute("INSERT INTO text_segments VALUES (?,?,?)", (urn, "ed1", section))
    # Wholesale tables appear identically in every part of a work.
    conn.execute(
        "INSERT INTO token_alignments "
        "(textgroup,work,pair_id,src_version,tgt_version,segment,src_indices,"
        "tgt_indices,src_tokens,tgt_tokens,score,meta_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("tlg9999", "tlg001", "a--b", "a", "b", "1", "[0]", "[0]",
         "[]", "[]", 1.0, "{}"),
    )
    conn.commit()
    conn.close()


def test_reconstitute_coalesces_metadata_and_wholesale_rows(tmp_path):
    shard_root = tmp_path / "site" / "data"
    work_dir = shard_root / "tlg9999" / "tlg001"
    _write_part(work_dir / "tlg9999.tlg001.part1.db", "1")
    _write_part(work_dir / "tlg9999.tlg001.part2.db", "2")
    first = sqlite3.connect(str(work_dir / "tlg9999.tlg001.part1.db"))
    first.execute("""CREATE TABLE place_references (
        textgroup TEXT NOT NULL, work TEXT NOT NULL, book TEXT,
        chapter TEXT NOT NULL, mention_type TEXT, mention_name TEXT,
        place_id TEXT, place_name TEXT, lat REAL, lon REAL, feature_type TEXT)""")
    first.execute(
        "INSERT INTO place_references VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("tlg9999", "tlg001", None, "1", "place", "Athens", "579885",
         "Athens", 37.98, 23.73, "settlement"),
    )
    first.execute("""CREATE TABLE edition_line_alignments (
        id INTEGER PRIMARY KEY, textgroup TEXT NOT NULL, work TEXT NOT NULL,
        pair_id TEXT NOT NULL, base_version TEXT NOT NULL,
        target_version TEXT NOT NULL, seq INTEGER NOT NULL,
        base_lines TEXT NOT NULL, target_lines TEXT NOT NULL,
        type TEXT NOT NULL, score REAL, review INTEGER NOT NULL DEFAULT 0)""")
    first.execute(
        "INSERT INTO edition_line_alignments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (1, "tlg9999", "tlg001", "a--b", "a", "b", 0, '["1"]', '["1"]',
         "1-1", 1.0, 0),
    )
    first.commit()
    first.close()

    out = tmp_path / "monolith.db"
    conn = reconstitute_monolith(out, shard_root)
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM text_units").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM alignment_grid").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM token_alignments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM place_references").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM edition_line_alignments").fetchone()[0] == 1
    conn.close()


def test_ensure_monolith_recovers_a_malformed_build_database(tmp_path):
    shard_root = tmp_path / "site" / "data"
    _write_part(
        shard_root / "tlg9999" / "tlg001" / "tlg9999.tlg001.part1.db", "1"
    )
    monolith = tmp_path / "corpus_alignment_grid.db"
    monolith.write_bytes(b"this is not a sqlite database")

    _ensure_monolith(monolith, shard_root)

    conn = sqlite3.connect(str(monolith))
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM text_units").fetchone()[0] == 1
    conn.close()
    assert list(tmp_path.glob("corpus_alignment_grid.malformed-*.db"))
