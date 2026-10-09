"""Parse and register Dindorf's Aristophanic fragment TEI."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DINDORF = "dindorf1893-grc1"
TEXTGROUP = "tlg0019"


def _text(element):
    return " ".join("".join(element.itertext()).split())


def build_dindorf(source: Path) -> dict:
    source = Path(source)
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition_urn = edition.get("n")
    fragments, works, attributions = [], {}, []
    for container in edition.xpath(
        "./tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        work = container.get("n")
        container_id = container.get(XML_ID)
        object_urn = container.get("corresp")
        title = container.xpath("string(tei:head[1])", namespaces=NS).strip()
        targets = []
        for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            number = fragment.get("n")
            source_urn = f"{edition_urn}:{work}.{number}"
            lines = [
                {"ref": line.get("n") or str(index), "source_id": line.get(XML_ID),
                 "text": _text(line)}
                for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1)
            ]
            context = "\n\n".join(
                _text(child) for child in fragment
                if etree.QName(child).localname not in {"head", "lg"} and _text(child)
            )
            fragments.append({
                "number": number, "source_id": fragment.get(XML_ID),
                "edition": DINDORF, "source_fragment_urn": source_urn,
                "same_as": [], "lines": lines, "context": context,
                "play_title": title, "play_work": work, "play_urn": object_urn,
            })
            targets.append(source_urn)
        works[container_id] = {
            "id": container_id, "work": work, "object_urn": object_urn,
            "title": title, "source_title": title, "source": source.name,
            "selector": f"#{container_id}",
            "record_type": ("fragmentary_play" if container.get("subtype") == "play"
                            else "fragment_collection"),
            "introduction": "",
        }
        if targets:
            attribution_id = f"{DINDORF}-{TEXTGROUP}-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": "Wilhelm Dindorf", "edition": DINDORF,
                "play_urn": object_urn, "corresp": targets,
            })
    return {
        "schema_version": 4, "textgroup": TEXTGROUP, "author": "Aristophanes",
        "corpus_title": "Aristophanes, Fragments",
        "source_label": "Dindorf's sources and notes",
        "canonical_source": source.name, "source_format": "tei",
        "versions": [{"short_id": DINDORF, "edition_urn": edition_urn,
                      "label": "Greek (Dindorf, 1893; OCR draft)",
                      "source": source.name}],
        "fragments": fragments, "works": works, "attributions": attributions,
    }


def update_registry(registry_path: Path, dindorf_path: Path) -> None:
    registry_path, dindorf_path = Path(registry_path), Path(dindorf_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = build_dindorf(dindorf_path)
    edition = {
        "path": str(dindorf_path),
        "urn": f"urn:cts:greekLit:{TEXTGROUP}.fragmenta.{DINDORF}",
        "label": "Greek (Dindorf, 1893; OCR draft)",
        "class": "greek-text", "format": "tei_fragment_collection",
        "corresp_axis": "work",
    }
    registry[f"{TEXTGROUP}.fragmenta"] = {
        "textgroup": TEXTGROUP, "work": "fragmenta",
        "title": "Aristophanes, Fragments", "fragmentary": True,
        "fragment_corpus": True, "record_type": "fragment_collection",
        "editions": {}, "appcrits": {}, "translations": {}, "commentaries": {},
        "treebanks": {}, "fragment_editions": {DINDORF: edition},
        "object_urn": f"urn:cts:greekLit:{TEXTGROUP}.fragmenta",
        "source_edition": "dindorf1893",
    }
    for work in source["works"].values():
        slug = work["work"]
        record = registry.setdefault(f"{TEXTGROUP}.{slug}", {
            "textgroup": TEXTGROUP, "work": slug, "title": work["source_title"],
            "fragmentary": True, "record_type": work["record_type"],
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {}, "fragment_editions": {},
            "object_urn": work["object_urn"],
        })
        record.setdefault("fragment_editions", {})[DINDORF] = edition
        record["fragmentary"] = True
        record["source_title"] = work["source_title"]
        record["source_edition"] = "dindorf1893"
        if work["record_type"] == "fragment_collection":
            record["fragment_collection"] = True
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
