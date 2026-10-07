#!/usr/bin/env python3
"""Audit Potter Euripides OCR coverage and card-order alignment."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
import rebuild_euripides as repair


NS = repair.NS
SPEAKER_PREFIX = re.compile(r"^(?:[A-ZÆŒΙ10]{2,}(?:\.\s*|\s+))+", re.UNICODE)
STOP_STARTS = {
    ("tlg002", 128): "the dying person was sacred",
    ("tlg002", 131): "suppose that the Dean dipped",
    ("tlg009", 449): "basket called κανῶν",
    ("tlg008", 376): "358. This alludes",
    ("tlg008", 377): "rather sow,",
    ("tlg008", 386): "Tyrwhitt with great reason",
    ("tlg008", 402): "persons struck with lightening",
    ("tlg010", 66): "Carmeli translates it thus",
    ("tlg010", 93): "nour, and even of royalty",
    ("tlg012", 287): "ἐξανίσανται:",
    ("tlg014", 222): "afterwards finished by the Lacedemonians",
    ("tlg014", 268): "suspect the text is corrupted",
    ("tlg015", 297): "This protended spear",
    ("tlg015", 310): "swelling with extravagant conceptions",
    ("tlg016", 334): "solution of this fable",
    ("tlg016", 352): "Ægypt it wisely and humanely intended",
    ("tlg018", 15): "⚫meration of the ships",
    ("tlg018", 39): "conversation with him, addresses himself",
    ("tlg018", 44): "* See Pindar's first Olympic Ode",
}

HEADER_KEYS = {
    repair.key(value)
    for value in (
        "The Bacchae", "Ion", "Alcestis", "Medea", "Hippolytus",
        "The Phoenician Virgins", "The Supplicants", "Hercules",
        "The Heraclidae", "Iphigenia in Aulis", "Rhesus",
        "The Trojan Dames", "Hecuba", "Helena", "Electra", "Orestes",
        "Iphigenia in Tauris", "Andromache",
    )
}


def clean_ocr_line(value: str) -> str:
    value = value.strip()
    value = SPEAKER_PREFIX.sub("", value).strip()
    value = re.sub(r"^[•⚫]\s*", "", value)
    value = re.sub(r"^[123](?:st|nd|d)?\.\s*", "", value, flags=re.I)
    value = re.sub(r"^1(?=\s|,)", "I", value)
    return value


def dramatic_lines(work: str, pages: dict[int, list[str]]) -> list[dict[str, object]]:
    low, high = repair.PLAY_PAGES[work]
    rows = []
    for page in range(low, high + 1):
        raw = [line.strip() for line in pages.get(page, []) if line.strip()]
        range_info = repair.range_on_page(raw, page)
        if not range_info:
            continue
        _, _, start = range_info
        end = len(raw)
        for index in range(start + 1, len(raw)):
            value = raw[index]
            if repair.NOTE_RE.match(value):
                end = index
                break
            stop = STOP_STARTS.get((work, page))
            if stop and value.startswith(stop):
                end = index
                break
        for value in raw[start + 1:end]:
            if not repair.eligible_verse_line(value):
                continue
            cleaned = clean_ocr_line(value)
            if repair.word_count(cleaned) < 2:
                continue
            if repair.key(cleaned) in HEADER_KEYS:
                continue
            if re.fullmatch(r"(?:1st|2d)\.?\s*SEM(?:ICH)?\.?", cleaned, re.I):
                continue
            if "Printer, Oxford" in cleaned or "chorus exitsenter" in cleaned.lower():
                continue
            rows.append({"page": page, "raw": value, "text": cleaned, "key": repair.key(cleaned)})
    return rows


def xml_lines(path: Path) -> tuple[etree._ElementTree, list[dict[str, object]]]:
    tree = etree.parse(str(path))
    rows = []
    card = None
    for element in tree.xpath("//t:body//*[self::t:milestone or self::t:l or self::t:stage]", namespaces=NS):
        if etree.QName(element).localname == "milestone" and element.get("unit") == "card":
            card = element.get("n")
        elif etree.QName(element).localname in {"l", "stage"}:
            text = repair.line_text(element)
            rows.append({"element": element, "n": element.get("n"), "card": card, "text": text, "key": repair.key(text)})
    return tree, rows


def align(ocr: list[dict[str, object]], xml: list[dict[str, object]]) -> list[int | None]:
    """Monotonic sequence match; several OCR physical lines may share an XML line."""
    ocr_keys = [row["key"] for row in ocr]
    xml_keys = [row["key"] for row in xml]
    result: list[int | None] = [None] * len(ocr)
    matcher = SequenceMatcher(None, ocr_keys, xml_keys, autojunk=False)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            result[block.a + offset] = block.b + offset

    # SequenceMatcher deliberately optimizes whole matching blocks.  In this
    # material that can strand perfectly identical lines when refrains or
    # repeated speaker formulae make a different block globally preferable.
    # Rescue exact lines inside their already-established monotonic bounds
    # before attempting any fuzzy match.
    positions: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(xml_keys):
        if key:
            positions[key].append(index)

    for _ in range(3):
        changed = False
        previous_exact = [-1] * len(result)
        current = -1
        for index, value in enumerate(result):
            if value is not None:
                current = value
            previous_exact[index] = current
        following_exact = [len(xml)] * len(result)
        current = len(xml)
        for index in range(len(result) - 1, -1, -1):
            if result[index] is not None:
                current = result[index]
            following_exact[index] = current
        for row_index, key in enumerate(ocr_keys):
            if result[row_index] is not None or not key:
                continue
            low = previous_exact[row_index]
            high = following_exact[row_index]
            candidates = [candidate for candidate in positions.get(key, []) if low <= candidate <= high]
            if candidates:
                # Position within the gap breaks ties between repeated lines.
                left_ocr = row_index
                while left_ocr >= 0 and result[left_ocr] is None:
                    left_ocr -= 1
                right_ocr = row_index
                while right_ocr < len(result) and result[right_ocr] is None:
                    right_ocr += 1
                if left_ocr >= 0 and right_ocr < len(result) and high > low:
                    fraction = (row_index - left_ocr) / (right_ocr - left_ocr)
                    expected = low + fraction * (high - low)
                else:
                    expected = low if low >= 0 else high
                result[row_index] = min(candidates, key=lambda candidate: abs(candidate - expected))
                changed = True
        if not changed:
            break

    previous = [-1] * len(result)
    current = -1
    for index, value in enumerate(result):
        if value is not None:
            current = value
        previous[index] = current
    following = [len(xml)] * len(result)
    current = len(xml)
    for index in range(len(result) - 1, -1, -1):
        if result[index] is not None:
            current = result[index]
        following[index] = current

    for row_index, row in enumerate(ocr):
        if result[row_index] is not None:
            continue
        low = max(0, previous[row_index])
        high = min(len(xml), following[row_index] + 1)
        best_index = None
        best_score = 0.0
        for index in range(low, high):
            key, other = row["key"], xml[index]["key"]
            if not other:
                continue
            if key in other or other in key:
                score = min(len(key), len(other)) / max(len(key), len(other))
            else:
                score = SequenceMatcher(None, key, other).ratio()
            if score > best_score:
                best_index, best_score = index, score
        if best_index is not None and best_score >= 0.72:
            result[row_index] = best_index
    return result


def audit(work: str, xml_path: Path, pages: dict[int, list[str]]) -> dict[str, object]:
    ocr = dramatic_lines(work, pages)
    _, xml = xml_lines(xml_path)
    matches = align(ocr, xml)
    missing = [row for row, match in zip(ocr, matches) if match is None]
    matched_cards = [xml[match]["card"] for match in matches if match is not None]
    regressions = sum(
        int(a) > int(b)
        for a, b in zip(matched_cards, matched_cards[1:])
        if a and b and a.isdigit() and b.isdigit()
    )
    missing_by_page = defaultdict(int)
    for row in missing:
        missing_by_page[str(row["page"])] += 1
    return {
        "work": work,
        "ocr_lines": len(ocr),
        "xml_lines": len(xml),
        "matched_ocr_lines": len(ocr) - len(missing),
        "missing_ocr_lines": len(missing),
        "coverage_percent": round(100 * (len(ocr) - len(missing)) / max(1, len(ocr)), 2),
        "card_order_regressions": regressions,
        "missing_by_page": dict(missing_by_page),
        "missing_samples": missing[:30],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_dir", type=Path, help="The grcnewxml data/tlg0006 directory")
    parser.add_argument("--ocr1", type=Path, required=True)
    parser.add_argument("--ocr2", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    ocr1 = repair.ocr_pages(args.ocr1)
    ocr2 = repair.ocr_pages(args.ocr2)
    volume1 = {"tlg002", "tlg003", "tlg004", "tlg005", "tlg008", "tlg009", "tlg010", "tlg015", "tlg017"}
    reports = []
    for work in sorted(repair.PLAY_PAGES):
        xml_path = args.xml_dir / work / f"tlg0006.{work}.potter1781-eng1.xml"
        reports.append(audit(work, xml_path, ocr1 if work in volume1 else ocr2))
    rendered = json.dumps(reports, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
