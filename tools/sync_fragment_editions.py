#!/usr/bin/env python3
"""Register play-level TEI fragment editions in PMV's work registry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
NS = {"tei": TEI, "cts": CTS}

ROMAN_VOLUMES = {
    "1": "I", "i": "I", "2": "II", "ii": "II",
    "3": "III", "iii": "III", "4": "IV", "iv": "IV",
}


def edition_label(metadata: Path, urn: str, fallback: str) -> str:
    root = ET.parse(metadata).getroot()
    for edition in root.findall("cts:edition", NS):
        if edition.get("urn") == urn:
            return edition.findtext("cts:label", default=fallback, namespaces=NS)
    return fallback


def source_volume(source: Path) -> Optional[str]:
    root = ET.parse(source).getroot()
    scope = root.find(".//tei:biblScope[@unit='volume']", NS)
    if scope is None or not (scope.text or "").strip():
        return None
    value = (scope.text or "").strip().lower().rstrip(".")
    if value.startswith("vol."):
        value = value[4:].strip()
    elif value.startswith("vol"):
        value = value[3:].strip()
    return ROMAN_VOLUMES.get(value, value.upper())


def label_with_volume(label: str, volume: Optional[str]) -> str:
    if not volume or "vol." in label.lower() or "vols." in label.lower():
        return label
    marker = "; OCR draft)"
    if marker in label:
        return label.replace(marker, f", vol. {volume}{marker}", 1)
    closing = label.find(")")
    if closing >= 0:
        return f"{label[:closing]}, vol. {volume}{label[closing:]}"
    return f"{label} — vol. {volume}"


def sync(registry_path: Path, data_dir: Path, version: str, default_label: str) -> int:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = sorted(data_dir.glob(f"*/*/*.{version}.xml"))
    source_paths = {str(source.resolve()) for source in sources}
    stale_records = []
    for key, record in registry.items():
        edition = record.get("fragment_editions", {}).get(version)
        if edition and edition.get("path") not in source_paths:
            record["fragment_editions"].pop(version)
            if (not record["fragment_editions"]
                    and not any(record.get(field) for field in (
                        "editions", "appcrits", "translations", "commentaries", "treebanks"))
                    and record.get("source_edition") == "multiple-fragment-editions"):
                stale_records.append(key)
    for key in stale_records:
        registry.pop(key)
    count = 0
    for source in sources:
        root = ET.parse(source).getroot()
        edition = root.find(".//tei:div[@type='edition']", NS)
        if edition is None:
            raise ValueError(f"No edition division: {source}")
        urn = edition.get("n")
        textgroup, work = urn.split(":")[-1].split(".")[:2]
        key = f"{textgroup}.{work}"
        title = edition.findtext("tei:head", default=work, namespaces=NS)
        object_urn = edition.get("corresp") or (
            f"urn:cite2:perseus:fragmentaryplays.v1:{textgroup}_{work}")
        record = registry.setdefault(key, {
            "textgroup": textgroup, "work": work, "title": title,
            "fragmentary": True, "record_type": "fragmentary_play",
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {}, "fragment_editions": {},
            "object_urn": object_urn, "source_title": title,
            "source_edition": "multiple-fragment-editions",
        })
        volume = source_volume(source)
        label = label_with_volume(
            edition_label(source.parent / "__cts__.xml", urn, default_label), volume)
        record.setdefault("fragment_editions", {})[version] = {
            "path": str(source.resolve()), "urn": urn,
            "label": label, "source_volume": volume,
            "class": "greek-text", "format": "tei_fragment_work",
            "corresp_axis": "fragment",
        }
        record["fragmentary"] = True
        record["object_urn"] = object_urn
        record["source_title"] = title
        record["source_edition"] = "multiple-fragment-editions"
        count += 1
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--label", required=True)
    parser.add_argument("--registry", type=Path,
                        default=Path(__file__).resolve().parents[1] / "work_registry.json")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get(
        "GRCNEWFRAGMENTS_DATA_DIR", "/Users/gcrane/github/grcnewfragments/data")))
    args = parser.parse_args()
    count = sync(args.registry, args.data, args.version, args.label)
    print(f"Registered {count} {args.version} fragment editions")


if __name__ == "__main__":
    main()
