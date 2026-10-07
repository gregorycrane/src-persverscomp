#!/usr/bin/env python3
"""Repair Potter's Sophocles translations against the HathiTrust OCR.

Creates review copies only.  It removes footnote continuations that were
mistaken for verse, restores Potter's notes as stand-off TEI apparatus, and
repairs mechanical line breaks/catchwords without changing CTS alignment.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"t": TEI}
Q = lambda name: f"{{{TEI}}}{name}"

PLAY_PAGES = {
    "tlg004": (9, 62),
    "tlg007": (67, 130),
    "tlg002": (137, 185),
    "tlg001": (191, 235),
    "tlg003": (241, 290),
    "tlg006": (297, 346),
    "tlg005": (353, 406),
}

RANGE_RE = re.compile(r"^(\d+)\s*(?:\.{2,}|-)\s*(\d+)$")
NOTE_RE = re.compile(r"^L\.\s*(\d+(?:\.\d+)?)\.?\s*(.*)$", re.I)

RANGE_OVERRIDES = {
    15: (222, 250),
    17: (222, 250),
    183: (1348, 1377),
    355: (51, 70),
    399: (1348, 1372),
}

NOTE_OVERRIDES = {
    ("tlg003", 275, "103470"): "1034",
    ("tlg005", 383, "193"): "919",
    ("tlg005", 399, "13.56"): "1356",
}

KNOWN_PROSE_LINES = {
    "tlg001": {"6.2", "6.3", "6.4", "6.5", "6.6", "7", "7.2", "7.3", "1247.4", "1247.5"},
    "tlg002": {"213", "214", "661", "661.2", "662"},
    "tlg004": {"199-200", "203-205", "206-207", "208-209", "210-211"},
    "tlg007": {
        "1777.3", "1777.4", "1777.5", "1777.6", "1777.7", "1777.8", "1777.9",
        "1778", "1778.2", "1778.3", "1778.4", "1778.5", "1778.6", "1778.7",
        "1778.8", "1779", "1779.2", "1779.3", "1779.4", "1779.5", "1779.6",
        "1779.7", "1779.8",
    },
}


def text_of(element: etree._Element) -> str:
    return " ".join("".join(element.itertext()).split())


def line_text(line: etree._Element) -> str:
    parts = [line.text or ""]
    for child in line:
        if etree.QName(child).localname != "ref":
            parts.extend(child.itertext())
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def key(text: str) -> str:
    text = unicodedata.normalize(
        "NFKD", text.replace("ſ", "s").replace("æ", "ae").replace("Æ", "Ae")
    )
    return "".join(char.lower() for char in text if char.isalnum())


def word_count(text: str) -> int:
    return len(re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text, re.UNICODE))


def first_alpha(text: str) -> str:
    return next((char for char in text if char.isalpha()), "")


def ocr_pages(path: Path) -> dict[int, list[str]]:
    raw = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## p\. (\d+) .*?$", raw, re.MULTILINE))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        result[int(match.group(1))] = raw[match.end():end].splitlines()
    return result


def range_on_page(lines: list[str], page: int) -> tuple[int, int, int] | None:
    compact = [line.strip() for line in lines if line.strip()]
    if page in RANGE_OVERRIDES:
        for index, value in enumerate(compact[:16]):
            if any(char.isdigit() for char in value) and ("." in value or "-" in value):
                start, end = RANGE_OVERRIDES[page]
                return start, end, index
    for index, value in enumerate(compact[:16]):
        match = RANGE_RE.fullmatch(value.replace(" ", "").rstrip(".-"))
        if match:
            start, end = RANGE_OVERRIDES.get(page, (int(match.group(1)), int(match.group(2))))
            return start, end, index
    # The first Trachiniae page is OCRed as 1.1.13.
    for index, value in enumerate(compact[:16]):
        if value == "1.1.13":
            return 1, 13, index
    return None


def eligible_verse_line(value: str) -> bool:
    value = value.strip()
    if not value or RANGE_RE.fullmatch(value.replace(" ", "")):
        return False
    if re.fullmatch(r"\d+\.?", value) or re.fullmatch(r"[!?:;,.()\[\]/]+", value):
        return False
    if NOTE_RE.match(value):
        return False
    # Running heads and isolated speaker/strophic labels.
    if re.fullmatch(
        r"(?:Edipus King of Thebes|Edipus at Colonus|Antigone|The Trachinian Virgins|Ajax|Philoctetes|Electra)\.",
        value,
        re.I,
    ):
        return False
    if re.fullmatch(r"[A-ZŒÆ]{2,}\.?", value):
        return False
    if re.fullmatch(r"(?:[A-ZŒÆ]{2,}\.\s*){2,}", value):
        return False
    if re.fullmatch(r"[A-ZŒÆ .,'-]+", value) and word_count(value) <= 6:
        return False
    if re.fullmatch(r"\d+\s*[A-Z]", value):
        return False
    return word_count(value) >= 2


def clean_note_text(parts: list[str]) -> str:
    text = " ".join(part.strip() for part in parts if part.strip())
    text = re.sub(r"-\s+([a-z])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+(?:\d+\s*[A-Z]?|[A-Z]\s*\d*)\s*$", "", text)
    text = re.sub(r"\s+[:;/]\s*$", "", text)
    return text


def extract_notes(
    pages: dict[int, list[str]], low: int, high: int, work_id: str
) -> tuple[list[dict[str, object]], dict[int, str], set[str], list[dict[str, object]]]:
    """Return notes, printed-line text, note physical-line keys, and page audit."""
    notes: list[dict[str, object]] = []
    verse_by_number: dict[int, str] = {}
    note_line_keys: set[str] = set()
    page_audit: list[dict[str, object]] = []
    active: dict[str, object] | None = None

    for page in range(low, high + 1):
        raw = [line.strip() for line in pages.get(page, []) if line.strip()]
        range_info = range_on_page(raw, page)
        marker_indexes = [i for i, value in enumerate(raw) if NOTE_RE.match(value)]
        first_marker = marker_indexes[0] if marker_indexes else len(raw)

        verse_candidates: list[tuple[int, str]] = []
        expected = None
        if range_info:
            start, end, range_index = range_info
            expected = end - start + 1 if end >= start and end - start < 70 else None
            for index in range(range_index + 1, first_marker):
                if eligible_verse_line(raw[index]):
                    verse_candidates.append((index, raw[index]))
            if expected is not None:
                for offset, (_, value) in enumerate(verse_candidates[:expected]):
                    verse_by_number[start + offset] = value

        # A note continued from the preceding page follows the main verse and
        # precedes this page's first new L. marker.
        continuation_start = first_marker
        if (
            active is not None
            and marker_indexes
            and expected is not None
            and len(verse_candidates) > expected
        ):
            continuation_start = verse_candidates[expected - 1][0] + 1
            continuation = raw[continuation_start:first_marker]
            active["parts"].extend(continuation)
            active["last_page"] = page
            note_line_keys.update(key(value) for value in continuation if key(value))
        elif (
            active is not None
            and not marker_indexes
            and expected is not None
            and len(verse_candidates) > expected
            and page - int(active.get("last_page", active["page"])) == 1
            and active["parts"]
            and not re.search(r"[.!?]['\"”)]?\s*$", str(active["parts"][-1]))
        ):
            continuation_start = verse_candidates[expected - 1][0] + 1
            continuation = raw[continuation_start:]
            active["parts"].extend(continuation)
            active["last_page"] = page
            note_line_keys.update(key(value) for value in continuation if key(value))

        for marker_pos, marker_index in enumerate(marker_indexes):
            match = NOTE_RE.match(raw[marker_index])
            assert match
            if active is not None:
                active.pop("last_page", None)
                active["text"] = clean_note_text(active.pop("parts"))
                notes.append(active)
            end_index = marker_indexes[marker_pos + 1] if marker_pos + 1 < len(marker_indexes) else len(raw)
            first = match.group(2).strip()
            parts = ([first] if first else []) + raw[marker_index + 1:end_index]
            printed_line = NOTE_OVERRIDES.get((work_id, page, match.group(1)), match.group(1))
            active = {
                "printed_line": printed_line,
                "page": page,
                "last_page": page,
                "parts": parts,
            }
            note_line_keys.update(key(value) for value in parts if key(value))

        page_audit.append({
            "page": page,
            "range": list(range_info[:2]) if range_info else None,
            "expected_verse_lines": expected,
            "eligible_before_notes": len(verse_candidates),
            "note_markers": len(marker_indexes),
            "continuation_lines": max(0, first_marker - continuation_start),
        })

    if active is not None:
        active.pop("last_page", None)
        active["text"] = clean_note_text(active.pop("parts"))
        notes.append(active)
    # Two OCR page images in Oedipus Tyrannus are duplicates.  More generally,
    # retain just one copy of an identical printed-line note.
    deduped = []
    for note in notes:
        duplicate = next(
            (
                prior
                for prior in deduped
                if prior["printed_line"] == note["printed_line"]
                and SequenceMatcher(None, key(str(prior["text"])), key(str(note["text"]))).ratio() > 0.8
            ),
            None,
        )
        if duplicate is None:
            deduped.append(note)
    notes = deduped
    return notes, verse_by_number, note_line_keys, page_audit


def append_line(target: etree._Element, source: etree._Element, prepend: bool = False) -> None:
    addition = source.text or ""
    if prepend:
        target.text = addition.rstrip() + " " + (target.text or "").lstrip()
        for child in reversed(list(source)):
            source.remove(child)
            target.insert(0, child)
        return
    if addition:
        if len(target):
            target[-1].tail = (target[-1].tail or "") + " " + addition.lstrip()
        else:
            target.text = (target.text or "") + " " + addition.lstrip()
    for child in list(source):
        source.remove(child)
        target.append(child)


def same_speech(first: etree._Element, second: etree._Element) -> bool:
    return next(first.iterancestors(Q("sp")), None) is next(second.iterancestors(Q("sp")), None)


def remove_note_pollution(
    body: etree._Element, note_keys: set[str], work_id: str
) -> tuple[list[dict[str, str]], str]:
    removed = []
    end_note_parts = []
    for line in list(body.xpath(".//t:l", namespaces=NS)):
        value = line_text(line)
        # Remove only reviewed prose spans.  OCR note blocks often end with a
        # catchword copied from the next page; treating every OCR note line as
        # prose would therefore delete genuine verse.
        matched = line.get("n") in KNOWN_PROSE_LINES.get(work_id, set())
        if matched:
            removed.append({"n": line.get("n", ""), "text": value})
            if work_id == "tlg007" and line.get("n") in KNOWN_PROSE_LINES[work_id]:
                end_note_parts.append(value)
            line.getparent().remove(line)
    return removed, clean_note_text(end_note_parts)


def repair_lines(body: etree._Element, ocr_keys: set[str]) -> dict[str, object]:
    changes: dict[str, object] = {}
    joins = []
    lines = body.xpath(".//t:l", namespaces=NS)
    index = 0
    while index + 1 < len(lines):
        first, second = lines[index], lines[index + 1]
        combined = key(line_text(first) + " " + line_text(second))
        if same_speech(first, second) and combined in ocr_keys:
            joins.append([first.get("n"), second.get("n"), line_text(second)])
            append_line(first, second)
            second.getparent().remove(second)
            lines.pop(index + 1)
            continue
        index += 1
    changes["ocr_physical_joins"] = joins

    # Remove catchwords: a short line repeated at the start of one of the
    # next few verse lines is a page-bottom anticipatory word, not verse.
    catchwords = []
    lines = body.xpath(".//t:l", namespaces=NS)
    for index, line in enumerate(list(lines)):
        if line.getparent() is None:
            continue
        value = line_text(line)
        if word_count(value) <= 2 and key(value):
            following = [candidate for candidate in lines[index + 1:index + 5] if candidate.getparent() is not None]
            if any(key(line_text(candidate)).startswith(key(value)) for candidate in following):
                catchwords.append([line.get("n"), value])
                line.getparent().remove(line)
    changes["removed_catchwords"] = catchwords

    numeric = []
    for line in list(body.xpath(".//t:l", namespaces=NS)):
        if re.fullmatch(r"\d+", line_text(line)):
            numeric.append([line.get("n"), line_text(line)])
            line.getparent().remove(line)
    changes["removed_numeric"] = numeric

    lowercase = []
    previous = None
    for line in list(body.xpath(".//t:l", namespaces=NS)):
        value = line_text(line)
        initial = first_alpha(value)
        if previous is not None and initial and initial.islower():
            lowercase.append([previous.get("n"), line.get("n"), value])
            append_line(previous, line)
            line.getparent().remove(line)
        else:
            previous = line
    changes["lowercase_joins"] = lowercase

    one_word = []
    lines = body.xpath(".//t:l", namespaces=NS)
    for index, line in enumerate(list(lines)):
        if line.getparent() is None or word_count(line_text(line)) != 1:
            continue
        previous = lines[index - 1] if index else None
        following = lines[index + 1] if index + 1 < len(lines) else None
        if previous is not None and previous.getparent() is not None and same_speech(previous, line):
            append_line(previous, line)
            line.getparent().remove(line)
            one_word.append([previous.get("n"), line.get("n"), line_text(line), "back"])
        elif following is not None and following.getparent() is not None and same_speech(line, following):
            append_line(line, following)
            following.getparent().remove(following)
            one_word.append([line.get("n"), following.get("n"), line_text(following), "forward"])
    changes["one_word_joins"] = one_word

    # A final safety pass implements Potter's invariant even where malformed
    # speech wrappers prevented the conservative pass above.
    forced_one_word = []
    lines = body.xpath(".//t:l", namespaces=NS)
    for index, line in enumerate(list(lines)):
        if line.getparent() is None or word_count(line_text(line)) != 1 or index == 0:
            continue
        previous = lines[index - 1]
        if previous.getparent() is not None:
            forced_one_word.append([previous.get("n"), line.get("n"), line_text(line)])
            append_line(previous, line)
            line.getparent().remove(line)
    changes["forced_one_word_joins"] = forced_one_word
    return changes


def best_line(body: etree._Element, target: str) -> tuple[etree._Element | None, float]:
    target_key = key(target)
    best = None
    best_score = 0.0
    for line in body.xpath(".//t:l", namespaces=NS):
        candidate = key(line_text(line))
        if not candidate:
            continue
        if target_key in candidate or candidate in target_key:
            score = min(len(target_key), len(candidate)) / max(len(target_key), len(candidate))
        else:
            score = SequenceMatcher(None, target_key, candidate).ratio()
        if score > best_score:
            best, best_score = line, score
    return best, best_score


def sanitize_note_texts(
    notes: list[dict[str, object]], body: etree._Element, work_id: str
) -> None:
    """Remove page catchwords/verse lines that OCR appended to footnotes."""
    verse_lines = sorted(
        {
            line_text(line)
            for line in body.xpath(".//t:l", namespaces=NS)
            if len(line_text(line)) >= 22
            and line.get("n") not in KNOWN_PROSE_LINES.get(work_id, set())
        },
        key=len,
        reverse=True,
    )
    for note in notes:
        value = str(note["text"])
        for verse in verse_lines:
            # OCR sometimes prefixes a catchword with a signature or page
            # artifact, so remove the matching dramatic line wherever it was
            # spliced into the prose note.
            value = value.replace(verse, " ")
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"\s+(?:\d+\s*[A-Z]?|[A-Z]\s*\d*)\s*$", "", value)
        value = re.sub(r"\s+[:;/]\s*$", "", value)
        note["text"] = value
    deduped: list[dict[str, object]] = []
    for note in notes:
        if any(
            prior["printed_line"] == note["printed_line"]
            and SequenceMatcher(None, key(str(prior["text"])), key(str(note["text"]))).ratio() > 0.8
            for prior in deduped
        ):
            continue
        deduped.append(note)
    notes[:] = deduped


def add_notes(
    root: etree._Element,
    body: etree._Element,
    work_id: str,
    notes: list[dict[str, object]],
    verse_by_number: dict[int, str],
) -> list[dict[str, object]]:
    text = root.find(Q("text"))
    back = text.find(Q("back")) if text is not None else None
    if back is None and text is not None:
        back = etree.SubElement(text, Q("back"))
    apparatus = etree.SubElement(back, Q("div"), type="apparatus", subtype="source-notes")
    head = etree.SubElement(apparatus, Q("head"))
    head.text = "Robert Potter's notes"
    results = []
    for index, note in enumerate(notes, 1):
        printed = note["printed_line"]
        try:
            printed_int = int(float(str(printed)))
        except ValueError:
            printed_int = -1
        target_text = verse_by_number.get(printed_int, "")
        if printed == "end":
            body_lines = body.xpath(".//t:l", namespaces=NS)
            anchor, score = (body_lines[-1], 1.0) if body_lines else (None, 0.0)
        else:
            anchor, score = best_line(body, target_text) if target_text else (None, 0.0)
            # Some inherited transcriptions omit the exact printed line.  In
            # that case anchor the note to the closest surviving neighbour,
            # rather than to a coincidentally similar line elsewhere.
            if score < 0.75 and printed_int >= 0:
                for distance in range(1, 4):
                    for neighbour in (printed_int - distance, printed_int + distance):
                        neighbour_text = verse_by_number.get(neighbour, "")
                        if not neighbour_text:
                            continue
                        candidate, candidate_score = best_line(body, neighbour_text)
                        if candidate_score > score:
                            anchor, score = candidate, candidate_score
        app_id = f"app-{work_id}-potter-note-{index:03d}"
        app = etree.SubElement(apparatus, Q("app"), loc=anchor.get("n", "") if anchor is not None else "")
        app.set(f"{{{XML}}}id", app_id)
        app_note = etree.SubElement(app, Q("note"), type="source", resp="#potter")
        label = etree.SubElement(app_note, Q("label"))
        label.text = f"L. {printed}."
        label.tail = " "
        paragraph = etree.SubElement(app_note, Q("p"))
        paragraph.text = str(note["text"])
        if anchor is not None and score >= 0.48:
            ref = etree.SubElement(anchor, Q("ref"), target=f"#{app_id}", type="source-note")
            ref.text = "*"
        results.append({
            "id": app_id,
            "printed_line": printed,
            "page": note["page"],
            "anchor_n": anchor.get("n") if anchor is not None and score >= 0.48 else None,
            "anchor_text": line_text(anchor) if anchor is not None else None,
            "ocr_anchor_text": target_text,
            "score": round(score, 3),
            "text": note["text"],
        })
    return results


def repair(source: Path, ocr_path: Path, output: Path, audit_path: Path) -> None:
    match = re.search(r"\.(tlg\d{3})\.", source.name)
    if not match or match.group(1) not in PLAY_PAGES:
        raise RuntimeError(f"Cannot determine Sophocles work from {source.name}")
    work_id = match.group(1)
    low, high = PLAY_PAGES[work_id]
    pages = ocr_pages(ocr_path)
    notes, verse_by_number, note_keys, page_audit = extract_notes(pages, low, high, work_id)

    tree = etree.parse(str(source))
    root = tree.getroot()
    body = root.xpath("//t:body", namespaces=NS)[0]
    sanitize_note_texts(notes, body, work_id)
    removed_notes, end_note = remove_note_pollution(body, note_keys, work_id)
    ocr_keys = {key(line) for page in range(low, high + 1) for line in pages.get(page, []) if key(line)}
    line_repairs = repair_lines(body, ocr_keys)
    if end_note:
        notes.append({"printed_line": "end", "page": high, "text": end_note})
    note_results = add_notes(root, body, work_id, notes, verse_by_number)

    revision = root.find(".//t:revisionDesc", namespaces=NS)
    if revision is not None:
        change = etree.SubElement(revision, Q("change"), when="2026-10-06", who="#gcrane")
        change.text = (
            "Rebuilt Potter lineation against the HathiTrust OCR; removed catchwords and "
            "footnote prose from the dramatic text, and restored Potter's source notes."
        )

    remaining_lower = []
    remaining_one = []
    for line in body.xpath(".//t:l", namespaces=NS):
        value = line_text(line)
        initial = first_alpha(value)
        if initial and initial.islower():
            remaining_lower.append([line.get("n"), value])
        if word_count(value) <= 1:
            remaining_one.append([line.get("n"), value])

    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    audit = {
        "source": str(source),
        "ocr": str(ocr_path),
        "work": work_id,
        "page_range": [low, high],
        "removed_note_lines": removed_notes,
        "line_repairs": line_repairs,
        "notes": note_results,
        "unanchored_notes": [item for item in note_results if item["anchor_n"] is None],
        "remaining_lowercase": remaining_lower,
        "remaining_one_word": remaining_one,
        "lines_after": len(body.xpath(".//t:l", namespaces=NS)),
        "note_count": len(notes),
        "note_ref_count": len(body.xpath(".//t:ref[@type='source-note']", namespaces=NS)),
        "page_audit": page_audit,
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--ocr", type=Path, required=True)
    args = parser.parse_args()
    repair(args.source, args.ocr, args.output, args.audit)


if __name__ == "__main__":
    main()
