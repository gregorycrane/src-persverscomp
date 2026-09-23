#!/usr/bin/env python3
"""Extract passage-level place mentions from a saved ToposText work page.

ToposText work pages encode a CTS citation on each paragraph and expose the
linked place id, mention type, and coordinates on each annotated anchor.  The
result uses the CSV schema consumed by pipeline.places.topostext.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from lxml import html


FIELDS = (
    "mention_type",
    "mention_name",
    "citation",
    "place_id",
    "place_name",
    "lat",
    "lon",
    "feature_type",
)
PLACE_ID_RE = re.compile(r"/place/([^/?#]+)")
MENTION_TYPES = {"place", "ethnic", "demonym", "person"}


def _feature_index(gazetteer_path: Path) -> dict[str, dict[str, str]]:
    with gazetteer_path.open(encoding="utf-8") as source:
        payload = json.load(source)

    result = {}
    for feature in payload.get("features", []):
        match = PLACE_ID_RE.search(feature.get("@id", ""))
        if not match:
            continue
        types = feature.get("types") or []
        result[match.group(1)] = {
            "place_name": (feature.get("properties") or {}).get("title", ""),
            "feature_type": types[0].get("sourceLabel", "") if types else "",
        }
    return result


def extract(html_path: Path, gazetteer_path: Path, work_urn: str) -> list[dict[str, str]]:
    gazetteer = _feature_index(gazetteer_path)
    document = html.parse(str(html_path))
    prefix = work_urn + ":"
    rows = []

    for paragraph in document.xpath("//p[starts-with(@id, $prefix)]", prefix=prefix):
        citation = paragraph.get("id", "")[len(prefix):]
        if not citation:
            continue
        for anchor in paragraph.xpath(".//a[contains(@about, '/place/')]"):
            mention_type = next(
                (name for name in (anchor.get("class") or "").split()
                 if name in MENTION_TYPES),
                "place",
            )
            match = PLACE_ID_RE.search(anchor.get("about", ""))
            if not match:
                continue
            place_id = match.group(1)
            feature = gazetteer.get(place_id, {})
            mention_name = " ".join(anchor.text_content().split())
            rows.append({
                "mention_type": mention_type,
                "mention_name": mention_name,
                "citation": citation,
                "place_id": place_id,
                # A few live ToposText ids are newer than a downloaded
                # gazetteer snapshot. The anchor still supplies a useful
                # label until the next gazetteer refresh.
                "place_name": feature.get("place_name") or mention_name,
                "lat": anchor.get("lat", ""),
                "lon": anchor.get("long", ""),
                "feature_type": feature.get("feature_type", ""),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path, help="saved ToposText work HTML")
    parser.add_argument("gazetteer", type=Path, help="ToposText JSON-LD gazetteer")
    parser.add_argument("output", type=Path, help="destination citations CSV")
    parser.add_argument("--work-urn", required=True,
                        help="work-level CTS URN, without passage suffix")
    args = parser.parse_args()

    rows = extract(args.html, args.gazetteer, args.work_urn)
    if not rows:
        raise SystemExit(f"No place annotations found for {args.work_urn}")
    missing_coordinates = sum(not row["lat"] or not row["lon"] for row in rows)
    if missing_coordinates:
        raise SystemExit(f"Refusing output: {missing_coordinates} rows lack coordinates")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows):,} mentions in "
          f"{len({row['citation'] for row in rows}):,} passages, covering "
          f"{len({row['place_id'] for row in rows}):,} places, to {args.output}")


if __name__ == "__main__":
    main()
