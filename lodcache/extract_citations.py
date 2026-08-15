"""
Extract real place citations for Thucydides, Iliad, and Agamemnon from
the ToposText app's SQLite database (topostext.db).

Confirmed schema (from inspection, not assumed):
    ZINDEXTABLE.ZPLACE     -> ZPLACES._id      (coordinates, place id, name)
    ZINDEXTABLE.ZPARAGRAPH -> ZPARAGRAPH._id   (ZLOCATION = citation, e.g. "1.1")
    ZINDEXTABLE.ZWORK      -> ZWORKS._id       (work title/credits)

Usage:
    python3 extract_citations.py <path-to-db> types      # step 0: what ZTYPE values exist
    python3 extract_citations.py <path-to-db> find_works # step 1: locate our 3 target works
    python3 extract_citations.py <path-to-db> extract    # step 2: pull the real citation rows
"""

import csv
import sqlite3
import sys

# Titles to search for -- LIKE patterns, case-insensitive via COLLATE NOCASE.
# We match on title text rather than assuming a work id, since ZWORKS has
# 819 rows and we don't want to guess wrong the way earlier assumptions
# about field names turned out wrong.
TARGET_TITLE_PATTERNS = {
    "Thucydides": "%Thucydides%",
    "Iliad": "%Iliad%",
    "Agamemnon": "%Agamemnon%",
}


def show_type_values(conn):
    """Step 0: what mention types actually exist in ZINDEXTABLE, and how
    many of each have a non-null ZPLACE. This tells us whether to filter
    strictly to a 'place' type or include broader categories like
    'ethnic' that still carry a real, mappable place id.
    """
    cur = conn.execute(
        "SELECT ZTYPE, COUNT(*), "
        "SUM(CASE WHEN ZPLACE IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM ZINDEXTABLE GROUP BY ZTYPE ORDER BY COUNT(*) DESC"
    )
    print(f"{'ZTYPE':<20} {'total rows':>12} {'rows w/ ZPLACE':>16}")
    for ztype, total, with_place in cur.fetchall():
        print(f"{str(ztype):<20} {total:>12,} {with_place:>16,}")


def find_target_works(conn):
    """Step 1: locate the _id for each of our three target works by
    title match, printing candidates rather than assuming a single hit
    -- some titles could plausibly match more than one row (e.g. if a
    scholia or commentary work also has 'Iliad' in its title).
    """
    for label, pattern in TARGET_TITLE_PATTERNS.items():
        print(f"\n--- candidates for {label!r} (pattern {pattern!r}) ---")
        cur = conn.execute(
            "SELECT _id, ZWORKID, ZCATEGORY, ZTITLE, ZLANGUAGE "
            "FROM ZWORKS WHERE ZTITLE LIKE ? COLLATE NOCASE",
            (pattern,),
        )
        rows = cur.fetchall()
        if not rows:
            print("  (no matches -- pattern may need adjusting)")
        for row in rows:
            print(f"  _id={row[0]} ZWORKID={row[1]} category={row[2]!r} "
                  f"title={row[3]!r} lang={row[4]!r}")


def extract_citations(conn, work_ids, out_prefix="citations"):
    """Step 2: pull every (place, citation) pair for the given work ids
    and write one CSV per work. work_ids is a dict of {label: _id}.
    """
    for label, work_id in work_ids.items():
        cur = conn.execute(
            """
            SELECT idx.ZTYPE, idx.ZNAME, par.ZLOCATION AS citation,
                   pl.ZPLACEID, pl.ZDISPLAYNAME, pl.ZLATITUDE, pl.ZLONGITUDE,
                   pl.ZFEATURETYPE
            FROM ZINDEXTABLE idx
            JOIN ZPARAGRAPH par ON idx.ZPARAGRAPH = par._id
            LEFT JOIN ZPLACES pl ON idx.ZPLACE = pl._id
            WHERE idx.ZWORK = ? AND idx.ZPLACE IS NOT NULL
            ORDER BY par.ZLOCATION
            """,
            (work_id,),
        )
        rows = cur.fetchall()
        out_path = f"{out_prefix}_{label.lower()}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["mention_type", "mention_name", "citation",
                        "place_id", "place_name", "lat", "lon", "feature_type"])
            w.writerows(rows)
        print(f"{label}: {len(rows)} place-mention rows -> {out_path}")
        if rows:
            types_seen = sorted(set(r[0] for r in rows))
            print(f"  mention types present: {types_seen}")
            print(f"  sample: {rows[0]}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    path, cmd = sys.argv[1], sys.argv[2]
    conn = sqlite3.connect(path)

    if cmd == "types":
        show_type_values(conn)
    elif cmd == "find_works":
        find_target_works(conn)
    elif cmd == "extract":
        # Requires work ids passed as label=id pairs, e.g.:
        #   python3 extract_citations.py db.sqlite extract Thucydides=52 Iliad=2 Agamemnon=12
        work_ids = {}
        for pair in sys.argv[3:]:
            label, _, wid = pair.partition("=")
            work_ids[label] = int(wid)
        if not work_ids:
            print("Pass work ids as Label=id pairs, e.g.:\n"
                  "  python3 extract_citations.py db.sqlite extract "
                  "Thucydides=52 Iliad=2 Agamemnon=12\n"
                  "(run 'find_works' first to get the real ids)")
            sys.exit(1)
        extract_citations(conn, work_ids)
    else:
        print(__doc__)

    conn.close()


if __name__ == "__main__":
    main()
