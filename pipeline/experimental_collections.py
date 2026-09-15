"""Publish the recoverable Aeschylus fragment and Claudel trial collections."""
from html import escape
import json
from pathlib import Path
import shutil
import sqlite3

from pipeline.config import WORKSPACE_DIR
from pipeline.core.storage import init_storage_engine

DATA_DIR = Path(__file__).resolve().parents[1] / "experimental" / "aeschylus"
FRAGMENTS_PATH = DATA_DIR / "fragment-collections.json"
CLAUDEL_PATH = DATA_DIR / "claudel-passages.json"
ALIGNMENT_FILES = (
    "claudel1896-agamemnon-alignment.json",
    "claudel1920-alignment.json",
    "claudel1920-choephoroi-alignment.json",
)


def _fragment_html(work, fragment):
    lines = "".join(
        f'<div lang="grc" class="fc-line"><span>{escape(str(line["ref"]))}</span>'
        f'<div>{escape(line["text"])}</div></div>'
        for line in fragment.get("lines", [])
    ) or "<p>Testimonium only in this encoding.</p>"
    context = "</div><div>".join(escape(fragment.get("context", "")).split("\n\n"))
    intro = ""
    if fragment is work.get("fragments", [None])[0] and work.get("introduction"):
        intro = ('<details class="fc-scope"><summary>Editorial evidence for this play</summary>'
                 f'<p>{escape(work["introduction"])}</p></details>')
    return (f'<div class="pmv-fragment"><h3>{escape(work["title"])} · Fragment '
            f'{escape(str(fragment["number"]))}</h3>{intro}<div class="fc-verse">{lines}</div>'
            '<details class="fc-context" open><summary>Transmitting source and Nauck’s notes</summary>'
            f'<div>{context}</div></details></div>')


def _publish_fragments(site_root, catalog):
    source = json.loads(FRAGMENTS_PATH.read_text(encoding="utf-8"))
    works = [w for w in source["works"].values() if w.get("pmv_work_key")]
    catalog["works"] = {k: v for k, v in catalog.get("works", {}).items()
                        if not k.startswith("tlg0085.frag_")}
    fragment_root = site_root / "data" / "tlg0085"
    fragment_root.mkdir(parents=True, exist_ok=True)
    for work in works:
        work_key = work["pmv_work_key"]
        textgroup, work_id = work_key.split(".", 1)
        work_dir = fragment_root / work_id
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        db_path = work_dir / f"{work_key}.part1.db"
        conn = init_storage_engine(db_path)
        version = "nauck1889grc1"
        conn.execute("INSERT INTO text_units VALUES (?,?,?,?,?,?,?,?)",
                     (work["pmv_focus"], work["edition_urn"],
                      "Greek (Nauck, 1889; transcription preview)", "greek-text",
                      textgroup, work_id, version, "edition"))
        fragments = work.get("fragments", [])
        for index, fragment in enumerate(fragments):
            chapter = str(fragment["number"])
            urn = f"urn:cts:perseusDemo:{work_key}:{chapter}.1"
            prev_urn = None if index == 0 else f"urn:cts:perseusDemo:{work_key}:{fragments[index-1]['number']}.1"
            next_urn = None if index + 1 == len(fragments) else f"urn:cts:perseusDemo:{work_key}:{fragments[index+1]['number']}.1"
            conn.execute("INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
                         (urn, textgroup, work_id, None, chapter, "1", prev_urn, next_urn, index))
            conn.execute("INSERT INTO text_segments VALUES (?,?,?)",
                         (urn, version, _fragment_html(work, fragment)))
            conn.execute("INSERT INTO edition_chapter_order VALUES (?,?,?,?,?,?)",
                         (textgroup, work_id, version, None, chapter, index))
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
        catalog["works"][work_key] = {
            "textgroup": textgroup, "work": work_id, "title": work["title"],
            "experimental_fragment": True, "default_columns": 1,
            "unit_labels": {"chapter": "Fragment", "section": "Section"},
            "parts": [{"part": 1, "file": db_path.name, "books": [],
                       "chapters": [str(f["number"]) for f in fragments],
                       "bytes": db_path.stat().st_size}],
            "versions": [{"canonical_id": work["pmv_focus"], "short_id": version,
                          "urn": work["edition_urn"],
                          "label": "Greek (Nauck, 1889; transcription preview)",
                          "doc_type": "edition", "text_class": "greek-text"}],
            "annotations": {},
        }
    (site_root / "fragment-collections.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(works)


def _publish_claudel(site_root, catalog):
    source = json.loads(CLAUDEL_PATH.read_text(encoding="utf-8"))
    published = 0
    for work_key, payload in source["works"].items():
        meta = catalog.get("works", {}).get(work_key)
        if not meta or not meta.get("parts"):
            continue
        textgroup, work = work_key.split(".", 1)
        db_path = site_root / "data" / textgroup / work / meta["parts"][0]["file"]
        conn = sqlite3.connect(db_path)
        for unit in payload["text_units"]:
            short_id = unit["short_id"]
            conn.execute("DELETE FROM text_segments WHERE version_short_id=?", (short_id,))
            conn.execute("DELETE FROM edition_chapter_order WHERE version_short_id=?", (short_id,))
            conn.execute("DELETE FROM text_units WHERE canonical_id=?", (unit["canonical_id"],))
            conn.execute("INSERT INTO text_units VALUES (?,?,?,?,?,?,?,?)", tuple(unit.values()))
            for row in payload["text_segments"]:
                conn.execute("INSERT OR REPLACE INTO text_segments VALUES (?,?,?)", tuple(row.values()))
            for row in payload["edition_chapter_order"]:
                conn.execute("INSERT OR REPLACE INTO edition_chapter_order VALUES (?,?,?,?,?,?)", tuple(row.values()))
            version_meta = {"canonical_id": unit["canonical_id"], "short_id": short_id,
                            "urn": unit["urn"], "label": unit["label"],
                            "doc_type": unit["doc_type"], "text_class": unit["text_class"]}
            meta["versions"] = [v for v in meta.get("versions", []) if v.get("short_id") != short_id]
            meta["versions"].append(version_meta)
            published += 1
        conn.commit()
        conn.close()
        meta["parts"][0]["bytes"] = db_path.stat().st_size
    for name in ALIGNMENT_FILES:
        shutil.copy2(DATA_DIR / name, site_root / name)
    return published


def publish(site_root=None):
    """Publish all trial assets and merge their metadata into catalog.json."""
    if not FRAGMENTS_PATH.exists() or not CLAUDEL_PATH.exists():
        return {"fragment_works": 0, "claudel_versions": 0}
    site_root = Path(site_root or (WORKSPACE_DIR / "site"))
    catalog_path = site_root / "catalog.json"
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found: {catalog_path}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    fragments = _publish_fragments(site_root, catalog)
    claudel = _publish_claudel(site_root, catalog)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ Published experimental collections: {fragments} fragment works, {claudel} Claudel versions")
    return {"fragment_works": fragments, "claudel_versions": claudel}
