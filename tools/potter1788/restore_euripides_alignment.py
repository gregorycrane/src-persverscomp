#!/usr/bin/env python3
"""Restore reviewed Potter Euripides OCR omissions to CTS card intervals.

This is deliberately conservative: note prose, running heads, stage labels,
and printer debris are excluded explicitly.  Restored dramatic lines receive
card-level (not invented line-level) CTS correspondence and cert="low".
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
import rebuild_euripides as base
import audit_euripides_alignment as audit


NS = base.NS
Q = base.Q
VOLUME1 = {"tlg002", "tlg003", "tlg004", "tlg005", "tlg008", "tlg009", "tlg010", "tlg015", "tlg017"}

# Lines proved not to be dramatic text by inspection of their OCR context.
EXCLUDE = {
    "tlg004": {506: ["The Chorus. The Heraclidae."]},
    "tlg006": {
        483: ["A river of Thessaly."],
        499: ["The tragedies", "29 1951 else czek", "21 1962, Wrm, Countryman"],
    },
    "tlg010": {
        67: ["lopt the head:", "Pierson minima", "ties: δαλὸν"],
        70: ["obedience driven", "part of the rock"],
    },
    "tlg012": {302: ["To Orestes."], 322: ["and POLLUX."]},
    "tlg013": {
        419: ["from mater"], 425: ["914."], 427: ["Pointing to Pylades."],
        432: ["To Orestes and Pylades."],
    },
    "tlg014": {
        254: ["at the tomb."], 256: ["THEOCLYMENUS"],
        258: ["they held", "second Antistrophe"],
        267: ["bonnd around"], 270: ["and POLLUX."],
        272: ["From the bleak pole", "Mold the round hail", "But from the breezy",
              "The fragrant murmurs", "This grace peculiar", "To thee the son",
              "Fenton", "Elysian field", "island of the blest", "earth's green end",
              "where this happy", "mentators are more", "translate it albam",
              "old name of Britain"],
    },
    "tlg015": {
        297: ["Her seven slain", "Their hands dismiss", "But with protended", "Pierce the tough"],
        302: ["The Ph"], 315: ["The Ph"],
        319: ["The Ph"], 323: ["The Ph"],
        344: ["he appears", "gal power", "resign:", "has done", "side;", "Regnum",
              "Mala,", "as Seneca", "more moderate", "expresses a true", "reconciled",
              "pressed a concern", "their former"],
        355: ["The Ph"],
    },
    "tlg016": {376: ["to 2d SEMICHORUS."], 384: ["above, CHORUS."]},
    "tlg018": {11: ["and Teucer sons"]},
    "tlg019": {99: ["of RHESUS at a distance."], 107: ["to Minerva"]},
}


def excluded(work: str, row: dict[str, object]) -> bool:
    value = str(row["text"])
    value_key = base.key(value)
    return any(
        value_key.startswith(base.key(prefix))
        for prefix in EXCLUDE.get(work, {}).get(int(row["page"]), [])
    )


def canonical_number(row: dict[str, object] | None) -> float | None:
    if not row:
        return None
    element = row["element"]
    values = re.findall(r":(\d+(?:\.\d+)?)", element.get("corresp", ""))
    if values:
        return float(values[-1])
    value = row.get("card")
    return float(value) if value and str(value).isdigit() else None


def speaker_prefix(raw: str) -> tuple[str | None, str]:
    match = re.match(r"^((?:[A-ZÆŒΙΟΡΗΧ10]{2,}(?:\.\s*|\s+))+)(.*)$", raw.strip())
    if not match:
        return None, raw.strip()
    label = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(".")
    label = label.replace("10Ν", "ION").replace("ΙΟΝ", "ION").replace("ΙΡΗ", "IPH")
    return label.title(), match.group(2).strip()


def direct_child(container: etree._Element, element: etree._Element) -> etree._Element:
    current = element
    while current.getparent() is not container:
        current = current.getparent()
    return current


def card_for_position(cards: list[int], number: float) -> int:
    eligible = [card for card in cards if card <= number]
    return eligible[-1] if eligible else cards[0]


def insertion_reference(container: etree._Element, card: int, next_element: etree._Element | None) -> int:
    children = list(container)
    milestones = [
        (index, int(child.get("n")))
        for index, child in enumerate(children)
        if child.tag == Q("milestone") and child.get("unit") == "card" and child.get("n", "").isdigit()
    ]
    following = next((index for index, value in milestones if value > card), len(children))
    if next_element is not None:
        next_index = children.index(direct_child(container, next_element))
        if next_index < following:
            following = next_index
    return following


def split_before(container: etree._Element, element: etree._Element) -> int:
    """Split an enclosing speech so a new speech can precede one exact line."""
    speech = next(element.iterancestors(Q("sp")), None)
    if speech is None or speech.getparent() is not container:
        return list(container).index(direct_child(container, element))
    tail = etree.Element(Q("sp"), attrib=dict(speech.attrib))
    speaker = speech.find(Q("speaker"))
    if speaker is not None:
        tail.append(copy.deepcopy(speaker))
    children = list(speech)
    start = children.index(element)
    for child in children[start:]:
        speech.remove(child)
        tail.append(child)
    position = list(container).index(speech) + 1
    container.insert(position, tail)
    return position


def remove_displaced_duplicate(body: etree._Element, key: str) -> list[str]:
    removed = []
    for element in list(body.xpath(".//t:l | .//t:stage", namespaces=NS)):
        if base.key(base.line_text(element)) == key:
            removed.append(base.line_text(element))
            parent = element.getparent()
            parent.remove(element)
    return removed


def restore_work(work: str, xml_path: Path, ocr_pages: dict[int, list[str]]) -> dict[str, object]:
    tree, xml = audit.xml_lines(xml_path)
    body = tree.xpath("//t:body", namespaces=NS)[0]
    container = body.xpath(".//t:div[@type='translation']", namespaces=NS)[0]
    ocr = audit.dramatic_lines(work, ocr_pages)
    matches = audit.align(ocr, xml)
    missing_indexes = [i for i, match in enumerate(matches) if match is None and not excluded(work, ocr[i])]
    cards = sorted({int(row["card"]) for row in xml if row["card"] and str(row["card"]).isdigit()})
    restored = []
    displaced = []

    runs: list[list[int]] = []
    for index in missing_indexes:
        if not runs or index != runs[-1][-1] + 1:
            runs.append([])
        runs[-1].append(index)

    for run in runs:
        before_i = next((i for i in range(run[0] - 1, -1, -1) if matches[i] is not None), None)
        after_i = next((i for i in range(run[-1] + 1, len(matches)) if matches[i] is not None), None)
        before = xml[matches[before_i]] if before_i is not None else None
        after = xml[matches[after_i]] if after_i is not None else None
        low = canonical_number(before)
        high = canonical_number(after)
        if low is None:
            low = float(cards[0])
        if high is None or high < low:
            high = float(cards[-1])

        grouped: dict[int, list[tuple[int, dict[str, object]]]] = defaultdict(list)
        for offset, ocr_index in enumerate(run, 1):
            position = low + (high - low) * offset / (len(run) + 1)
            card = card_for_position(cards, position)
            grouped[card].append((ocr_index, ocr[ocr_index]))

        current_speaker = None
        if before is not None:
            speech = next(before["element"].iterancestors(Q("sp")), None)
            speaker = speech.find(Q("speaker")) if speech is not None else None
            current_speaker = base.text_of(speaker) if speaker is not None else None

        for card, rows in sorted(grouped.items()):
            if after is not None and str(after.get("card", "")) == str(card):
                reference = split_before(container, after["element"])
            else:
                reference = insertion_reference(container, card, after["element"] if after is not None else None)
            speech = etree.Element(Q("sp"), cert="low")
            speech.set("corresp", f"urn:cts:greekLit:tlg0006.{work}.perseus-grc2:{card}")
            active_speaker = None
            for ocr_index, row in rows:
                raw = str(row.get("raw", row["text"]))
                explicit, _ = speaker_prefix(raw)
                if explicit:
                    current_speaker = explicit
                if active_speaker is None:
                    active_speaker = current_speaker or "Unknown"
                    speaker = etree.SubElement(speech, Q("speaker"))
                    speaker.text = active_speaker
                elif current_speaker != active_speaker:
                    container.insert(reference, speech)
                    reference += 1
                    speech = etree.Element(Q("sp"), cert="low")
                    speech.set("corresp", f"urn:cts:greekLit:tlg0006.{work}.perseus-grc2:{card}")
                    active_speaker = current_speaker or "Unknown"
                    speaker = etree.SubElement(speech, Q("speaker"))
                    speaker.text = active_speaker
                duplicate = remove_displaced_duplicate(body, str(row["key"]))
                if duplicate:
                    displaced.extend(duplicate)
                line = etree.SubElement(speech, Q("l"), n=f"ocr-p{row['page']}-{ocr_index + 1}", cert="low")
                line.set("corresp", f"urn:cts:greekLit:tlg0006.{work}.perseus-grc2:{card}")
                line.text = str(row["text"])
                restored.append({"page": row["page"], "card": card, "text": row["text"]})
            container.insert(reference, speech)

    revision = tree.getroot().find(".//t:revisionDesc", namespaces=NS)
    if revision is not None and restored:
        change = etree.SubElement(revision, Q("change"), when="2026-10-06", who="#gcrane")
        change.text = (
            "Restored dramatic lines omitted from the inherited Potter transcription and "
            "aligned them conservatively to CTS card intervals from surrounding anchors."
        )
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    return {"work": work, "restored": len(restored), "displaced_relocated": len(displaced), "lines": restored}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_dir", type=Path)
    parser.add_argument("--ocr1", type=Path, required=True)
    parser.add_argument("--ocr2", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    pages1, pages2 = base.ocr_pages(args.ocr1), base.ocr_pages(args.ocr2)
    results = []
    for work in sorted(base.PLAY_PAGES):
        path = args.xml_dir / work / f"tlg0006.{work}.potter1781-eng1.xml"
        combined = {"work": work, "restored": 0, "displaced_relocated": 0, "passes": 0, "lines": []}
        for _ in range(5):
            result = restore_work(work, path, pages1 if work in VOLUME1 else pages2)
            combined["passes"] += 1
            combined["restored"] += result["restored"]
            combined["displaced_relocated"] += result["displaced_relocated"]
            combined["lines"].extend(result["lines"])
            if result["restored"] == 0:
                break
        results.append(combined)
    args.report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Restored", sum(item["restored"] for item in results), "dramatic lines")


if __name__ == "__main__":
    main()
