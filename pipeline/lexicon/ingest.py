"""Lexicon ingestion driver. Relocated from Cell 12's driver tail.

Unlike the corpus works, this was ALREADY lexicon_id-scoped with
delete-then-insert per lexicon (LEXICON_REGISTRY is its own registry, not
keyed off WORK_REGISTRY) -- the only change here is accepting an optional
lexicon_ids filter instead of always looping over every lexicon.
"""
from pathlib import Path
from pipeline.lexicon.parsers import LEXICON_REGISTRY, LEXICON_FORMAT_PARSERS


def ensure_lexicon_schema(conn):
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS lexicon_meta (
            lexicon_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT,
            citation TEXT,
            entry_kind TEXT NOT NULL,
            shard_file TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lexicon_scope (
            lexicon_id TEXT NOT NULL,
            textgroup TEXT NOT NULL,
            PRIMARY KEY (lexicon_id, textgroup)
        );
        CREATE TABLE IF NOT EXISTS lexicon_entries (
            lexicon_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            headword_display TEXT NOT NULL,
            headword_translit TEXT,
            headword_key TEXT NOT NULL,
            sort_key TEXT NOT NULL,
            entry_html TEXT NOT NULL,
            PRIMARY KEY (lexicon_id, entry_id)
        );
        CREATE INDEX IF NOT EXISTS idx_lex_headword ON lexicon_entries(lexicon_id, headword_key);
        CREATE TABLE IF NOT EXISTS lexicon_aliases (
            lexicon_id TEXT NOT NULL,
            alias_key TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            PRIMARY KEY (lexicon_id, alias_key, entry_id)
        );
        CREATE INDEX IF NOT EXISTS idx_lex_alias ON lexicon_aliases(lexicon_id, alias_key);
        CREATE TABLE IF NOT EXISTS lexicon_citations (
            lexicon_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            textgroup TEXT,
            work TEXT,
            ref TEXT,
            urn TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_lex_cit_urn ON lexicon_citations(urn);
    """)

    # Migration guard: CREATE TABLE IF NOT EXISTS is a no-op against a table
    # that already exists from an earlier run of this cell (e.g. before Pizzi
    # was added) -- it won't retroactively add headword_translit. Add it here
    # if missing, so re-running this cell on an older monolith doesn't break.
    _existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(lexicon_entries)").fetchall()]
    if "headword_translit" not in _existing_cols:
        cur.execute("ALTER TABLE lexicon_entries ADD COLUMN headword_translit TEXT")
        print("  (migrated lexicon_entries: added headword_translit column)")
    conn.commit()


def ingest_lexica(conn, lexicon_ids=None):
    ensure_lexicon_schema(conn)
    cur = conn.cursor()
    target_ids = lexicon_ids or list(LEXICON_REGISTRY.keys())
    PARSERS = LEXICON_FORMAT_PARSERS
    for lexicon_id in target_ids:
        cfg = LEXICON_REGISTRY[lexicon_id]
        if not Path(cfg["path"]).exists():
            print(f"  ! skipping {lexicon_id}: file not found at {cfg['path']}")
            continue
    
        print(f"Ingesting lexicon: {lexicon_id} ({cfg['format']})...")
        parser = PARSERS[cfg["format"]]
        entries, aliases, citations = parser(cfg["path"], lexicon_id)
    
        cur.execute("DELETE FROM lexicon_meta WHERE lexicon_id=?", (lexicon_id,))
        cur.execute("DELETE FROM lexicon_scope WHERE lexicon_id=?", (lexicon_id,))
        cur.execute("DELETE FROM lexicon_entries WHERE lexicon_id=?", (lexicon_id,))
        cur.execute("DELETE FROM lexicon_aliases WHERE lexicon_id=?", (lexicon_id,))
        cur.execute("DELETE FROM lexicon_citations WHERE lexicon_id=?", (lexicon_id,))
    
        cur.execute(
            "INSERT INTO lexicon_meta (lexicon_id, title, author, citation, entry_kind, shard_file) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lexicon_id, cfg["title"], cfg["author"], cfg["citation"], cfg["entry_kind"], cfg["shard_file"]),
        )
        cur.executemany(
            "INSERT INTO lexicon_scope (lexicon_id, textgroup) VALUES (?, ?)",
            [(lexicon_id, tg) for tg in cfg["textgroups"]],
        )
        cur.executemany(
            "INSERT INTO lexicon_entries (lexicon_id, entry_id, headword_display, headword_translit, headword_key, sort_key, entry_html) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(lexicon_id, e["entry_id"], e["headword_display"], e.get("headword_translit"),
              e["headword_key"], e["sort_key"], e["entry_html"])
             for e in entries],
        )
        cur.executemany(
            "INSERT OR IGNORE INTO lexicon_aliases (lexicon_id, alias_key, entry_id) VALUES (?, ?, ?)",
            [(lexicon_id, a["alias_key"], a["entry_id"]) for a in aliases],
        )
        cur.executemany(
            "INSERT INTO lexicon_citations (lexicon_id, entry_id, textgroup, work, ref, urn) VALUES (?, ?, ?, ?, ?, ?)",
            [(lexicon_id, c["entry_id"], c["textgroup"], c["work"], c["ref"], c["urn"]) for c in citations],
        )
        conn.commit()
        print(f"  \u2713 {len(entries)} entries, {len(aliases)} aliases, {len(citations)} citations "
              f"\u2192 shard {cfg['shard_file']}")
    
    print("\nDone.")
    