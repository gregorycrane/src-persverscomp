"""Lexicon sharding -- split the monolith's lexicon_* tables into the
per-shard sql.js DBs the browser fetches, and (re)write site/lexica.json.

Ported from the archived notebook's "Cell 2c" (shard_lexica). The one
addition: `only_shard_files` lets a caller process just one shard and
*merge* its manifest entries into an existing lexica.json rather than
rewriting the whole file -- so wiring in a single new lexicon (the
Orlando Furioso glossary) doesn't disturb the other lexica, which are
still produced by the notebook.
"""
import json
import sqlite3
from pathlib import Path

_LEXICON_TABLES = ["lexicon_meta", "lexicon_scope", "lexicon_entries",
                   "lexicon_aliases", "lexicon_citations"]


def shard_lexica(monolith_path, lexica_dir, site_root, only_shard_files=None):
    lexica_dir = Path(lexica_dir)
    site_root = Path(site_root)
    lexica_dir.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(str(monolith_path))
    src.row_factory = sqlite3.Row

    have = {r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'lexicon_%'")}
    if "lexicon_meta" not in have:
        src.close()
        print("  ! shard_lexica: no lexicon_meta in monolith -- nothing to shard")
        return

    shard_files = [r[0] for r in src.execute(
        "SELECT DISTINCT shard_file FROM lexicon_meta ORDER BY shard_file")]
    if only_shard_files is not None:
        wanted = set(only_shard_files)
        shard_files = [s for s in shard_files if s in wanted]

    processed = {"lexica": {}, "textgroups": {}}   # what THIS run produced

    for shard_file in shard_files:
        lexicon_ids = [r[0] for r in src.execute(
            "SELECT lexicon_id FROM lexicon_meta WHERE shard_file=?", (shard_file,))]
        if not lexicon_ids:
            continue

        shard_path = lexica_dir / shard_file
        shard_path.unlink(missing_ok=True)
        dst = sqlite3.connect(str(shard_path))
        dst.execute("PRAGMA synchronous=OFF")
        placeholders = ", ".join("?" for _ in lexicon_ids)

        for table in _LEXICON_TABLES:
            if table not in have:
                continue
            schema = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if schema and schema[0]:
                dst.execute(schema[0])
            col_names = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
            rows = src.execute(
                f"SELECT {', '.join(col_names)} FROM {table} "
                f"WHERE lexicon_id IN ({placeholders})", lexicon_ids).fetchall()
            if rows:
                dst.executemany(
                    f"INSERT INTO {table} ({', '.join(col_names)}) "
                    f"VALUES ({', '.join('?' for _ in col_names)})",
                    [tuple(r) for r in rows])
        dst.commit()
        dst.close()

        for lexicon_id in lexicon_ids:
            m = src.execute(
                "SELECT title, author, citation, entry_kind FROM lexicon_meta "
                "WHERE lexicon_id=?", (lexicon_id,)).fetchone()
            processed["lexica"][lexicon_id] = {
                "title": m["title"], "author": m["author"],
                "citation": m["citation"], "entry_kind": m["entry_kind"],
                "shard": shard_file,
            }
            for tg in (r[0] for r in src.execute(
                    "SELECT textgroup FROM lexicon_scope WHERE lexicon_id=?", (lexicon_id,))):
                processed["textgroups"].setdefault(tg, [])
                if lexicon_id not in processed["textgroups"][tg]:
                    processed["textgroups"][tg].append(lexicon_id)

        print(f"  ✓ lexicon shard {shard_file}: {len(lexicon_ids)} lexicon(s)")

    src.close()

    manifest_path = site_root / "lexica.json"
    if only_shard_files is None:
        manifest = processed
    else:
        # Merge into whatever is already there (notebook-produced or prior run).
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            manifest = {"lexica": {}, "textgroups": {}}
        manifest.setdefault("lexica", {})
        manifest.setdefault("textgroups", {})
        new_ids = set(processed["lexica"])
        manifest["lexica"].update(processed["lexica"])
        # drop our lexicon_ids from every textgroup list, then re-add fresh
        for tg, ids in list(manifest["textgroups"].items()):
            manifest["textgroups"][tg] = [i for i in ids if i not in new_ids]
        for tg, ids in processed["textgroups"].items():
            manifest["textgroups"].setdefault(tg, [])
            for i in ids:
                if i not in manifest["textgroups"][tg]:
                    manifest["textgroups"][tg].append(i)
            if not manifest["textgroups"][tg]:
                del manifest["textgroups"][tg]

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✓ {manifest_path}")
