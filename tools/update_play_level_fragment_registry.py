#!/usr/bin/env python3
"""Replace aggregate drama-fragment registry records with canonical CTS works."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree


REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "work_registry.json"
DATA = Path("/Users/gcrane/github/grcnewxml/data")
TEXTGROUPS = ("tlg0011", "tlg0006", "tlg0019")
CTS_NS = {"ti": "http://chs.harvard.edu/xmlns/cts"}
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def records_for(textgroup):
    records = {}
    root = DATA / textgroup
    for metadata_path in sorted(root.glob("*/__cts__.xml")):
        edition_paths = sorted(metadata_path.parent.glob(f"{textgroup}.*.*grc1.xml"))
        if not edition_paths:
            continue
        metadata = etree.parse(str(metadata_path))
        work_urn = metadata.getroot().get("urn")
        if not work_urn or not work_urn.startswith(f"urn:cts:greekLit:{textgroup}."):
            continue
        slug = work_urn.rsplit(".", 1)[-1]
        # Existing numbered TLG works are surviving plays, not members of the
        # newly generated descriptive-ID fragment package.
        if slug.startswith("tlg"):
            continue
        title = metadata.xpath("string(/ti:work/ti:title[1])", namespaces=CTS_NS).strip()
        editions = {}
        object_urn = None
        for edition_path in edition_paths:
            short_id = edition_path.stem.split(".")[-1]
            edition_urn = f"urn:cts:greekLit:{textgroup}.{slug}.{short_id}"
            label = metadata.xpath(
                "string(/ti:work/ti:edition[@urn=$urn]/ti:label[1])",
                namespaces=CTS_NS, urn=edition_urn).strip()
            editions[short_id] = {
                "path": str(edition_path), "urn": edition_urn,
                "label": label or short_id, "class": "greek-text",
                "format": "tei_fragment_work", "corresp_axis": "fragment",
            }
            if object_urn is None:
                tree = etree.parse(str(edition_path))
                object_urn = tree.xpath(
                    "string(//tei:div[@type='edition']/@corresp)",
                    namespaces=TEI_NS).strip()
        record_type = ("fragment_collection"
                       if "fragmentarycollections" in (object_urn or "")
                       else "fragmentary_play")
        record = {
            "textgroup": textgroup, "work": slug, "title": title,
            "fragmentary": True, "record_type": record_type,
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {},
            "fragment_editions": editions, "object_urn": object_urn,
            "source_title": title,
            "source_edition": ("multiple-fragment-editions"
                               if len(editions) > 1
                               else next(iter(editions)).rsplit("-grc", 1)[0]),
        }
        if record_type == "fragment_collection":
            record["fragment_collection"] = True
        records[f"{textgroup}.{slug}"] = record
    return records


def main():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for textgroup in TEXTGROUPS:
        canonical = records_for(textgroup)
        stale = {key for key, record in registry.items()
                 if key.startswith(textgroup + ".")
                 and (record.get("fragmentary") or record.get("fragment_corpus"))}
        retained = [(key, value) for key, value in registry.items()
                    if key not in stale and key not in canonical]
        core = [key for key, value in retained
                if value.get("textgroup") == textgroup]
        insert_after = core[-1] if core else None
        updated = {}
        inserted = False
        for key, value in retained:
            updated[key] = value
            if key == insert_after:
                updated.update(canonical)
                inserted = True
        if not inserted:
            updated.update(canonical)
        registry = updated
        print(textgroup, len(canonical), "play-level registry records")
    REGISTRY.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
