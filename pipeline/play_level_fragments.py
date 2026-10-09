"""Read canonical play-level CTS fragment editions into PMV's transient model."""

from __future__ import annotations

from pathlib import Path

from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _text(element):
    return " ".join("".join(element.itertext()).split())


def build(data_root: Path, textgroup: str, version: str, author: str,
          label: str, editor: str) -> dict:
    data_root = Path(data_root)
    paths = sorted(data_root.glob(f"*/{textgroup}.*.{version}.xml"))
    if not paths:
        raise FileNotFoundError(
            f"No {textgroup} play-level {version} editions in {data_root}")
    fragments, works, attributions = [], {}, []
    for source in paths:
        tree = etree.parse(str(source))
        edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
        edition_urn = edition.get("n")
        work = edition_urn.split(":")[-1].split(".")[1]
        object_urn = edition.get("corresp")
        title = edition.xpath("string(tei:head[1])", namespaces=NS).strip()
        record_id = f"{author.lower()}-{version}-{work}"
        targets = []
        for fragment in edition.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            number = fragment.get("n")
            source_urn = f"{edition_urn}:{number}"
            lines = [
                {"ref": line.get("n") or str(index),
                 "source_id": line.get(XML_ID), "text": _text(line)}
                for index, line in enumerate(
                    fragment.xpath(".//tei:l", namespaces=NS), 1)
            ]
            context = "\n\n".join(
                _text(child) for child in fragment
                if etree.QName(child).localname not in {"head", "lg"}
                and _text(child)
            )
            record = {
                "number": number, "source_id": fragment.get(XML_ID),
                "edition": version, "source_fragment_urn": source_urn,
                "same_as": (fragment.get("sameAs") or "").split(),
                "lines": lines, "context": context,
                "play_title": title, "play_work": work,
                "play_urn": object_urn,
            }
            fragments.append(record)
            targets.append(source_urn)
        record_type = ("fragment_collection"
                       if "fragmentarycollections" in (object_urn or "")
                       else "fragmentary_play")
        works[record_id] = {
            "id": record_id, "work": work, "object_urn": object_urn,
            "title": title, "source_title": title, "source": source.name,
            "selector": f"{source.name}#edition", "record_type": record_type,
            "introduction": "\n\n".join(
                _text(child) for child in edition
                if etree.QName(child).localname not in {"head", "div", "pb"}
                and _text(child)),
        }
        if targets:
            attribution_id = f"{version}-{textgroup}-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": editor, "edition": version,
                "play_urn": object_urn, "corresp": targets,
            })
    return {
        "schema_version": 5, "textgroup": textgroup, "author": author,
        "corpus_title": f"{author}, Fragments", "source_label": label,
        "canonical_source": str(data_root), "source_format": "tei-play-level",
        "versions": [{"short_id": version, "edition_urn": None,
                      "label": label, "source": str(data_root)}],
        "fragments": fragments, "works": works,
        "attributions": attributions,
    }
