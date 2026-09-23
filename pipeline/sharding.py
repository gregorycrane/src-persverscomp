"""Shards the monolith into site/data/<textgroup>/<work>/<tg>.<wk>.db.
Relocated from Cell 9.
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from pipeline.registry import WORK_REGISTRY

PART_SIZE_CEILING_BYTES = 60 * 1024 * 1024

HARD_SIZE_CEILING_BYTES = 95 * 1024 * 1024

PARTITIONED_TABLES = ["alignment_grid", "text_segments", "treebank_sentences",
                       "treebank_tokens", "metrical_lines", "place_references",
                       "edition_chapter_order"]

WHOLESALE_TABLES = ["text_units", "treebank_speakers", "token_alignments",
                     "edition_line_alignments"]

ALL_TABLES = PARTITIONED_TABLES + WHOLESALE_TABLES

_HEAVY_COLS = {
    "treebank_sentences": ["sentence_json", "prose_translation",
                            "literal_translation", "transliteration", "credits_json"],
    "treebank_tokens": ["form", "lemma", "feats", "gloss", "translit", "ltranslit"],
    "metrical_lines": ["line_json"],
}


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _table_cols(src, table):
    return [c[1] for c in src.execute(f"PRAGMA table_info({table})").fetchall()]

def _book_lookup(src, tg, wk):
    """Returns (ordered_books, chapter_book, cs_book, ambiguous).
    `chapter_book` (chapter -> book) is ALWAYS built, even when ambiguous --
    it's a best-effort last-write-wins mapping in that case, but it must
    still exist for tables with no `section` column (metrical_lines) that
    have nothing else to look up by. `cs_book` ((chapter, section) -> book)
    is only built when needed (chapter turned out to be reused across more
    than one book), for tables that DO have a section column to disambiguate
    with; it's None when chapter alone was already unambiguous.

    BUG HISTORY: an earlier version returned *either* chapter_book *or*
    cs_book depending on ambiguity, never both. That silently dropped every
    metrical_lines row whenever a work's chapters were ambiguous, since
    metrical_lines deliberately avoids the (chapter, section) lookup (no
    section column) but was then handed nothing else to look up by."""
    rows = src.execute(
        "SELECT book, chapter, section FROM alignment_grid "
        "WHERE textgroup=? AND work=? ORDER BY sort_order", (tg, wk)).fetchall()

    ordered_books, seen = [], set()
    for book, chapter, section in rows:
        if book not in seen:
            seen.add(book)
            ordered_books.append(book)

    chapter_book, ambiguous = {}, False
    for book, chapter, section in rows:
        if chapter in chapter_book and chapter_book[chapter] != book:
            ambiguous = True
        chapter_book[chapter] = book  # last-write-wins; only exact if not ambiguous

    cs_book = {(chapter, section): book for book, chapter, section in rows} if ambiguous else None
    return ordered_books, chapter_book, cs_book, ambiguous

def _estimate_book_sizes(src, tg, wk, ordered_books, chapter_book, cs_book):
    """Rough per-book byte estimate from the heavy TEXT columns -- used only
    to decide where part boundaries fall, not an exact file-size prediction."""
    sizes = {b: 0 for b in ordered_books}
    sizes[None] = 0  # bucket for rows that couldn't be mapped to a book

    def bump(book, n):
        sizes[book] = sizes.get(book, 0) + (n or 0)

    for book, n in src.execute("""
        SELECT ag.book, SUM(LENGTH(ts.content_html))
        FROM text_segments ts JOIN alignment_grid ag ON ts.passage_urn = ag.passage_urn
        WHERE ag.textgroup=? AND ag.work=? GROUP BY ag.book""", (tg, wk)).fetchall():
        bump(book, n)

    for table, cols in _HEAVY_COLS.items():
        cols = [c for c in cols if c in _table_cols(src, table)]
        if not cols:
            continue
        len_expr = " + ".join(f"COALESCE(LENGTH({c}),0)" for c in cols)
        # Use (chapter, section) only for tables that actually HAVE a section
        # column and only when it's needed (cs_book is None otherwise) --
        # metrical_lines never qualifies (no section column), so it always
        # falls back to chapter_book, which is always populated.
        use_cs = cs_book is not None and "section" in _table_cols(src, table)
        key_cols = "chapter, section" if use_cs else "chapter"
        lookup = cs_book if use_cs else chapter_book
        for row in src.execute(
                f"SELECT {key_cols}, SUM({len_expr}) FROM {table} "
                f"WHERE textgroup=? AND work=? GROUP BY {key_cols}", (tg, wk)).fetchall():
            *key, n = row
            k = tuple(key) if use_cs else key[0]
            bump(lookup.get(k), n)

    return sizes

def _estimate_flat_chapter_sizes(src, tg, wk):
    """Fallback for works with no book divisions at all: same idea as
    _estimate_book_sizes, but keyed directly by chapter."""
    sizes = {}

    def bump(chapter, n):
        sizes[chapter] = sizes.get(chapter, 0) + (n or 0)

    for chapter, n in src.execute("""
        SELECT ag.chapter, SUM(LENGTH(ts.content_html))
        FROM text_segments ts JOIN alignment_grid ag ON ts.passage_urn = ag.passage_urn
        WHERE ag.textgroup=? AND ag.work=? GROUP BY ag.chapter""", (tg, wk)).fetchall():
        bump(chapter, n)

    for table, cols in _HEAVY_COLS.items():
        cols = [c for c in cols if c in _table_cols(src, table)]
        if not cols:
            continue
        len_expr = " + ".join(f"COALESCE(LENGTH({c}),0)" for c in cols)
        for chapter, n in src.execute(
                f"SELECT chapter, SUM({len_expr}) FROM {table} "
                f"WHERE textgroup=? AND work=? GROUP BY chapter", (tg, wk)).fetchall():
            bump(chapter, n)

    return sizes

def _bin_into_parts(ordered_keys, sizes, ceiling):
    """Greedily group ordered keys (books, or chapters for the no-book
    fallback) into contiguous parts, each capped at `ceiling` estimated
    bytes."""
    parts, current, current_size = [], [], 0
    for key in ordered_keys:
        k_size = sizes.get(key, 0)
        if current and current_size + k_size > ceiling:
            parts.append(current)
            current, current_size = [], 0
        current.append(key)
        current_size += k_size
    if current:
        parts.append(current)
    return [p for p in parts if p]

def split_corpus_by_work(monolith_path, out_root, only_work_keys=None):
    """Split the monolith into per-work, per-book-range shard parts.

    When ``only_work_keys`` is supplied, rewrite only those work directories
    and merge their refreshed metadata into the existing catalog.  A missing
    catalog automatically falls back to a full shard pass so a partial build
    can never publish an incomplete catalog.
    """
    monolith_path = Path(monolith_path)
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(monolith_path))
    src.row_factory = sqlite3.Row

    works = [dict(r) for r in src.execute(
        "SELECT DISTINCT textgroup, work FROM text_units ORDER BY textgroup, work")]
    all_works = works

    requested = set(only_work_keys or [])
    catalog_path = out_root / "catalog.json"
    incremental = bool(requested) and catalog_path.exists()
    if requested and not incremental:
        print("[shard] no existing catalog for incremental update; falling back to full sharding")
    if incremental:
        works = [w for w in works if f"{w['textgroup']}.{w['work']}" in requested]

    # ── Centralized author/work display names ──────────────────────────
    # Single source of truth for "Aeschylus" / "Agamemnon"-style display
    # names, written into catalog.json so every page (the main reader,
    # map.html, anything future) reads the same data instead of each
    # maintaining its own hardcoded copy. This used to live as two
    # separate hand-typed objects inside app.js itself (AUTHOR_NAMES +
    # WORK_TITLES) -- moved here so it's typed exactly once, in the one
    # place that already has to know about every work in WORK_REGISTRY.
    AUTHOR_NAMES = {
        "phi1348": "Suetonius",
        "phi0620": "Propertius",

        "ariosto": "Ludovico Ariosto",
        "boeckh1858": "August Boeckh",
        "ferdowsi": "Ferdowsi",
        "heike": "Heike Monogatari",
        "anon": "Beowulf Poet",

        "tlg0001": "Apollonius of Rhodes",
        "tlg0003": "Thucydides",
        "tlg0006": "Euripides",
        "tlg0011": "Sophocles",
        "tlg0012": "Homer",
        "tlg0019": "Aristophanes",
        "tlg0020": "Hesiod",
        "tlg0059": "Plato",
        "tlg0085": "Aeschylus",
        "tlg0525": "Pausanias",
        "tlg0527": "Septuaginta",
        "tlg0086": "Aristotle",
        "tlg2045": "Nonnus",
    }
    WORK_TITLES = {
        "phi1348.abo011": "Julius Caesar",
        "phi1348.abo012": "Augustus",
        "phi1348.abo013": "Tiberius",
        "phi1348.abo014": "Caligula",
        "phi1348.abo015": "Claudius",
        "phi1348.abo016": "Nero",
        "phi1348.abo017": "Galba",
        "phi1348.abo018": "Otho",
        "phi1348.abo019": "Vitellius",
        "phi1348.abo020": "Vespasian",
        "phi1348.abo021": "Titus",
        "phi1348.abo022": "Domitian",

        "phi0620.phi001": "Elegies",

        "ariosto.orlandofurioso": "Orlando Furioso",
        "boeckh1858.orationes": "Orationes",
        "ferdowsi.shahnameh": "Shahnameh",
        "heike.tokyo1933": "The Tale of the Heike",

        "tlg0001.tlg001": "Argonautica",
        "tlg0003.tlg001": "History",
        "tlg0059.tlg003": "Crito",
        "tlg0525.tlg001": "Description of Greece",
        "tlg0006.tlg001": "Cyclops",
        "tlg0006.tlg002": "Alcestis",
        "tlg0006.tlg003": "Medea",
        "tlg0006.tlg004": "Children of Heracles",
        "tlg0006.tlg005": "Hippolytus",
        "tlg0006.tlg006": "Andromache",
        "tlg0006.tlg007": "Hecuba",
        "tlg0006.tlg008": "Suppliants",
        "tlg0006.tlg009": "Heracles",
        "tlg0006.tlg010": "Ion",
        "tlg0006.tlg011": "Trojan Women",
        "tlg0006.tlg012": "Electra",
        "tlg0006.tlg013": "Iphigenia in Taurus",
        "tlg0006.tlg014": "Helen",
        "tlg0006.tlg014": "Helen",
        "tlg0006.tlg015": "Phoenician Women",
        "tlg0006.tlg016": "Orestes",
        "tlg0006.tlg017": "Bacchae",
        "tlg0006.tlg018": "Iphigenia at Aulis",
        "tlg0006.tlg019": "Rhesus",
        "tlg0011.tlg001": "Trachiniai",
        "tlg0011.tlg002": "Antigone",
        "tlg0011.tlg003": "Ajax",
        "tlg0011.tlg004": "Oedipus Rex",
        "tlg0011.tlg005": "Electra",
        "tlg0011.tlg006": "Philoctetes",
        "tlg0011.tlg007": "Oedipus at Colonus",
        "tlg0011.tlg008": "Ichneutae",
        "tlg0012.tlg001": "Iliad",
        "tlg0012.tlg002": "Odyssey",
        "tlg0019.tlg001": "Acharnians",
        "tlg0019.tlg002": "Knights",
        "tlg0019.tlg003": "Clouds",
        "tlg0019.tlg004": "Wasps",
        "tlg0019.tlg005": "Peace",
        "tlg0019.tlg006": "Birds",
        "tlg0019.tlg007": "Lysistrata",
        "tlg0019.tlg008": "Thesmophoriazusae",
        "tlg0019.tlg009": "Frogs",
        "tlg0019.tlg010": "Ecclesiazusae",
        "tlg0019.tlg011": "Wealth",
        "tlg0020.tlg001": "Theogony",
        "tlg0020.tlg002": "Works and Days",
        "tlg0020.tlg003": "Shield of Heracles",
        "tlg0085.tlg001": "Suppliant Women",
        "tlg0527.tlg032": "Job",
        "tlg0085.tlg002": "Persians",
        "tlg0085.tlg003": "Prometheus Bound",
        "tlg0085.tlg004": "Seven Against Thebes",
        "tlg0085.tlg005": "Agamemnon",
        "tlg0085.tlg006": "Libation Bearers",
        "tlg0085.tlg007": "Eumenides",
        "tlg0086.tlg034": "Poetics",
        "tlg2045.tlg001": "Dionysiaca",
    }

    if incremental:
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            catalog = {"works": {}, "authors": AUTHOR_NAMES}
            incremental = False
            works = all_works
        catalog.setdefault("works", {})
        catalog["authors"] = AUTHOR_NAMES
    else:
        catalog = {"works": {}, "authors": AUTHOR_NAMES}

    for tg, wk in [(w["textgroup"], w["work"]) for w in works]:
        work_key = f"{tg}.{wk}"
        print(f"\n[shard] {work_key}")

        work_dir = out_root / "data" / tg / wk
        work_dir.mkdir(parents=True, exist_ok=True)
        for stale in work_dir.glob(f"{work_key}.*"):
            stale.unlink()

        ordered_books, chapter_book, cs_book, ambiguous = _book_lookup(src, tg, wk)
        if ambiguous:
            print(f"  \u26a0 chapter values are reused across books for {work_key}; "
                  f"using chapter+section for tables that have a section column "
                  f"(treebank_sentences, treebank_tokens), and a best-effort "
                  f"last-write-wins chapter-only mapping for metrical_lines, which "
                  f"has no section column to disambiguate with -- worth a manual "
                  f"spot check of metrical_lines placement for this work.")

        if ordered_books == [None]:
            # No book divisions at all (flat prose work) -- fall back to
            # splitting by contiguous chapters (in reading order) instead.
            ordered_keys = [r[0] for r in src.execute(
                "SELECT chapter FROM alignment_grid WHERE textgroup=? AND work=? "
                "GROUP BY chapter ORDER BY MIN(sort_order)", (tg, wk)).fetchall()]
            sizes = _estimate_flat_chapter_sizes(src, tg, wk)
            part_groups = _bin_into_parts(ordered_keys, sizes, PART_SIZE_CEILING_BYTES)
            split_mode = "chapter"
        else:
            sizes = _estimate_book_sizes(src, tg, wk, ordered_books, chapter_book, cs_book)
            part_groups = _bin_into_parts(ordered_books, sizes, PART_SIZE_CEILING_BYTES)
            split_mode = "book"

        if not part_groups:
            print(f"  ! no passages found for {work_key} -- skipping (nothing to shard)")
            continue

        n_parts = len(part_groups)
        if n_parts > 1:
            print(f"  \u2192 splitting into {n_parts} parts by {split_mode} "
                  f"({[len(p) for p in part_groups]} {split_mode}s each)")

        def _write_group_to_path(shard_path, group):
            """Writes one part's data (for `group`, a list of book or
            chapter keys) to `shard_path`. Returns per-table row counts."""
            shard_path.unlink(missing_ok=True)
            dst = sqlite3.connect(str(shard_path))
            dst.execute("PRAGMA synchronous=OFF")

            for table in ALL_TABLES:
                schema = src.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)).fetchone()
                if schema and schema[0]:
                    dst.execute(schema[0])
            dst.commit()

            group_set = set(group)
            row_counts = {}
            for table in ALL_TABLES:
                try:
                    col_names = _table_cols(src, table)

                    if table in WHOLESALE_TABLES:
                        if "textgroup" in col_names and "work" in col_names:
                            rows_data = src.execute(
                                f"SELECT * FROM {table} WHERE textgroup=? AND work=?",
                                (tg, wk)).fetchall()
                        else:
                            rows_data = []

                    elif table == "alignment_grid":
                        key_col = "book" if split_mode == "book" else "chapter"
                        placeholders = ", ".join("?" for _ in group)
                        rows_data = src.execute(
                            f"SELECT * FROM alignment_grid WHERE textgroup=? AND work=? "
                            f"AND {key_col} IN ({placeholders})", (tg, wk, *group)).fetchall()

                    elif table == "text_segments":
                        key_col = "book" if split_mode == "book" else "chapter"
                        placeholders = ", ".join("?" for _ in group)
                        rows_data = src.execute(f"""
                            SELECT ts.* FROM text_segments ts
                            JOIN alignment_grid ag ON ts.passage_urn = ag.passage_urn
                            WHERE ag.textgroup=? AND ag.work=? AND ag.{key_col} IN ({placeholders})
                        """, (tg, wk, *group)).fetchall()

                    else:
                        # treebank_sentences / treebank_tokens / metrical_lines --
                        # keyed by chapter(+section); filtered in Python via the
                        # book lookup (or directly by chapter in the flat-work
                        # fallback), since there's no book column to filter on
                        # directly in SQL here for tables that predate `book`.
                        all_rows = src.execute(
                            f"SELECT * FROM {table} WHERE textgroup=? AND work=?",
                            (tg, wk)).fetchall()
                        chapter_idx = col_names.index("chapter")
                        section_idx = col_names.index("section") if "section" in col_names else None
                        subdoc_idx = col_names.index("subdoc") if "subdoc" in col_names else None
                        book_idx    = col_names.index("book") if "book" in col_names else None
                        use_cs = cs_book is not None and section_idx is not None
                        ordered_books_set = set(ordered_books)
                        rows_data = []
                        for row in all_rows:
                            key_of_row = None
                            # 1) A real `book` column (treebank_sentences /
                            # treebank_tokens, once populated) is authoritative
                            # -- use it directly, no join/guessing needed. This
                            # is the actual fix: parse_poetry_cards_tei hardcodes
                            # section="1" on every alignment_grid row for poetry,
                            # so cs_book's (chapter, section) key -- and even bare
                            # chapter_book -- can't disambiguate a chapter number
                            # reused across books (book 1 poem 1 vs. book 2 poem
                            # 1, both "1"); both silently route every book's rows
                            # into whichever book sorted last.
                            if book_idx is not None and row[book_idx]:
                                key_of_row = row[book_idx]
                            # 2) Older rows (or tables without `book`, e.g.
                            # metrical_lines): fall back to parsing it out of
                            # subdoc, which for poem-carded rows is the full
                            # sent_id ("1.1.5"/"2.1.5" -- see cell 4).
                            elif subdoc_idx is not None:
                                subdoc_val = row[subdoc_idx]
                                if subdoc_val:
                                    maybe_book = str(subdoc_val).split('.', 1)[0]
                                    if maybe_book in ordered_books_set:
                                        key_of_row = maybe_book
                            # 3) Last resort: the original chapter/section join
                            # (fine for genuinely unambiguous works, and for
                            # metrical_lines which has no subdoc/book at all).
                            if key_of_row is None:
                                if split_mode == "chapter":
                                    key_of_row = row[chapter_idx]
                                elif use_cs:
                                    key_of_row = cs_book.get((row[chapter_idx], row[section_idx]))
                                else:
                                    key_of_row = chapter_book.get(row[chapter_idx])
                            if key_of_row in group_set:
                                rows_data.append(row)

                    if rows_data:
                        col_list = ", ".join(col_names)
                        placeholders = ", ".join("?" for _ in col_names)
                        insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                        for row in rows_data:
                            dst.execute(insert_sql, row)
                        dst.commit()
                        row_counts[table] = len(rows_data)

                except Exception as e:
                    print(f"  ! {shard_path.name} {table}: {e}")

            dst.close()
            return row_counts

        def _resolve_under_ceiling(group):
            """Writes `group` to a scratch file and checks its REAL size --
            not the estimate -- since the estimate can undershoot badly at
            high row counts (SQLite per-row overhead isn't something a raw
            content-byte sum captures well). If it's over HARD_SIZE_CEILING_BYTES
            and still has more than one book/chapter to split, bisects and
            recurses. Returns a flat list of (group, row_counts) tuples, each
            verified to fit (or a single book/chapter that can't be split
            further, flagged loudly instead of silently shipped oversized)."""
            scratch = work_dir / f"{work_key}.scratch.db"
            row_counts = _write_group_to_path(scratch, group)
            actual_bytes = scratch.stat().st_size
            scratch.unlink(missing_ok=True)

            if actual_bytes <= HARD_SIZE_CEILING_BYTES or len(group) <= 1:
                if actual_bytes > HARD_SIZE_CEILING_BYTES:
                    print(f"  \u26a0 a single {split_mode} ({group[0]}) is "
                          f"{actual_bytes/1e6:.1f}MB on its own -- can't split further "
                          f"at this granularity; will ship oversized.")
                return [(group, row_counts)]

            mid = len(group) // 2
            print(f"  \u21bb estimate undershot: a {len(group)}-{split_mode} group came out "
                  f"{actual_bytes/1e6:.1f}MB (over the {HARD_SIZE_CEILING_BYTES/1e6:.0f}MB hard "
                  f"ceiling) -- bisecting and re-checking")
            return _resolve_under_ceiling(group[:mid]) + _resolve_under_ceiling(group[mid:])

        resolved_groups = []
        for group in part_groups:
            resolved_groups.extend(_resolve_under_ceiling(group))

        parts_meta = []
        for i, (group, _unused_counts) in enumerate(resolved_groups, start=1):
            part_file = f"{work_key}.part{i}.db"
            shard_path = work_dir / part_file
            row_counts = _write_group_to_path(shard_path, group)  # final numbered write
            for table, n in row_counts.items():
                print(f"    part{i} {table}: {n}")

            sz = shard_path.stat().st_size
            flag = "  \u26a0 STILL OVER 100MB" if sz > 100 * 1024 * 1024 else ""
            print(f"  \u2713 part{i}: {sz/1e6:.1f}MB ({split_mode}s {group[0]}\u2026{group[-1]}){flag}")
            parts_meta.append({
                "part": i, "file": part_file,
                split_mode + "s": [str(x) for x in group],
                "bytes": sz,
                "sha256": _file_sha256(shard_path),
            })

        # ── Work-level metadata (unchanged in spirit: computed against the
        # FULL work from the monolith, not any individual part) ────────────
        metadata = {"textgroup": tg, "work": wk, "parts": parts_meta, "annotations": {}}

        versions = [dict(r) for r in src.execute(
            "SELECT short_id, urn, label, doc_type, text_class, source_version, "
            "source_certainty, source_note, translation_of "
            "FROM text_units WHERE textgroup=? AND work=?",
            (tg, wk))]
        metadata["versions"] = versions

        for key, sql in [
            ("treebanks", "SELECT COUNT(DISTINCT version_short_id) FROM treebank_sentences WHERE textgroup=? AND work=?"),
            ("alignments", "SELECT COUNT(DISTINCT pair_id) FROM token_alignments WHERE textgroup=? AND work=?"),
            ("commentaries", "SELECT COUNT(DISTINCT subdoc) FROM treebank_speakers WHERE textgroup=? AND work=?"),
            ("metrical_lines", "SELECT COUNT(*) FROM metrical_lines WHERE textgroup=? AND work=?"),
        ]:
            try:
                metadata["annotations"][key] = src.execute(sql, (tg, wk)).fetchone()[0]
            except Exception:
                metadata["annotations"][key] = 0

        work_label = src.execute(
            "SELECT MIN(label) FROM text_units WHERE textgroup=? AND work=?", (tg, wk)).fetchone()
        metadata["label"] = WORK_REGISTRY.get(work_key, {}).get(
            "title", work_label[0] if work_label[0] else work_key
        )
        metadata["title"] = WORK_TITLES.get(
            work_key,
            WORK_REGISTRY.get(work_key, {}).get("title", metadata["label"]),
        )

        # Static, per-work display metadata (not derived from the shard,
        # doesn't vary by part). unit_labels overrides the client's default
        # "Book"/"Chapter"/"Section" wording (e.g. a speech collection saying
        # "Speech"/"Paragraph"/"Sentence" instead) -- always from
        # work_registry.json, since there's no TEI-derived source for it.
        #
        # book_titles/book_summaries give real per-book display text (e.g.
        # an oration's own heading) instead of a bare number. These are
        # sourced from work_book_metadata FIRST -- auto-derived straight off
        # the TEI's own <head> elements at build time (see the
        # speech_collection_sentences branch of the parse loop) -- and only
        # fall back to a hand-maintained work_registry.json entry for work
        # types that table doesn't cover. Preferring the table over the
        # registry is what fixes the old bug where an edited/added second
        # <head> in the source XML never reached the reader: previously
        # book_titles/book_summaries came ONLY from work_registry.json, a
        # manual copy that had no way to notice the XML had changed. Both
        # fields remain optional -- omitted entirely when a work has neither
        # DB rows nor a registry entry.
        _reg_entry = WORK_REGISTRY.get(work_key, {})
        if _reg_entry.get("unit_labels"):
            metadata["unit_labels"] = _reg_entry["unit_labels"]

        _db_book_rows = [dict(r) for r in src.execute(
            "SELECT book, title, summary FROM work_book_metadata WHERE textgroup=? AND work=?",
            (tg, wk))]
        _db_titles = {r["book"]: r["title"] for r in _db_book_rows if r["title"]}
        _db_summaries = {r["book"]: r["summary"] for r in _db_book_rows if r["summary"]}

        if _db_titles:
            metadata["book_titles"] = _db_titles
        elif _reg_entry.get("book_titles"):
            metadata["book_titles"] = _reg_entry["book_titles"]

        if _db_summaries:
            metadata["book_summaries"] = _db_summaries
        elif _reg_entry.get("book_summaries"):
            metadata["book_summaries"] = _reg_entry["book_summaries"]

        catalog["works"][work_key] = metadata
        print(f"    Annotations: {metadata['annotations']}")

    src.close()
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n\u2713 Done.")
