#!/usr/bin/env python3
"""Repair Potter's Euripides translations against the HathiTrust OCR.

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
    "tlg017": (5, 56),       # Bacchae, vol. 1
    "tlg010": (58, 118),     # Ion, vol. 1
    "tlg002": (125, 164),    # Alcestis, vol. 1
    "tlg003": (171, 220),    # Medea, vol. 1
    "tlg005": (231, 280),    # Hippolytus, vol. 1
    "tlg015": (287, 356),    # Phoenician Women, vol. 1
    "tlg008": (365, 410),    # Suppliants, vol. 1
    "tlg009": (417, 466),    # Heracles, vol. 1
    "tlg004": (471, 507),    # Heraclidae, vol. 1
    "tlg018": (9, 70),       # Iphigenia at Aulis, vol. 2
    "tlg019": (75, 108),     # Rhesus, vol. 2
    "tlg011": (113, 162),    # Trojan Women, vol. 2
    "tlg007": (167, 206),    # Hecuba, vol. 2
    "tlg014": (213, 272),    # Helen, vol. 2
    "tlg012": (279, 326),    # Electra, vol. 2
    "tlg016": (333, 390),    # Orestes, vol. 2
    "tlg013": (397, 448),    # Iphigenia in Tauris, vol. 2
    "tlg006": (455, 499),    # Andromache, vol. 2
}

RANGE_RE = re.compile(r"^(\d+)\s*(?:\.{2,}|-)\s*(\d+)$")
NOTE_RE = re.compile(r"^L\.\s*(\d+(?:\.\d+)?)\.?\s*(.*)$", re.I)

RANGE_OVERRIDES = {}

NOTE_OVERRIDES = {}

CONTINUATION_STARTS = {
    ("tlg010", 66): "Carmeli translates it thus :",
    ("tlg018", 15): "⚫meration of the ships and forces",
    ("tlg015", 297): "This protended spear,",
    ("tlg015", 310): "swelling with extravagant conceptions:",
    ("tlg008", 402): "persons struck with lightening as sacred;",
    ("tlg018", 39): "conversation with him, addresses himself",
    ("tlg014", 222): "afterwards finished by the Lacedemonians,",
    ("tlg014", 268): "suspect the text is corrupted:",
    ("tlg012", 287): "ἐξανίσανται:",
    ("tlg016", 334): "solution of this fable:",
    ("tlg016", 352): "Ægypt it wisely and humanely intended",
}

KNOWN_PROSE_LINES = {
    # Footnote prose and quotations inherited as dramatic verse.
    "tlg004": {"1040.2"},
    "tlg006": {"820.4"},
    "tlg008": {"315.5", "601.2"},
    "tlg009": {"465.4", "465.5", "497.4"},
    "tlg010": {"225.4", "226", "226.2", "226.3", "226.4", "230"},
    "tlg012": {"672"},
    "tlg013": {"939.3", "1078"},
    "tlg015": {"159.2", "159.3", "159.4", "160"},
    "tlg016": {"580.2"},
    "tlg018": {"190.4", "960.4"},
    "tlg019": {"23.3"},
}

IMPLICIT_NOTES = {
    "tlg004": [{"printed_line": "symbol", "page": 505, "text": "The Chorus; the Heraclidae.", "anchor_line_n": "1040"}],
    "tlg006": [{"printed_line": "symbol", "page": 481, "text": "A river of Thessaly.", "anchor_line_n": "820.2"}],
    "tlg008": [
        {"printed_line": "358", "page": 376, "text": "This alludes to his dangerous engagement with the wild boar, or rather sow, of Crommyon, which he slew. Plutarch, Life of Theseus, p. 8, ed. Bryan.", "target_text": "The great achievement: 'gainst the savage boar"},
        {"printed_line": "symbol", "page": 386, "text": "Tyrwhitt with great reason gives to Adrastus through this scene the part usually assigned to Aethra, who went to Athens with Theseus, and came to Eleusis no more.", "target_text": "Soon shall the warlike train of Pallas march."},
    ],
    "tlg009": [
        {"printed_line": "symbol", "page": 433, "text": "Therimachus; Creontidas.", "anchor_line_n": "465"},
        {"printed_line": "symbol", "page": 434, "text": "Deicoon.", "anchor_line_n": "497"},
    ],
    "tlg012": [{"printed_line": "symbol", "page": 301, "text": "To Orestes.", "anchor_line_n": "670"}],
    "tlg013": [
        {"printed_line": "symbol", "page": 426, "text": "Pointing to Pylades.", "anchor_line_n": "939.2"},
        {"printed_line": "symbol", "page": 430, "text": "To Orestes and Pylades.", "anchor_line_n": "1075.7"},
    ],
    "tlg018": [{"printed_line": "symbol", "page": 44, "text": "See Pindar's first Olympic Ode, and the Scholiast, strophe 2.", "anchor_line_n": "960.3"}],
    "tlg019": [{"printed_line": "symbol", "page": 76, "text": "Sarpedon.", "anchor_line_n": "25.3"}],
}

LINE_REPLACEMENTS = {
    # The first half of this line was the tail of the preceding note.
    ("tlg010", "230.2"): "What is his name?",
}

RUNNING_HEAD_LINES = {"VOL. 11.", "VOL. II."}


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
        r"(?:Bacch(?:ae|æ)|Ion|Alcestis|Medea|Hippolytus|The Phoenician Virgins|"
        r"The Supplicants|Hercules Furens|The Heraclidae|Iphigenia in Aulis|Rhesus|"
        r"The Trojan Dames|Hecuba|Helena|Electra|Orestes|Iphigenia in Tauris|Andromache)\.",
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
            and (work_id, page) not in CONTINUATION_STARTS
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

        continuation_hint = CONTINUATION_STARTS.get((work_id, page))
        if active is not None and continuation_hint:
            start_index = next(
                (i for i, value in enumerate(raw) if value.startswith(continuation_hint)),
                None,
            )
            if start_index is not None:
                continuation = raw[start_index:first_marker]
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

    running_heads = []
    leading_i = []
    for line in list(body.xpath(".//t:l", namespaces=NS)):
        value = line_text(line)
        if value in RUNNING_HEAD_LINES:
            running_heads.append([line.get("n"), value])
            line.getparent().remove(line)
            continue
        if re.match(r"^1(?=\s|,)", value):
            corrected = re.sub(r"^1(?=\s|,)", "I", value, count=1)
            if not len(line):
                line.text = corrected
                leading_i.append([line.get("n"), value, corrected])
    changes["removed_running_heads"] = running_heads
    changes["corrected_leading_I"] = leading_i

    # One-word replies and lower-case stage directions occur legitimately in
    # Euripides. Report them for review, but do not merge them mechanically.
    changes["lowercase_joins"] = []
    changes["one_word_joins"] = []
    changes["forced_one_word_joins"] = []
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


def repair_alignment_gaps(body: etree._Element, work_id: str) -> list[str]:
    if work_id != "tlg008":
        return []
    target = body.xpath('.//t:l[@n="785-790"]', namespaces=NS)
    if not target or body.xpath('.//t:milestone[@unit="card"][@n="786"]', namespaces=NS):
        return []
    milestone = etree.Element(Q("milestone"), unit="card", n="786", edRef="Perseus")
    target[0].addprevious(milestone)
    return ["786"]


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
        target_text = str(note.get("target_text") or verse_by_number.get(printed_int, ""))
        if printed == "end":
            body_lines = body.xpath(".//t:l", namespaces=NS)
            anchor, score = (body_lines[-1], 1.0) if body_lines else (None, 0.0)
        elif note.get("anchor_line_n"):
            matches = body.xpath(f'.//t:l[@n="{note["anchor_line_n"]}"]', namespaces=NS)
            anchor, score = (matches[0], 1.0) if matches else (None, 0.0)
        else:
            anchor, score = best_line(body, target_text) if target_text else (None, 0.0)
            # Some inherited transcriptions omit the exact printed line. In
            # that case walk outward through Potter's numbered lines and use
            # the nearest *strongly matching* surviving neighbour. This keeps
            # a note local without accepting a coincidental match elsewhere.
            if score < 0.75 and printed_int >= 0:
                for distance in range(1, 81):
                    nearby = []
                    for neighbour in (printed_int - distance, printed_int + distance):
                        neighbour_text = verse_by_number.get(neighbour, "")
                        if not neighbour_text:
                            continue
                        candidate, candidate_score = best_line(body, neighbour_text)
                        if candidate is not None and candidate_score >= 0.8:
                            nearby.append((candidate_score, candidate, neighbour_text))
                    if nearby:
                        score, anchor, target_text = max(nearby, key=lambda item: item[0])
                        break
        app_id = f"app-{work_id}-potter-note-{index:03d}"
        app = etree.SubElement(apparatus, Q("app"), loc=anchor.get("n", "") if anchor is not None else "")
        app.set(f"{{{XML}}}id", app_id)
        app_note = etree.SubElement(app, Q("note"), type="source", resp="#potter")
        label = etree.SubElement(app_note, Q("label"))
        label.text = f"L. {printed}." if printed != "symbol" else "Note."
        label.tail = " "
        paragraph = etree.SubElement(app_note, Q("p"))
        paragraph.text = str(note["text"])
        if anchor is not None and score >= 0.75:
            ref = etree.SubElement(anchor, Q("ref"), target=f"#{app_id}", type="source-note")
            ref.text = "*"
        results.append({
            "id": app_id,
            "printed_line": printed,
            "page": note["page"],
            "anchor_n": anchor.get("n") if anchor is not None and score >= 0.75 else None,
            "anchor_text": line_text(anchor) if anchor is not None else None,
            "ocr_anchor_text": target_text,
            "score": round(score, 3),
            "text": note["text"],
        })
    return results


def repair(source: Path, ocr_path: Path, output: Path, audit_path: Path) -> None:
    match = re.search(r"\.(tlg\d{3})\.", source.name)
    if not match or match.group(1) not in PLAY_PAGES:
        raise RuntimeError(f"Cannot determine Euripides work from {source.name}")
    work_id = match.group(1)
    low, high = PLAY_PAGES[work_id]
    pages = ocr_pages(ocr_path)
    notes, verse_by_number, note_keys, page_audit = extract_notes(pages, low, high, work_id)
    notes.extend(dict(note) for note in IMPLICIT_NOTES.get(work_id, []))
    notes.sort(key=lambda note: (int(note["page"]), str(note["printed_line"])))

    tree = etree.parse(str(source))
    root = tree.getroot()
    body = root.xpath("//t:body", namespaces=NS)[0]
    replacements = []
    for (replacement_work, line_n), value in LINE_REPLACEMENTS.items():
        if replacement_work != work_id:
            continue
        matches = body.xpath(f'.//t:l[@n="{line_n}"]', namespaces=NS)
        if matches and not len(matches[0]):
            replacements.append([line_n, line_text(matches[0]), value])
            matches[0].text = value
    sanitize_note_texts(notes, body, work_id)
    removed_notes, end_note = remove_note_pollution(body, note_keys, work_id)
    ocr_keys = {key(line) for page in range(low, high + 1) for line in pages.get(page, []) if key(line)}
    line_repairs = repair_lines(body, ocr_keys)
    line_repairs["line_replacements"] = replacements
    line_repairs["restored_card_boundaries"] = repair_alignment_gaps(body, work_id)
    if end_note:
        notes.append({"printed_line": "end", "page": high, "text": end_note})
    note_results = add_notes(root, body, work_id, notes, verse_by_number)

    revision = root.find(".//t:revisionDesc", namespaces=NS)
    if revision is not None:
        change = etree.SubElement(revision, Q("change"), when="2026-10-06", who="#gcrane")
        change.text = (
            "Checked Potter's Euripides against the HathiTrust OCR, removed mechanical "
            "catchwords, and restored Potter's source notes."
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
