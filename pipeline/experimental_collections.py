"""Publish TEI-first fragment collections and the Claudel trial collections."""
from copy import deepcopy
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import sqlite3

from pipeline.config import WORKSPACE_DIR
from pipeline.core.storage import init_storage_engine
from pipeline.fragment_collections import build as build_aeschylus_fragments
from pipeline.fragment_collections import materialize_work_views
from pipeline.aeschylus_fragment_concordance import (
    DINDORF as AESCHYLUS_DINDORF,
    NAUCK as AESCHYLUS_NAUCK,
    build_dindorf as build_dindorf_aeschylus,
    build_play_level as build_play_level_aeschylus,
    merge_work_views as merge_aeschylus_work_views,
)
from pipeline.nauck_corpus import AUTHORS as NAUCK_AUTHORS
from pipeline.nauck_corpus import publication_model as build_nauck_author_fragments
from pipeline.sophocles_fragment_concordance import (
    NAUCK as SOPHOCLES_NAUCK,
    PEARSON as SOPHOCLES_PEARSON,
    align_fragments as align_sophocles_fragments,
    merge_work_views as merge_sophocles_work_views,
    safe_card_id,
)
from pipeline.sophocles_dindorf_concordance import (
    DINDORF as SOPHOCLES_DINDORF,
    aggregate_work as aggregate_sophocles_work,
    build_dindorf as build_dindorf_sophocles,
    merge_three_work_views as merge_three_sophocles_work_views,
)
from pipeline.euripides_dindorf_concordance import (
    DINDORF as EURIPIDES_DINDORF,
    NAUCK as EURIPIDES_NAUCK,
    aggregate_work as aggregate_euripides_work,
    build_dindorf as build_dindorf_euripides,
    merge_work_views as merge_euripides_work_views,
)
from pipeline.aristophanes_dindorf_fragments import (
    build_dindorf as build_dindorf_aristophanes,
)
from pipeline.play_level_fragments import build as build_play_level_fragments

DATA_DIR = Path(__file__).resolve().parents[1] / "experimental" / "aeschylus"
CORPUS_DATA_DIR = Path(os.environ.get(
    "GRCNEWXML_DATA_DIR", "/Users/gcrane/github/grcnewxml/data"))
FRAGMENTS_PATH = CORPUS_DATA_DIR / "tlg0085"
DINDORF_FRAGMENTS_PATH = CORPUS_DATA_DIR / "tlg0085"
SOPHOCLES_FRAGMENTS_PATH = (Path(__file__).resolve().parents[1] / "experimental" /
                             "sophocles" / "fragment-collections.json")
SOPHOCLES_DATA_PATH = CORPUS_DATA_DIR / "tlg0011"
EURIPIDES_DATA_PATH = CORPUS_DATA_DIR / "tlg0006"
ARISTOPHANES_DATA_PATH = CORPUS_DATA_DIR / "tlg0019"
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
        f'<l n="{escape(str(line["ref"]))}" lang="grc">{escape(line["text"])}</l>'
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
    display_title = work["title"]
    if work.get("fragment_corpus") and fragment.get("play_title"):
        display_title = f'{display_title} · {fragment["play_title"]}'
    return (f'<div class="pmv-fragment"><h3>{escape(display_title)} · Fragment '
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
    corpus_view = {
        "title": source.get("author", "Aeschylus"),
        "fragments": fragments,
        "fragment_corpus": True,
    }
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
    catalog.setdefault("authors", {})[textgroup] = source.get("author", textgroup)


def _publish_fragment_source(
    site_root, catalog, source_path, xml_builder=None, include_empty_works=False,
    publish_corpus=True,
):
    source_path = Path(source_path)
    source = ((xml_builder or build_aeschylus_fragments)(source_path)
              if source_path.suffix.lower() == ".xml" or source_path.is_dir()
              else json.loads(source_path.read_text(encoding="utf-8")))
    textgroup = source.get("textgroup", "tlg0085")
    published = materialize_work_views(source)
    works = [
        w for w in published["works"].values()
        if include_empty_works or w.get("fragments")
    ]
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
    if publish_corpus:
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
            "short_id": "nauck1889-grc1",
            "edition_urn": "urn:cts:greekLit:tlg0085.fragmenta.nauck1889-grc1",
            "label": "Greek (Nauck, 1889; transcription preview)",
        }]
        for version_meta in versions:
            if not version_meta.get("edition_urn"):
                version_meta["edition_urn"] = (
                    f"urn:cts:greekLit:{textgroup}.{work_id}."
                    f"{version_meta['short_id']}")
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
            "source_title": work.get("source_title", work["title"]),
            "experimental_fragment": True, "fragmentary": True,
            "evidence_only": not bool(fragments),
            "status": "Fragmentary text" if fragments else "Evidence only",
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


def _aggregate_aeschylus_work(works, versions):
    """Build one author-level view from already play-constrained alignments."""
    cards, fragments = [], []
    for work in works.values():
        fragments.extend(work.get("fragments", []))
        for card in work.get("cards", []):
            item = deepcopy(card)
            item["label"] = f"{work['work']}-{card['label']}"
            cards.append(item)
    return {
        "id": "aeschylus-fragmenta", "work": "fragmenta",
        "title": "Aeschylus, Fragments", "source_title": "FRAGMENTA",
        "object_urn": "urn:cts:greekLit:tlg0085.fragmenta",
        "fragments": fragments, "cards": cards, "versions": versions,
        "status": "Fragmentary text", "fragment_corpus": True,
    }


def _publish_fragments(site_root, catalog):
    """Publish Dindorf and Nauck as aligned, independently numbered editions."""
    # Preserve the generic fixture/API used for ad-hoc JSON multi-edition
    # collections; the production Aeschylus source is the paired TEI below.
    if Path(FRAGMENTS_PATH).suffix.lower() == ".json":
        return _publish_fragment_source(site_root, catalog, FRAGMENTS_PATH)
    if Path(FRAGMENTS_PATH).is_dir():
        nauck_source = build_play_level_aeschylus(FRAGMENTS_PATH, AESCHYLUS_NAUCK)
        dindorf_source = build_play_level_aeschylus(
            DINDORF_FRAGMENTS_PATH, AESCHYLUS_DINDORF)
    else:
        nauck_source = build_aeschylus_fragments(FRAGMENTS_PATH)
        dindorf_source = (build_dindorf_aeschylus(DINDORF_FRAGMENTS_PATH)
                           if DINDORF_FRAGMENTS_PATH.exists() else None)
    if dindorf_source is None:
        return _publish_fragment_source(site_root, catalog, FRAGMENTS_PATH)
    works, concordance = merge_aeschylus_work_views(dindorf_source, nauck_source)
    catalog["works"] = {
        key: value for key, value in catalog.get("works", {}).items()
        if not ((value.get("fragmentary") or value.get("fragment_corpus"))
                and value.get("textgroup") == "tlg0085")
    }
    versions = dindorf_source["versions"] + nauck_source["versions"]
    fields = (
        ("dindorf", AESCHYLUS_DINDORF, "Dindorf's sources and notes"),
        ("nauck", AESCHYLUS_NAUCK, "Nauck's notes and apparatus"),
    )
    for work in works.values():
        _write_aligned_fragment_work(
            site_root, catalog, work, textgroup="tlg0085", edition_fields=fields)
    catalog.setdefault("authors", {})["tlg0085"] = "Aeschylus"
    browser_data = {
        "schema_version": 5, "textgroup": "tlg0085", "author": "Aeschylus",
        "corpus_title": "Fragments", "versions": versions, "works": works,
        "collections": [{"id": "aeschylus-fragments", "title": "Fragments",
                         "author": "Aeschylus", "textgroup": "tlg0085",
                         "members": list(works)}],
        "scope": {"work_views": len(works),
                  "dindorf_fragments": len(dindorf_source["fragments"]),
                  "nauck_fragments": len(nauck_source["fragments"]),
                  "aligned_fragment_pairs": len(concordance)},
        "editorial_note": (
            "Dindorf 1893 and Nauck 1889 retain their own fragment numbers. "
            "Shared cards record conservative, text-supported correspondences; "
            "unmatched fragments remain visible as edition-specific cards."),
    }
    rendered = json.dumps(browser_data, ensure_ascii=False, indent=2) + "\n"
    (site_root / "tlg0085-fragment-collections.json").write_text(rendered, encoding="utf-8")
    (site_root / "fragment-collections.json").write_text(rendered, encoding="utf-8")
    (site_root / "tlg0085-fragment-concordance.json").write_text(
        json.dumps({"schema_version": 1,
                    "editions": [AESCHYLUS_DINDORF, AESCHYLUS_NAUCK],
                    "matches": concordance}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return len(works)


def _write_aligned_fragment_work(
    site_root, catalog, work, textgroup="tlg0011", edition_fields=None
):
    """Write one work whose card may contain segments from two editions."""
    work_id = work["work"]
    work_key = f"{textgroup}.{work_id}"
    work_dir = site_root / "data" / textgroup / work_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    db_path = work_dir / f"{work_key}.part1.db"
    conn = init_storage_engine(db_path)
    versions = work.get("versions", [])
    version_map = {v["short_id"]: v for v in versions}
    for version in versions:
        conn.execute(
            "INSERT INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type) VALUES (?,?,?,?,?,?,?,?)",
            (_fragment_focus(textgroup, work_id, version["short_id"]),
             version["edition_urn"], version["label"], "greek-text", textgroup,
             work_id, version["short_id"], "edition"),
        )
    cards = work.get("cards", [])
    card_for_source = {}
    urns = [f"urn:cts:greekLit:{work_key}:{safe_card_id(card['label'])}.1"
            for card in cards]
    edition_fields = edition_fields or (
        ("pearson", SOPHOCLES_PEARSON, "Pearson’s notes and apparatus"),
        ("nauck", SOPHOCLES_NAUCK, "Nauck’s notes and apparatus"),
    )
    for index, (card, urn) in enumerate(zip(cards, urns)):
        conn.execute(
            "INSERT INTO alignment_grid VALUES (?,?,?,?,?,?,?,?,?)",
            (urn, textgroup, work_id, None, card["label"], "1",
             urns[index - 1] if index else None,
             urns[index + 1] if index + 1 < len(urns) else None, index),
        )
        for field, version_id, source_label in edition_fields:
            fragment = card.get(field)
            if fragment is None:
                continue
            conn.execute("INSERT INTO text_segments VALUES (?,?,?)", (
                urn, version_id, _fragment_html(work, fragment, source_label)))
            card_for_source[fragment["source_fragment_urn"]] = card["label"]
    for field, version_id, _ in edition_fields:
        if version_id not in version_map:
            continue
        local_index = 0
        for card in cards:
            fragment = card.get(field)
            if fragment is not None:
                conn.execute("INSERT INTO edition_chapter_order VALUES (?,?,?,?,?,?)",
                             (textgroup, work_id, version_id, None,
                              card_for_source[fragment["source_fragment_urn"]], local_index))
                local_index += 1
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    catalog["works"][work_key] = {
        "textgroup": textgroup, "work": work_id, "title": work["title"],
        "source_title": work.get("source_title", work["title"]),
        "experimental_fragment": True, "fragmentary": True,
        "fragment_corpus": bool(work.get("fragment_corpus")),
        "evidence_only": not bool(cards), "status": work.get("status", "Fragmentary text"),
        "object_urn": work.get("object_urn"), "default_columns": min(3, len(versions)) or 1,
        "unit_labels": {"chapter": "Fragment alignment", "section": "Section"},
        "parts": [{"part": 1, "file": db_path.name, "books": [],
                   "chapters": [card["label"] for card in cards],
                   "bytes": db_path.stat().st_size,
                   "sha256": hashlib.sha256(db_path.read_bytes()).hexdigest()}],
        "versions": [{"canonical_id": _fragment_focus(textgroup, work_id, v["short_id"]),
                      "short_id": v["short_id"], "urn": v["edition_urn"],
                      "label": v["label"], "doc_type": "edition",
                      "text_class": "greek-text"} for v in versions],
        "annotations": {},
    }


def _aggregate_sophocles_work(pearson, nauck):
    """Build an author-level union; only unique exact text is aligned here."""
    pfrags = [dict(fragment) for fragment in pearson.get("fragments", [])]
    nfrags = [dict(fragment) for fragment in nauck.get("fragments", [])]
    pairs = align_sophocles_fragments(pfrags, nfrags, fuzzy=False)
    by_p = {id(p): n for p, n, _, _ in pairs}
    paired_n = {n["number"] for _, n, _, _ in pairs}
    cards = []
    for fragment in pfrags:
        other = by_p.get(id(fragment))
        if other:
            cards.append({"label": f"P{fragment['number']}=N{other['number']}",
                          "pearson": fragment, "nauck": other})
        else:
            cards.append({"label": f"P{fragment['number']}", "pearson": fragment})
    cards.extend({"label": f"N{f['number']}", "nauck": f}
                 for f in nfrags if f["number"] not in paired_n)
    return {
        "id": "sophocles-fragmenta", "work": "fragmenta",
        "title": "Sophocles, Fragments", "source_title": "FRAGMENTA",
        "object_urn": "urn:cts:greekLit:tlg0011.fragmenta",
        "fragments": pfrags + nfrags, "cards": cards,
        "versions": pearson["versions"] + nauck["versions"],
        "status": "Fragmentary text", "fragment_corpus": True,
    }


def _publish_sophocles_fragments(site_root, catalog):
    pearson_source = json.loads(SOPHOCLES_FRAGMENTS_PATH.read_text(encoding="utf-8"))
    nauck_source = build_play_level_fragments(
        SOPHOCLES_DATA_PATH, "tlg0011", SOPHOCLES_NAUCK, "Sophocles",
        "Greek (Nauck, 1889; OCR draft)", "August Nauck")
    dindorf_source = build_play_level_fragments(
        SOPHOCLES_DATA_PATH, "tlg0011", SOPHOCLES_DINDORF, "Sophocles",
        "Greek (Dindorf, 1893; OCR draft)", "Wilhelm Dindorf")
    if dindorf_source:
        works, concordance = merge_three_sophocles_work_views(
            pearson_source, nauck_source, dindorf_source)
        versions = (dindorf_source["versions"] + nauck_source["versions"]
                    + pearson_source["versions"])
        edition_fields = (
            ("dindorf", SOPHOCLES_DINDORF, "Dindorf’s sources and notes"),
            ("nauck", SOPHOCLES_NAUCK, "Nauck’s notes and apparatus"),
            ("pearson", SOPHOCLES_PEARSON, "Pearson’s notes and apparatus"),
        )
    else:
        pearson = materialize_work_views(pearson_source)
        nauck = materialize_work_views(nauck_source)
        works, concordance = merge_sophocles_work_views(pearson, nauck)
        versions = nauck_source["versions"] + pearson_source["versions"]
        edition_fields = (
            ("nauck", SOPHOCLES_NAUCK, "Nauck’s notes and apparatus"),
            ("pearson", SOPHOCLES_PEARSON, "Pearson’s notes and apparatus"),
        )
    catalog["works"] = {
        key: value for key, value in catalog.get("works", {}).items()
        if not ((value.get("fragmentary") or value.get("fragment_corpus"))
                and value.get("textgroup") == "tlg0011")
    }
    for work in works.values():
        _write_aligned_fragment_work(
            site_root, catalog, work, edition_fields=edition_fields)
    catalog.setdefault("authors", {})["tlg0011"] = "Sophocles"
    browser_data = {
        "schema_version": 5, "textgroup": "tlg0011", "author": "Sophocles",
        "corpus_title": "Fragments", "versions": versions,
        "works": works,
        "collections": [{"id": "sophocles-fragments", "title": "Fragments",
                         "author": "Sophocles", "textgroup": "tlg0011",
                         "members": list(works)}],
        "scope": {"play_headings": len(works),
                  "dindorf_fragments": len(dindorf_source["fragments"]) if dindorf_source else 0,
                  "nauck_fragments": len(nauck_source["fragments"]),
                  "pearson_fragments": len(pearson_source["fragments"]),
                  "aligned_fragment_pairs": len(concordance)},
        "editorial_note": (
            "Dindorf, Nauck, and Pearson retain their own fragment numbers. "
            "Shared cards record only text-supported correspondences; unmatched "
            "fragments remain visible as edition-specific cards."),
    }
    (site_root / "tlg0011-fragment-collections.json").write_text(
        json.dumps(browser_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (site_root / "tlg0011-fragment-concordance.json").write_text(
        json.dumps({"schema_version": 1,
                    "editions": ([SOPHOCLES_DINDORF, SOPHOCLES_NAUCK, SOPHOCLES_PEARSON]
                                 if dindorf_source else [SOPHOCLES_NAUCK, SOPHOCLES_PEARSON]),
                    "matches": concordance}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return len(works)


def _publish_euripides_fragments(site_root, catalog):
    """Publish Dindorf and Nauck with independent numbering and shared cards."""
    dindorf_source = build_play_level_fragments(
        EURIPIDES_DATA_PATH, "tlg0006", EURIPIDES_DINDORF, "Euripides",
        "Greek (Dindorf, 1893; OCR draft)", "Wilhelm Dindorf")
    nauck_source = build_play_level_fragments(
        EURIPIDES_DATA_PATH, "tlg0006", EURIPIDES_NAUCK, "Euripides",
        "Greek (Nauck, 1889; OCR draft)", "August Nauck")
    works, concordance = merge_euripides_work_views(dindorf_source, nauck_source)
    versions = dindorf_source["versions"] + nauck_source["versions"]
    fields = (
        ("dindorf", EURIPIDES_DINDORF, "Dindorf’s sources and notes"),
        ("nauck", EURIPIDES_NAUCK, "Nauck’s notes and apparatus"),
    )
    catalog["works"] = {
        key: value for key, value in catalog.get("works", {}).items()
        if not ((value.get("fragmentary") or value.get("fragment_corpus"))
                and value.get("textgroup") == "tlg0006")
    }
    for work in works.values():
        _write_aligned_fragment_work(
            site_root, catalog, work, textgroup="tlg0006", edition_fields=fields)
    catalog.setdefault("authors", {})["tlg0006"] = "Euripides"
    browser_data = {
        "schema_version": 5, "textgroup": "tlg0006", "author": "Euripides",
        "corpus_title": "Fragments", "versions": versions, "works": works,
        "collections": [{"id": "euripides-fragments", "title": "Fragments",
                         "author": "Euripides", "textgroup": "tlg0006",
                         "members": list(works)}],
        "scope": {"work_views": len(works),
                  "dindorf_fragments": len(dindorf_source["fragments"]),
                  "nauck_fragments": len(nauck_source["fragments"]),
                  "aligned_fragment_pairs": len(concordance)},
        "editorial_note": (
            "Dindorf 1893 and Nauck 1889 retain their own printed fragment numbers. "
            "Shared cards record conservative, text-supported correspondences; "
            "unmatched fragments remain visible as edition-specific cards."),
    }
    (site_root / "tlg0006-fragment-collections.json").write_text(
        json.dumps(browser_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (site_root / "tlg0006-fragment-concordance.json").write_text(
        json.dumps({"schema_version": 1,
                    "editions": [EURIPIDES_DINDORF, EURIPIDES_NAUCK],
                    "matches": concordance}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return len(works)


def _publish_aristophanes_fragments(site_root, catalog):
    """Publish Dindorf's Aristophanic fragments as TEI-derived work views."""
    if not ARISTOPHANES_DATA_PATH.exists():
        return 0
    source = build_play_level_fragments(
        ARISTOPHANES_DATA_PATH, "tlg0019", "dindorf1893-grc1",
        "Aristophanes", "Greek (Dindorf, 1893; OCR draft)",
        "Wilhelm Dindorf")
    return _publish_fragment_source(
        site_root, catalog, ARISTOPHANES_DATA_PATH,
        xml_builder=lambda _: source,
        publish_corpus=False,
    )


def _publish_nauck_author_corpora(site_root, catalog):
    published = 0
    for spec in NAUCK_AUTHORS:
        if spec.textgroup in {"tlg0011", "tlg0006"}:
            continue  # Published above as aligned multi-edition corpora.
        source = (CORPUS_DATA_DIR / spec.textgroup / "fragments" / "source" /
                  f"{spec.textgroup}.fragmenta.nauck1889grc1.xml")
        if not source.exists():
            continue
        _publish_fragment_source(
            site_root, catalog, source, xml_builder=build_nauck_author_fragments,
            include_empty_works=True,
        )
        published += 1
    return published


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
    sophocles_fragments = (_publish_sophocles_fragments(site_root, catalog)
                           if SOPHOCLES_FRAGMENTS_PATH.exists() else 0)
    euripides_fragments = _publish_euripides_fragments(site_root, catalog)
    aristophanes_fragments = _publish_aristophanes_fragments(site_root, catalog)
    nauck_authors = _publish_nauck_author_corpora(site_root, catalog) + 1
    claudel = _publish_claudel(site_root, catalog)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total_fragments = (fragments + sophocles_fragments + euripides_fragments
                       + aristophanes_fragments)
    print(f"  ✓ Published experimental collections: {total_fragments} fragment works "
          f"({sophocles_fragments} Sophocles, {euripides_fragments} Euripides, "
          f"{aristophanes_fragments} Aristophanes), "
          f"{nauck_authors} Nauck author corpora, "
          f"{claudel} Claudel versions")
    return {"fragment_works": fragments, "fragment_authors": nauck_authors,
            "claudel_versions": claudel}
