"""Monolith schema + canonical-id generation. Relocated from Cell 4.

NATURAL_KEY_TABLES / SURROGATE_ID_TABLES classify every table for
reconstitute.py: natural-key tables merge from shards with
`INSERT OR IGNORE SELECT *` (their primary key is globally unique, while
work-level metadata is repeated in every part of a multi-part shard);
surrogate-id tables use an AUTOINCREMENT `id` that only guarantees
uniqueness within a single build process, so reconstitute.py must drop the
old id and let SQLite reassign fresh ones on merge. treebank_tokens is
intentionally excluded from both -- it's a derived search index (see
treebank/flatten.py) and gets rebuilt from treebank_sentences after any
merge rather than merged directly, since its sentence_id values only make
sense relative to the ids assigned in the SAME build.
"""
import re
import sqlite3
from pathlib import Path

TEXTGROUP_NAMESPACE = {
    "tlg": "greekLit", "phi": "latinLit",
    "anon": "angLit",
    "ferdowsi": "persLit", "boeckh": "latinLit",
    "heike": "japaneseLit", "ariosto": "itaLit",
}

def init_storage_engine(db_path):
    if db_path.exists():
        db_path.unlink()
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA page_size = 4096;")
    cursor.execute("PRAGMA journal_mode = OFF;")
    cursor.execute("PRAGMA synchronous = OFF;")
    
    cursor.execute("""
        CREATE TABLE text_units (
            canonical_id TEXT PRIMARY KEY,
            urn TEXT NOT NULL,
            label TEXT NOT NULL,
            text_class TEXT NOT NULL,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            short_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            source_version TEXT,
            source_certainty TEXT,
            source_note TEXT,
            translation_of TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE work_book_metadata (
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            book TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            PRIMARY KEY (textgroup, work, book)
        );
    """)
    # ^ Auto-derived per-book display title/summary, sourced straight from a
    # parser that reads them off the TEI itself (currently only
    # parse_speech_collection_tei, which reads an oration/speech div's own
    # first/second <head>) rather than being hand-copied into
    # work_registry.json. This is the fix for the old "second <head> never
    # shown" bug: that bug was never really a parsing problem -- the parser
    # always extracted both heads correctly -- it was that the extracted
    # values were discarded (assigned to `_book_titles_this_edition` /
    # `_book_summaries_this_edition`, underscore-prefixed on purpose) and
    # catalog.json's book_titles/book_summaries came exclusively from a
    # manually-maintained copy in work_registry.json, which silently drifts
    # out of sync whenever the source XML's <head> text changes. Populating
    # this table here means every rebuild re-derives titles/summaries
    # straight from the XML -- no manual copy step left to go stale. See the
    # merge into catalog.json in the sharding cell, which prefers this table
    # over work_registry.json's book_titles/book_summaries and only falls
    # back to the registry for work types this table doesn't cover.
    cursor.execute("""
        CREATE TABLE alignment_grid (
            passage_urn TEXT PRIMARY KEY,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            book TEXT,
            chapter TEXT NOT NULL,
            section TEXT NOT NULL,
            prev_urn TEXT,
            next_urn TEXT,
            sort_order INTEGER NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE text_segments (
            passage_urn TEXT,
            version_short_id TEXT,
            content_html TEXT NOT NULL,
            PRIMARY KEY (passage_urn, version_short_id),
            FOREIGN KEY (passage_urn) REFERENCES alignment_grid(passage_urn)
        );
    """)
    cursor.execute("""
        CREATE TABLE edition_chapter_order (
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            version_short_id TEXT NOT NULL,
            book TEXT,
            chapter TEXT NOT NULL,
            local_sort_index INTEGER NOT NULL,
            PRIMARY KEY (textgroup, work, version_short_id, book, chapter)
        );
    """)
    cursor.execute("""
        CREATE TABLE treebank_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            version_short_id TEXT NOT NULL,
            subdoc TEXT NOT NULL,
            chapter TEXT NOT NULL,
            section TEXT NOT NULL,
            book TEXT,
            sentence_json TEXT NOT NULL,
            prose_translation TEXT,
            literal_translation TEXT,
            transliteration TEXT,
            credits_json TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE treebank_doc_credits (
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            version_short_id TEXT NOT NULL,
            source_repo TEXT,
            credits_json TEXT,
            PRIMARY KEY (textgroup, work, version_short_id)
        );
    """)
    cursor.execute("""
        CREATE TABLE treebank_speakers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            subdoc TEXT NOT NULL,
            speaker TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_alignments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            textgroup    TEXT NOT NULL,
            work         TEXT NOT NULL,
            pair_id      TEXT NOT NULL,
            src_version  TEXT NOT NULL,
            tgt_version  TEXT NOT NULL,
            segment      TEXT NOT NULL,
            src_indices  TEXT NOT NULL,
            tgt_indices  TEXT NOT NULL,
            src_tokens   TEXT NOT NULL,
            tgt_tokens   TEXT NOT NULL,
            score        REAL NOT NULL,
            meta_json    TEXT NOT NULL DEFAULT '{}'
        );
    """)
    # Forward-compatible migration for persistent databases created before
    # authored bridge alignments began carrying morphology and stable IDs.
    _aln_columns = {row[1] for row in cursor.execute("PRAGMA table_info(token_alignments)")}
    if "meta_json" not in _aln_columns:
        cursor.execute("ALTER TABLE token_alignments ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'")
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS metrical_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            version_short_id TEXT NOT NULL,
            line_ref TEXT NOT NULL,
            book TEXT NOT NULL,
            chapter TEXT NOT NULL,
            line_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_metrical_chapter
            ON metrical_lines(textgroup, work, version_short_id, book, chapter);
    ''')
    
    cursor.execute("CREATE INDEX idx_grid_lookup ON alignment_grid(textgroup, work, book, chapter);")
    cursor.execute("CREATE INDEX idx_segments_lookup ON text_segments(passage_urn);")
    cursor.execute("CREATE INDEX idx_edition_order_lookup ON edition_chapter_order(textgroup, work, version_short_id, book);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_align_lookup ON token_alignments(textgroup, work, pair_id, segment);")
    cursor.execute("CREATE INDEX idx_tb_lookup ON treebank_sentences(textgroup, work, version_short_id, chapter);")
    cursor.execute("CREATE INDEX idx_tb_subdoc ON treebank_sentences(textgroup, work, subdoc);")
    
    conn.commit()
    return conn

def generate_canonical_id(work_key, label_string, doc_type="edition"):
    prefix = work_key.replace('.', '_')
    match = re.search(r'\((.*?)\)', label_string)
    if match:
        content = match.group(1)
        parts = content.split(',')
        editor = parts[0].strip()
        year = parts[1].strip() if len(parts) > 1 else ""
        editor_last = editor.split()[-1].lower().replace('.', '')
        year_clean = re.sub(r'\D', '', year)
        base_id = f"{prefix}_{editor_last}_{year_clean}"
    else:
        fallback_suffix = re.sub(r'\W+', '_', label_string).lower()
        base_id = f"{prefix}_{fallback_suffix}"

    if doc_type != "edition":
        base_id = f"{base_id}_{doc_type}"
    return base_id

# -- Table classification for reconstitute.py (see module docstring) --------
NATURAL_KEY_TABLES = {
    "text_units", "work_book_metadata", "alignment_grid",
    "text_segments", "edition_chapter_order", "treebank_doc_credits",
}
SURROGATE_ID_TABLES = {
    "treebank_sentences", "treebank_speakers", "token_alignments", "metrical_lines",
}
# Rebuilt from treebank_sentences after a merge -- never merged directly.
DERIVED_TABLES = {"treebank_tokens"}
