"""Edition line-alignment crosswalk ingestion. Relocated from Cell 4."""
import csv
import json
import re
import sqlite3

def ingest_edition_alignment(conn, path, *, textgroup=None, work=None,
                             base_version=None, target_version=None):
    meta = {"work": work, "base_version": base_version, "target_version": target_version}
    header, recs = None, []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("#"):
                if (m := re.match(r"#\s*work:\s*([\w.]+)", line)) and not meta["work"]:
                    meta["work"] = m.group(1)
                if (m := re.match(r"#\s*base[^:]*:\s*([\w-]+)", line)) and not meta["base_version"]:
                    meta["base_version"] = m.group(1)
                if (m := re.match(r"#\s*target:\s*([\w-]+)", line)) and not meta["target_version"]:
                    meta["target_version"] = m.group(1)
                continue
            if not line.strip():
                continue
            cells = line.split("\t")
            if header is None:
                header = cells; continue
            recs.append(dict(zip(header, cells)))

    tg = textgroup or (meta["work"].split(".")[0] if meta["work"] and "." in meta["work"] else None)
    wk = meta["work"].split(".")[1] if (meta["work"] and "." in meta["work"]) else work
    if not (tg and wk and meta["base_version"] and meta["target_version"]):
        raise ValueError(f"Could not resolve identity: tg={tg} wk={wk} meta={meta}")
    pair_id = f"{meta['base_version']}--{meta['target_version']}"

    cells_to_list = lambda c: [x.strip() for x in (c or "").split(",") if x.strip()]

    conn.execute("""
        CREATE TABLE IF NOT EXISTS edition_line_alignments (
            id INTEGER PRIMARY KEY,
            textgroup TEXT NOT NULL, work TEXT NOT NULL, pair_id TEXT NOT NULL,
            base_version TEXT NOT NULL, target_version TEXT NOT NULL,
            seq INTEGER NOT NULL,
            base_lines TEXT NOT NULL, target_lines TEXT NOT NULL,  -- JSON arrays
            type TEXT NOT NULL, score REAL, review INTEGER NOT NULL DEFAULT 0
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ela_pair "
                 "ON edition_line_alignments(textgroup, work, pair_id)")
    conn.execute("DELETE FROM edition_line_alignments WHERE textgroup=? AND work=? AND pair_id=?",
                 (tg, wk, pair_id))
    for seq, r in enumerate(recs):
        conn.execute("""INSERT INTO edition_line_alignments
            (textgroup, work, pair_id, base_version, target_version, seq,
             base_lines, target_lines, type, score, review)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (tg, wk, pair_id, meta["base_version"], meta["target_version"], seq,
             json.dumps(cells_to_list(r.get("base"))),
             json.dumps(cells_to_list(r.get("target"))),
             r.get("type"), float(r["score"]) if r.get("score") else None,
             1 if (r.get("review") or "").strip().upper() == "REVIEW" else 0))
    conn.commit()
    print(f"  ✓ edition_line_alignments [{tg}.{wk}] {pair_id}: {len(recs)} rows")
