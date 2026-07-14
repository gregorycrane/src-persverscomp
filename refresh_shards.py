#!/usr/bin/env python3
"""
refresh_shards.py  --  in-place maintenance for the persverscomp deployed shards.

Strips foreign `text_segments` rows from every per-work shard under <site>/data/**
(the rows that leaked because text_segments has no textgroup/work columns and was
copied whole during sharding), VACUUMs to reclaim the freed pages, and rewrites the
`bytes` field in catalog.json so the "Available Works" page reports true sizes.

This does NOT need the build monolith or the source XML corpus -- it only touches
the shards that are already on disk. Run it, redeploy site/, hard-refresh the page.

Usage:
    python3 refresh_shards.py /path/to/site            # default: ./site
    python3 refresh_shards.py /path/to/site --dry-run  # report only, no writes
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path


def table_columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def table_exists(con, table):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def refresh_one(db_path: Path, dry_run: bool):
    """Return (work_key, before_rows, after_rows, before_bytes, after_bytes)."""
    work_key = f"{db_path.parent.parent.name}.{db_path.parent.name}"
    before_bytes = db_path.stat().st_size

    con = sqlite3.connect(str(db_path))
    if not (table_exists(con, "text_segments") and table_exists(con, "alignment_grid")):
        con.close()
        print(f"  - {work_key}: no text_segments/alignment_grid; skipped")
        return None

    before_rows = con.execute("SELECT COUNT(*) FROM text_segments").fetchone()[0]
    # alignment_grid is already work-scoped (it has textgroup/work) and shares
    # passage_urn with text_segments, so it is the authoritative passage filter.
    orphan = con.execute(
        "SELECT COUNT(*) FROM text_segments "
        "WHERE passage_urn NOT IN (SELECT passage_urn FROM alignment_grid)"
    ).fetchone()[0]
    after_rows = before_rows - orphan

    if dry_run:
        con.close()
        print(f"  ~ {work_key}: would drop {orphan} of {before_rows} text_segments "
              f"(keep {after_rows})  [{before_bytes/1e6:.1f} MB]")
        return (work_key, before_rows, after_rows, before_bytes, before_bytes)

    if orphan:
        con.execute(
            "DELETE FROM text_segments "
            "WHERE passage_urn NOT IN (SELECT passage_urn FROM alignment_grid)"
        )
        con.commit()
        con.execute("VACUUM")
        con.commit()
    con.close()

    after_bytes = db_path.stat().st_size
    print(f"  \u2713 {work_key}: text_segments {before_rows} \u2192 {after_rows}   "
          f"{before_bytes/1e6:.1f} MB \u2192 {after_bytes/1e6:.2f} MB")
    return (work_key, before_rows, after_rows, before_bytes, after_bytes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?", default="site",
                    help="path to the site/ directory (contains data/ and catalog.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing")
    args = ap.parse_args()

    site = Path(args.site)
    data_root = site / "data"
    if not data_root.is_dir():
        sys.exit(f"no data/ under {site!s} -- pass the site directory")

    shards = sorted(data_root.glob("*/*/*.db"))
    if not shards:
        sys.exit(f"no shards found under {data_root!s}/*/*/*.db")

    print(f"Refreshing {len(shards)} shard(s) under {data_root}"
          + ("  (dry run)" if args.dry_run else ""))
    results = [r for r in (refresh_one(p, args.dry_run) for p in shards) if r]

    # Update catalog.json bytes in place, preserving everything else.
    catalog_path = site / "catalog.json"
    if not args.dry_run and catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        works = catalog.get("works", {})
        updated = 0
        for work_key, _, _, _, after_bytes in results:
            if work_key in works:
                works[work_key]["bytes"] = after_bytes
                updated += 1
        catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\ncatalog.json: updated bytes for {updated} work(s)")
    elif not catalog_path.exists():
        print("\n(no catalog.json found; sizes on disk are corrected but the "
              "Available Works page reads catalog.json -- regenerate it from cell 2)")

    if not args.dry_run:
        saved = sum(b - a for _, _, _, b, a in results)
        print(f"\nReclaimed {saved/1e6:.1f} MB across {len(results)} shard(s).")


if __name__ == "__main__":
    main()
