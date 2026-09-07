"""ToposText place-citation ingestion (Thucydides/Iliad/Agamemnon/Apollonius/
Nonnus pilot). Relocated from Cell 7.

PLACE_REFERENCE_WORKS is its own small registry keyed by CSV-filename label,
not by WORK_REGISTRY's work_key -- ingest_place_references() now accepts an
optional `labels` filter instead of always processing every CSV.
"""
import csv
import sqlite3
from pathlib import Path

TOPOTEXT_CSV_DIR = Path("/Users/gcrane/github/src-persverscomp/lodcache")

PLACE_REFERENCE_WORKS = {
    "apollonius": ("tlg0001", "tlg001"),
    "thucydides": ("tlg0003", "tlg001"),
    "iliad":      ("tlg0012", "tlg001"),
    "agamemnon":  ("tlg0085", "tlg005"),
    "nonnus":  ("tlg2045", "tlg001"),
}

def _citation_to_card_chapter(citation, book_intervals, has_books):
    """Maps a ToposText citation (a raw line number, optionally with a
    book prefix for multi-book poetry) to its containing card, returned
    as a (book, chapter) PAIR -- never folded into one string. This
    matches how alignment_grid actually stores poetry addressing: a
    real, separate `book` column plus a bare card-label `chapter`
    (e.g. book="18", chapter="1-21"), NOT the "book.chapter" folded
    convention that only applies to prose works like Thucydides (see
    getChapterDataPayload's "AND book=?" clause in app.js, which is
    the ground truth this must match). For a bookless work, book is
    returned as None and chapter is the bare card label alone.
    Returns (None, None) if the line falls outside every known card.
    """
    parts = citation.split(".")
    if has_books and len(parts) >= 2:
        book, line_str = parts[0], parts[-1]
    else:
        book, line_str = "1", parts[-1]
    try:
        line_num = int(line_str)
    except ValueError:
        return None, None
    for card in book_intervals.get(book, []):
        if card["start_line"] <= line_num <= card["end_line"]:
            return (book if has_books else None), card["label"]
    return None, None


def ingest_place_references(conn, labels=None, work_has_books=None):
    """Relocated from Cell 7's driver tail, parameterized with a `labels`
    filter (subset of PLACE_REFERENCE_WORKS keys) instead of always
    processing every CSV in TOPOTEXT_CSV_DIR.

    work_has_books: like chunking_guard.py's run_chunking_guard, this was
    kernel-global state (WORK_HAS_BOOKS, populated by Cell 1's edition
    ingestion) in the notebook -- pass the same dict
    ingest_work.ingest_editions_and_structure() returns. Defaults to empty,
    matching the original code's own fallback (`WORK_HAS_BOOKS.get(work_key,
    True)` -- i.e. assume book-divided unless told otherwise).
    """
    from pipeline.registry import WORK_REGISTRY
    from pipeline.core.canonical_intervals import build_poetry_canonical_intervals
    WORK_HAS_BOOKS = work_has_books or {}
    cur = conn.cursor()
    target_labels = labels or list(PLACE_REFERENCE_WORKS.keys())
    # Drop and recreate rather than CREATE TABLE IF NOT EXISTS: earlier runs
    # of this cell (before the book/chapter-separation fix) created this
    # table WITHOUT a book column, and IF NOT EXISTS would silently keep
    # that stale schema around, breaking every insert below with "no column
    # named book". Safe to drop unconditionally since the table is always
    # fully repopulated from the CSVs on every run regardless.
    conn.execute("DROP TABLE IF EXISTS place_references")
    conn.execute("""
        CREATE TABLE place_references (
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            book TEXT,
            chapter TEXT NOT NULL,
            mention_type TEXT,
            mention_name TEXT,
            place_id TEXT,
            place_name TEXT,
            lat REAL,
            lon REAL,
            feature_type TEXT
        )
    """)

    # Idempotent re-run: clear any previously-loaded rows for these three
    # works before inserting, so running this cell twice doesn't duplicate
    # every row.
    for label in target_labels:
        tg, wk = PLACE_REFERENCE_WORKS[label]
        conn.execute("DELETE FROM place_references WHERE textgroup=? AND work=?", (tg, wk))

    total_inserted = 0
    for label in target_labels:
        tg, wk = PLACE_REFERENCE_WORKS[label]
        csv_path = TOPOTEXT_CSV_DIR / f"citations_{label}.csv"
        if not csv_path.exists():
            print(f"  ! {csv_path} not found -- skipping {label}")
            continue

        work_key = f"{tg}.{wk}"
        work_meta = WORK_REGISTRY[work_key]
        is_poetry = any(c.get("parse_mode") == "poetry_cards"
                         for c in work_meta.get("editions", {}).values())
        has_books = WORK_HAS_BOOKS.get(work_key, True)

        book_intervals = None
        if is_poetry:
            book_intervals = build_poetry_canonical_intervals(work_meta["editions"])

        rows_for_work = []
        unmatched = 0
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                book_val = None
                chapter = row["citation"]
                if is_poetry:
                    book_val, mapped = _citation_to_card_chapter(row["citation"], book_intervals, has_books)
                    if mapped is None:
                        unmatched += 1
                        continue
                    chapter = mapped

                lat = float(row["lat"]) if row["lat"] not in (None, "") else None
                lon = float(row["lon"]) if row["lon"] not in (None, "") else None
                rows_for_work.append((
                    tg, wk, book_val, chapter,
                    row["mention_type"], row["mention_name"],
                    row["place_id"], row["place_name"], lat, lon,
                    row["feature_type"],
                ))

        conn.executemany(
            "INSERT INTO place_references "
            "(textgroup, work, book, chapter, mention_type, mention_name, "
            " place_id, place_name, lat, lon, feature_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_for_work,
        )
        conn.commit()
        print(f"  {label} ({tg}.{wk}, {'poetry-cards' if is_poetry else 'prose'}): "
              f"{len(rows_for_work)} rows loaded from {csv_path.name}"
              + (f" ({unmatched} citations fell outside every known card -- skipped)"
                 if unmatched else ""))
        total_inserted += len(rows_for_work)

    print(f"\nTotal place_references rows loaded: {total_inserted}")

    # Quick sanity check: how many DISTINCT chapter values do we have per
    # work, and does that look like a reasonable spread (not, say, every
    # row collapsed onto one chapter due to a citation-parsing bug)?
    for label in target_labels:
        tg, wk = PLACE_REFERENCE_WORKS[label]
        n = conn.execute(
            "SELECT COUNT(DISTINCT chapter) FROM place_references WHERE textgroup=? AND work=?",
            (tg, wk)).fetchone()[0]
        print(f"  {label}: {n} distinct chapter values")

    conn.commit()
    return total_inserted
