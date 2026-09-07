"""Rebuild the monolith from the deployed shards alone, with no TEI/treebank
source files needed. NEW module -- didn't exist in the notebook.

Needed whenever DB_PATH is missing but site/data/**/*.db shards exist: a
fresh clone, or after cleanup.py ran. See core/storage.py's
NATURAL_KEY_TABLES / SURROGATE_ID_TABLES / DERIVED_TABLES docstring for why
the two table classes are merged differently, and why treebank_tokens is
excluded and rebuilt afterward instead.
"""
import sqlite3
from pathlib import Path

from pipeline.core.storage import init_storage_engine, NATURAL_KEY_TABLES, SURROGATE_ID_TABLES
from pipeline.treebank.flatten import flatten_treebank_tokens


def reconstitute_monolith(out_path, shard_root, glob_pattern="*/*/*.db"):
    """Build a fresh monolith at out_path by merging every shard under
    shard_root (default layout: shard_root/<textgroup>/<work>/<tg>.<wk>.db).

    Natural-key tables merge with a plain `INSERT SELECT *` -- their
    primary key is already globally unique per work. Surrogate-id tables
    (AUTOINCREMENT `id`) have the `id` column dropped and reassigned fresh
    on merge, ordered by the shard's own `id` so each work's relative
    sequence survives -- nothing downstream depends on the specific id
    VALUES, only on relative ordering within one work+version group (see
    index_builder.py's `ORDER BY ..., id` usage).

    treebank_tokens is deliberately NOT merged shard-by-shard (its
    sentence_id values only make sense relative to the ids assigned within
    a single build) -- it's rebuilt wholesale from the merged
    treebank_sentences afterward via flatten_treebank_tokens().
    """
    out_path = Path(out_path)
    shard_root = Path(shard_root)
    conn = init_storage_engine(out_path)

    shard_paths = sorted(shard_root.glob(glob_pattern))
    if not shard_paths:
        raise FileNotFoundError(f"No shards found under {shard_root} matching {glob_pattern}")

    n_merged = 0
    for shard_path in shard_paths:
        conn.execute("ATTACH DATABASE ? AS s", (str(shard_path),))
        try:
            existing = {r[0] for r in conn.execute(
                "SELECT name FROM s.sqlite_master WHERE type='table'"
            ).fetchall()}

            for t in sorted(NATURAL_KEY_TABLES & existing):
                conn.execute(f"INSERT INTO main.{t} SELECT * FROM s.{t}")

            for t in sorted(SURROGATE_ID_TABLES & existing):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] != "id"]
                col_list = ", ".join(cols)
                conn.execute(
                    f"INSERT INTO main.{t} ({col_list}) "
                    f"SELECT {col_list} FROM s.{t} ORDER BY id"
                )
            n_merged += 1
            conn.commit()  # DETACH requires no pending transaction on the attached db
        finally:
            conn.execute("DETACH DATABASE s")

    conn.commit()
    flatten_treebank_tokens(conn)
    conn.commit()
    print(f"Reconstituted monolith at {out_path} from {n_merged} shard(s).")
    return conn
