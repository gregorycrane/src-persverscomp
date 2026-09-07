"""reconstitute.py's merge logic depends on NATURAL_KEY_TABLES /
SURROGATE_ID_TABLES / DERIVED_TABLES exactly matching what
init_storage_engine actually creates -- if a table gets added to the
schema later and nobody updates the classification, reconstitute.py will
silently skip it during a monolith rebuild-from-shards. This test is the
tripwire for that.
"""
import sqlite3
import tempfile
from pathlib import Path

from pipeline.core.storage import (
    init_storage_engine, NATURAL_KEY_TABLES, SURROGATE_ID_TABLES, DERIVED_TABLES,
)


def test_every_created_table_is_classified():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "test.db"
        conn = init_storage_engine(db_path)
        created = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
    # sqlite_sequence is an internal bookkeeping table SQLite creates
    # automatically for any AUTOINCREMENT column -- not part of our schema.
    created.discard("sqlite_sequence")

    classified = NATURAL_KEY_TABLES | SURROGATE_ID_TABLES | DERIVED_TABLES
    # treebank_tokens is created by flatten.py, not init_storage_engine --
    # it's fine for it to be classified (DERIVED_TABLES) without being
    # among the tables init_storage_engine itself creates.
    unclassified = created - classified
    assert not unclassified, f"tables created but not classified: {unclassified}"


def test_natural_and_surrogate_dont_overlap():
    assert not (NATURAL_KEY_TABLES & SURROGATE_ID_TABLES)
