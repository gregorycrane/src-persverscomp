"""Publish the recoverable Aeschylus fragment and Claudel trial collections."""
from html import escape
import json
from pathlib import Path
import shutil
import sqlite3

from pipeline.config import WORKSPACE_DIR
from pipeline.core.storage import init_storage_engine
from pipeline.fragment_collections import materialize_work_views

DATA_DIR = Path(__file__).resolve().parents[1] / "experimental" / "aeschylus"
FRAGMENTS_PATH = DATA_DIR / "fragment-collections.json"
SOPHOCLES_FRAGMENTS_PATH = (Path(__file__).resolve().parents[1] / "experimental" /
                             "sophocles" / "fragment-collections.json")
CLAUDEL_PATH = DATA_DIR / "claudel-passages.json"
ALIGNMENT_FILES = (
    "claudel1896-agamemnon-alignment.json",
    "claudel1920-alignment.json",
    "claudel1920-choephoroi-alignment.json",
)


def _fragment_focus(textgroup, work_id, short_id):
    edition = short_id.rsplit("grc", 1)[0].rstrip("-_")
    return f"{textgroup}_{work_id}_{edition}"


def _fragment_passage_urn(fragment, edition_urn):
    source_urn = fragment.get("source_fragment_urn") or f"{edition_urn}:{fragment['number']}"
    return f"{source_urn}.1"


def _fragment_html(work, fragment, source_label="Nauck’s notes"):
    pages = fragment.get("pages") or ([fragment.get("page")] if fragment.get("page") else [])
    locator = ""
    if fragment.get("volume") or pages:
        volume = fragment.get("volume")
        volume_label = {"1": "I", "2": "II", "3": "III"}.get(str(volume), str(volume or ""))
        if len(pages) == 1:
            page_label = f"p. {pages[0]}"
        elif pages:
            page_label = f"pp. {pages[0]}–{pages[-1]}"
        else:
            page_label = ""
        locator = (f'<div class="fc-source-locator">Pearson 1917 · Vol. '+
                   f'{escape(volume_label)}{(" · " + escape(page_label)) if page_label else ""}</div>')
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
    if fragment is work.get("fragments", [None])[0] and work.get("external_work_urn"):
        external_key = work["external_work_urn"].split(":")[-1]
        external_number = work.get("external_fragment", "")
        intro += (f'<p class="fc-related-work"><a href="?w={escape(external_key)}">'
                  f'Pearson fragment {escape(external_number)}: open the separately installed '
                  'Ichneutae</a></p>')
    return (f'<div class="pmv-fragment"><h3>{escape(work["title"])} · Fragment '
            f'{escape(str(fragment["number"]))}</h3>{locator}{intro}<div class="fc-verse">{lines}</div>'
            f'<details class="fc-context" open><summary>Transmitting source and {escape(source_label)}</summary>'
            f'<div>{context}</div></details></div>')


def _publish_fragment_corpus(site_root, catalog, source):
    """Publish the citable author-level fragment corpus independently."""
    textgroup, work_id = source.get("textgroup", "tlg0085"), "fragmenta"
    work_key = f"{textgroup}.{work_id}"
    work_urn = f"urn:cts:greekLit:{work_key}"
    work_dir = site_root / "data" / textgroup / work_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    db_path = work_dir / f"{work_key}.part1.db"
    conn = init_storage_engine(db_path)
    versions = source.get("versions", [])
    fragments = source.get("fragments", [])
    for version in versions:
        conn.execute("INSERT INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type) VALUES (?,?,?,?,?,?,?,?)", (
            _fragment_focus(textgroup, work_id, version["short_id"]),
            version["edition_urn"], version["label"], "greek-text",
            textgroup, work_id, version["short_id"], "edition"))
    corpus_view = {"title": source.get("author", "Aeschylus"), "fragments": fragments}
    for index, fragment in enumerate(fragments):
        version_id = fragment["edition"]
        version = next(v for v in versions if v["short_id"] == version_id)
        urn = _fragment_passage_urn(fragment, version["edition_urn"])
        previous = fragments[index - 1] if index else None
        following = fragments[index + 1] if index + 1 < len(fragments) else None
        prev_urn = (_fragment_passage_urn(previous, version["edition_urn"])
                    if previous and previous["edition"] == version_id else None)
        next_urn = (_fragment_passage_urn(following, version["edition_urn"])
                    if following and following["edition"] == version_id else None)
        chapter = str(fragment["number"])
        conn.execute("INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
                     (urn, textgroup, work_id, None, chapter, "1", prev_urn, next_urn, index))
        conn.execute("INSERT INTO text_segments VALUES (?,?,?)",
                     (urn, version_id, _fragment_html(corpus_view, fragment, source.get("source_label", "Nauck’s notes"))))
        conn.execute("INSERT INTO edition_chapter_order VALUES (?,?,?,?,?,?)",
                     (textgroup, work_id, version_id, None, chapter, index))
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    catalog["works"][work_key] = {
        "textgroup": textgroup, "work": work_id, "title": source.get("corpus_title", "Fragments"),
        "experimental_fragment": True, "fragment_corpus": True,
        "work_urn": work_urn, "default_columns": 1,
        "unit_labels": {"chapter": "Fragment", "section": "Section"},
        "parts": [{"part": 1, "file": db_path.name, "books": [],
                   "chapters": [str(f["number"]) for f in fragments],
                   "bytes": db_path.stat().st_size}],
        "versions": [{"canonical_id": _fragment_focus(textgroup, work_id, v["short_id"]),
                      "short_id": v["short_id"], "urn": v["edition_urn"],
                      "label": v["label"], "doc_type": "edition",
                      "text_class": "greek-text"} for v in versions],
        "annotations": {},
    }


def _publish_fragment_source(site_root, catalog, source_path):
    source = json.loads(source_path.read_text(encoding="utf-8"))
    textgroup = source.get("textgroup", "tlg0085")
    published = materialize_work_views(source)
    works = [w for w in published["works"].values() if w.get("fragments")]
    # Remove both the former frag_-prefixed demo records and records from a
    # previous fragment publication.  Ordinary registered works are retained.
    catalog["works"] = {
        k: v for k, v in catalog.get("works", {}).items()
        if not k.startswith(f"{textgroup}.frag_") and not (v.get("fragmentary") and v.get("textgroup") == textgroup)
        and not (v.get("fragment_corpus") and v.get("textgroup") == textgroup)
    }
    fragment_root = site_root / "data" / textgroup
    fragment_root.mkdir(parents=True, exist_ok=True)
    for legacy_dir in fragment_root.glob("frag_*"):
        if legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)
    _publish_fragment_corpus(site_root, catalog, source)
    for work in works:
        work_id = work.get("work") or work["id"].replace("aeschylus-", "", 1).replace("-", "_")
        work_key = f"{textgroup}.{work_id}"
        object_urn = work.get(
            "object_urn", f"urn:cite2:perseus:fragmentaryplays.v1:{work_id}")
        textgroup_for_work, work_id = work_key.split(".", 1)
        work_dir = fragment_root / work_id
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        db_path = work_dir / f"{work_key}.part1.db"
        conn = init_storage_engine(db_path)
        fragments = work.get("fragments", [])
        versions = work.get("versions") or [{
            "short_id": "nauck1889grc1",
            "edition_urn": "urn:cts:greekLit:tlg0085.fragmenta.nauck1889grc1",
            "label": "Greek (Nauck, 1889; transcription preview)",
        }]
        for version_meta in versions:
            version = version_meta["short_id"]
            focus = _fragment_focus(textgroup, work_id, version)
            conn.execute("INSERT INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type) VALUES (?,?,?,?,?,?,?,?)",
                         (focus, version_meta["edition_urn"], version_meta["label"],
                          "greek-text", textgroup_for_work, work_id, version, "edition"))
        ordered_chapters = []
        seen_chapters = set()
        for index, fragment in enumerate(fragments):
            version = fragment.get("edition", versions[0]["short_id"])
            if version not in {v["short_id"] for v in versions}:
                raise ValueError(f"{work_key}: fragment {fragment.get('number')} uses undeclared edition {version}")
            chapter = str(fragment["number"])
            version_meta = next(v for v in versions if v["short_id"] == version)
            urn = _fragment_passage_urn(fragment, version_meta["edition_urn"])
            edition_fragments = [f for f in fragments if f.get("edition", versions[0]["short_id"]) == version]
            edition_index = edition_fragments.index(fragment)
            prev_urn = None if edition_index == 0 else _fragment_passage_urn(
                edition_fragments[edition_index-1], version_meta["edition_urn"])
            next_urn = None if edition_index + 1 == len(edition_fragments) else _fragment_passage_urn(
                edition_fragments[edition_index+1], version_meta["edition_urn"])
            conn.execute("INSERT OR IGNORE INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
                         (urn, textgroup_for_work, work_id, None, chapter, "1", prev_urn, next_urn, index))
            conn.execute("INSERT INTO text_segments VALUES (?,?,?)",
                         (urn, version, _fragment_html(work, fragment, source.get("source_label", "Nauck’s notes"))))
            conn.execute("INSERT INTO edition_chapter_order VALUES (?,?,?,?,?,?)",
                         (textgroup_for_work, work_id, version, None, chapter, index))
            if chapter not in seen_chapters:
                seen_chapters.add(chapter)
                ordered_chapters.append(chapter)
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
        catalog["works"][work_key] = {
            "textgroup": textgroup_for_work, "work": work_id, "title": work["title"],
            "experimental_fragment": True, "fragmentary": True,
            "object_urn": object_urn, "default_columns": 1,
            "unit_labels": {"chapter": "Fragment", "section": "Section"},
            "parts": [{"part": 1, "file": db_path.name, "books": [],
                       "chapters": ordered_chapters,
                       "bytes": db_path.stat().st_size}],
            "versions": [{"canonical_id": _fragment_focus(textgroup, work_id, v["short_id"]),
                          "short_id": v["short_id"], "urn": v["edition_urn"],
                          "label": v["label"], "doc_type": "edition",
                          "text_class": "greek-text"} for v in versions],
            "annotations": {},
        }
    rendered = json.dumps(published, ensure_ascii=False, indent=2) + "\n"
    (site_root / f"{textgroup}-fragment-collections.json").write_text(
        rendered, encoding="utf-8")
    if textgroup == "tlg0085":
        (site_root / "fragment-collections.json").write_text(rendered, encoding="utf-8")
    return len(works)


def _publish_fragments(site_root, catalog):
    return _publish_fragment_source(site_root, catalog, FRAGMENTS_PATH)


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
            conn.execute("INSERT INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type) VALUES (?,?,?,?,?,?,?,?)", tuple(unit.values()))
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
    sophocles_fragments = (
        _publish_fragment_source(site_root, catalog, SOPHOCLES_FRAGMENTS_PATH)
        if SOPHOCLES_FRAGMENTS_PATH.exists() else 0
    )
    claudel = _publish_claudel(site_root, catalog)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total_fragments = fragments + sophocles_fragments
    print(f"  ✓ Published experimental collections: {total_fragments} fragment works "
          f"({sophocles_fragments} Sophocles), {claudel} Claudel versions")
    return {"fragment_works": fragments, "claudel_versions": claudel}
