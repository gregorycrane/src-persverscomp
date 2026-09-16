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

# These tables are copied wholesale into every numbered part of a split work
# by sharding.py.  They therefore belong in the monolith once per work, not
# once per part.  text_units is also wholesale, but its natural primary key is
# coalesced by INSERT OR IGNORE below.
_REPEATED_SURROGATE_TABLES = {
    "treebank_speakers", "token_alignments", "edition_line_alignments",
}
_OPTIONAL_NATURAL_TABLES = {"place_references"}
_OPTIONAL_SURROGATE_TABLES = {"edition_line_alignments"}


def reconstitute_monolith(out_path, shard_root, glob_pattern="*/*/*.db"):
    """Build a fresh monolith at out_path by merging every shard under
    shard_root (default layout: shard_root/<textgroup>/<work>/<tg>.<wk>.db).

Natural-key tables merge with `INSERT OR IGNORE SELECT *` -- their
primary key is already globally unique per work, while work metadata is
deliberately repeated in every part of a multi-part shard. Surrogate-id tables
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
    seen_work_dirs = set()
    for shard_path in shard_paths:
        work_dir = shard_path.parent.resolve()
        first_part_for_work = work_dir not in seen_work_dirs
        conn.execute("ATTACH DATABASE ? AS s", (str(shard_path),))
        try:
            existing = {r[0] for r in conn.execute(
                "SELECT name FROM s.sqlite_master WHERE type='table'"
            ).fetchall()}

            # Some annotation tables are created only when their ingest step
            # runs, so they are absent from the base storage schema.  Recover
            # their schema directly from the first shard that contains them.
            main_tables = {r[0] for r in conn.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table'"
            ).fetchall()}
            for t in sorted(((_OPTIONAL_NATURAL_TABLES | _OPTIONAL_SURROGATE_TABLES)
                             & existing) - main_tables):
                schema = conn.execute(
                    "SELECT sql FROM s.sqlite_master WHERE type='table' AND name=?", (t,)
                ).fetchone()
                if schema and schema[0]:
                    conn.execute(schema[0])
                    for (index_sql,) in conn.execute(
                        "SELECT sql FROM s.sqlite_master "
                        "WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (t,)
                    ).fetchall():
                        conn.execute(index_sql)

            for t in sorted((NATURAL_KEY_TABLES | _OPTIONAL_NATURAL_TABLES) & existing):
                # text_units (and potentially other work-level metadata) is
                # copied into every part of a split work.  Its natural key
                # makes those rows safe to coalesce here.  A plain INSERT
                # made reconstruction fail as soon as it reached part 2.
                conn.execute(f"INSERT OR IGNORE INTO main.{t} SELECT * FROM s.{t}")

            for t in sorted((SURROGATE_ID_TABLES | _OPTIONAL_SURROGATE_TABLES) & existing):
                if t in _REPEATED_SURROGATE_TABLES and not first_part_for_work:
                    continue
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] != "id"]
                col_list = ", ".join(cols)
                conn.execute(
                    f"INSERT INTO main.{t} ({col_list}) "
                    f"SELECT {col_list} FROM s.{t} ORDER BY id"
                )
            n_merged += 1
            conn.commit()  # DETACH requires no pending transaction on the attached db
            seen_work_dirs.add(work_dir)
        except Exception:
            # A failed INSERT leaves a transaction open, and SQLite refuses
            # DETACH while that transaction is active.  Roll it back so the
            # original error is preserved instead of being masked by
            # "database s is locked" from DETACH.
            conn.rollback()
            raise
        finally:
            conn.execute("DETACH DATABASE s")

    conn.commit()
    flatten_treebank_tokens(conn)
    conn.commit()
    print(f"Reconstituted monolith at {out_path} from {n_merged} shard(s).")
    return conn
