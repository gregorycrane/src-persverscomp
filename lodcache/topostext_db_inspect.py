"""
ToposText app-database inspector — finds out what's actually in
topostext.db before we write any ingestion code against it.

Doesn't trust guessed table/column names (places / index / passages) --
inspects every table's real schema, then searches every TEXT-like column
across the whole database for CTS URN patterns, so we find the citation
data wherever it actually lives, whatever it's actually called.

Usage:
    python3 topostext_db_inspect.py <path-to-db-file>
"""

import re
import sqlite3
import sys

CTS_RE = re.compile(r"urn:cts:greekLit:tlg\d+\.tlg\d+")


def list_tables(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cur.fetchall()]


def describe_table(conn, table):
    print(f"\n=== {table} ===")
    try:
        cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
        count = cur.fetchone()[0]
    except sqlite3.Error as e:
        print(f"  (couldn't count rows: {e})")
        return
    print(f"  rows: {count:,}")

    cur = conn.execute(f'PRAGMA table_info("{table}")')
    cols = cur.fetchall()
    col_names = [c[1] for c in cols]
    print(f"  columns: {col_names}")

    if count == 0:
        return

    cur = conn.execute(f'SELECT * FROM "{table}" LIMIT 3')
    for row in cur.fetchall():
        # Truncate long values so the sample stays readable.
        shown = [
            (str(v)[:80] + "...") if isinstance(v, str) and len(str(v)) > 80 else v
            for v in row
        ]
        print(f"  sample row: {dict(zip(col_names, shown))}")


def find_cts_urns(conn, tables):
    """The real point of this script: scan every text column in every
    table for anything matching a CTS URN, regardless of what the
    table/column is called. This is how we find the citation data even
    if it's not in a table literally named 'index' or 'passages'.
    """
    print("\n" + "=" * 60)
    print("Scanning all tables for CTS URN patterns "
          "(urn:cts:greekLit:tlgNNNN.tlgNNN...)")
    print("=" * 60)

    hits_by_table = {}
    for table in tables:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        cols = cur.fetchall()
        text_cols = [c[1] for c in cols if c[2].upper() in ("TEXT", "VARCHAR", "")
                     or "CHAR" in c[2].upper()]
        if not text_cols:
            continue
        for col in text_cols:
            try:
                cur = conn.execute(
                    f'SELECT "{col}" FROM "{table}" '
                    f'WHERE "{col}" LIKE \'%cts:%\' LIMIT 5'
                )
                rows = cur.fetchall()
            except sqlite3.Error:
                continue
            matches = [r[0] for r in rows if r[0] and CTS_RE.search(str(r[0]))]
            if matches:
                hits_by_table.setdefault(table, []).append((col, matches))

    if not hits_by_table:
        print("No CTS URN patterns found in any text column across the "
              "whole database. Either this database doesn't carry them "
              "under this exact URN format, or the citation data lives "
              "in a different db file / a differently-formatted "
              "reference (e.g. an internal numeric ID needing a separate "
              "lookup table -- check tables with generic names like "
              "'refs', 'tags', 'mentions', 'links' by eye if this comes "
              "back empty).")
        return

    for table, col_hits in hits_by_table.items():
        for col, matches in col_hits:
            print(f"\n  FOUND in {table}.{col}:")
            for m in matches:
                print(f"    {m}")


def main(path):
    conn = sqlite3.connect(path)
    tables = list_tables(conn)
    print(f"Database: {path}")
    print(f"Tables found ({len(tables)}): {tables}")

    for table in tables:
        describe_table(conn, table)

    find_cts_urns(conn, tables)
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
