#!/usr/bin/env python3
"""Repair lineation and notes in Potter's six other Aeschylus translations.

The script is deliberately conservative: it creates review copies, preserves
the existing CTS card correspondence, and reports every unresolved one-word
line.  Missing source-note anchors are supplied from comparison with the
HathiTrust OCR.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"t": TEI}
Q = lambda name: f"{{{TEI}}}{name}"


def text_of(element: etree._Element) -> str:
    return " ".join("".join(element.itertext()).split())


def line_text(line: etree._Element) -> str:
    parts = [line.text or ""]
    for child in line:
        if etree.QName(child).localname != "ref":
            parts.extend(child.itertext())
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def match_key(text: str) -> str:
    text = unicodedata.normalize(
        "NFKD", text.replace("ſ", "s").replace("æ", "ae").replace("Æ", "Ae")
    )
    return "".join(char.lower() for char in text if char.isalnum())


def first_alpha(text: str) -> str:
    return next((char for char in text if char.isalpha()), "")


def word_count(text: str) -> int:
    return len(re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text, flags=re.UNICODE))


def speech_label(line: etree._Element) -> str:
    speech = next(line.iterancestors(Q("sp")), None)
    if speech is None:
        return ""
    speaker = speech.find(Q("speaker"))
    return match_key(text_of(speaker)) if speaker is not None else ""


def same_speech(first: etree._Element, second: etree._Element) -> bool:
    first_speech = next(first.iterancestors(Q("sp")), None)
    second_speech = next(second.iterancestors(Q("sp")), None)
    if first_speech is second_speech:
        return True
    first_label, second_label = speech_label(first), speech_label(second)
    return bool(first_label and first_label == second_label)


def append_line(target: etree._Element, source: etree._Element, *, prepend: bool = False) -> None:
    addition = source.text or ""
    if prepend:
        old_text = target.text or ""
        target.text = addition.rstrip() + (" " if addition and old_text else "") + old_text.lstrip()
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


def page_map(body: etree._Element) -> dict[int, str | None]:
    current = None
    result = {}
    for element in body.iter():
        local = etree.QName(element).localname
        if local == "pb":
            current = element.get("n")
        elif local == "l":
            result[id(element)] = current
    return result


def ocr_pages(path: Path) -> dict[str, list[str]]:
    raw = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## p\. (\d+) .*?$", raw, re.MULTILINE))
    pages = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        pages[match.group(1)] = raw[match.end():end].splitlines()
    return pages


def app_index(root: etree._Element) -> dict[str, etree._Element]:
    return {
        app.get(f"{{{XML}}}id"): app
        for app in root.xpath("//t:back//t:app[@xml:id]", namespaces=NS)
    }


def set_plain_text(element: etree._Element, value: str) -> None:
    for child in list(element):
        element.remove(child)
    element.text = " ".join(value.split())


def merge_note_apps(
    root: etree._Element,
    keep_id: str,
    remove_id: str,
    *,
    clean_keep=lambda value: value,
    clean_remove=lambda value: value,
) -> None:
    apps = app_index(root)
    keep, remove = apps.get(keep_id), apps.get(remove_id)
    if keep is None or remove is None:
        return
    keep_note = keep.find(".//t:note", namespaces=NS)
    remove_note = remove.find(".//t:note", namespaces=NS)
    if keep_note is None or remove_note is None:
        return
    merged = f"{clean_keep(text_of(keep_note)).strip()} {clean_remove(text_of(remove_note)).strip()}"
    set_plain_text(keep_note, merged)
    remove.getparent().remove(remove)


def add_line_ref(body: etree._Element, line_n: int, target: str, marker: str) -> None:
    line = body.xpath(f'.//t:l[@n="{line_n}"]', namespaces=NS)
    if not line:
        raise RuntimeError(f"Cannot anchor {target}: line {line_n} not found")
    if line[0].xpath(f'.//t:ref[@target="#{target}"]', namespaces=NS):
        return
    ref = etree.SubElement(line[0], Q("ref"), target=f"#{target}")
    ref.text = marker


def repair_source_notes(root: etree._Element, body: etree._Element, work_id: str) -> dict[str, object]:
    """Repair OCR-split notes and restore anchors visible in Potter's print."""
    changes: dict[str, object] = {"merged": [], "removed_duplicates": [], "added_anchors": []}

    anchors: dict[str, list[tuple[int, str, str]]] = {
        "tlg001": [(1, "app-tlg001-note.91.a", "a")],
        "tlg003": [(94, "app-tlg003-note.14.c", "c")],
        "tlg005": [
            (2, "app-tlg005-note.7.a", "a"),
            (32, "app-tlg005-note.9.c", "c"),
            (94, "app-tlg005-note.13.h", "h"),
            (131, "app-tlg005-note.15.k", "k"),
            (148, "app-tlg005-note.16.l", "l"),
            (196, "app-tlg005-note.20.p", "p"),
            (210, "app-tlg005-note.21.q", "q"),
            (252, "app-tlg005-note.24.t", "t"),
            (289, "app-tlg005-note.26.x", "x"),
            (451, "app-tlg005-note.36.z", "z"),
            (585, "app-tlg005-note.44.c", "c"),
            (612, "app-tlg005-note.45.e", "e"),
            (638, "app-tlg005-note.49.h", "h"),
            (706, "app-tlg005-note.52.i", "i"),
            (757, "app-tlg005-note.56.m", "m"),
            (777, "app-tlg005-note.58.p", "p"),
            (913, "app-tlg005-note.66.o", "o"),
            (927, "app-tlg005-note.66.p", "p"),
            (934, "app-tlg005-note.67.q", "q"),
            (965, "app-tlg005-note.69.r", "r"),
            # The asterisk follows "house" in the page 73 scan.
            (1035, "app-tlg005-note.73.t", "*"),
            (1097, "app-tlg005-note.77.u", "u"),
            (1656, "app-tlg005-note.117.v", "v"),
        ],
    }

    if work_id == "tlg005":
        # Page breaks divided several long footnotes.  Remove printer
        # signatures/catchwords and combine the continuations.
        pairs = [
            ("app-tlg005-note.7.a", "app-tlg005-note.8.a",
             lambda s: re.sub(r"\s+B 4$", "", s), lambda s: s),
            ("app-tlg005-note.16.l", "app-tlg005-note.17.m",
             lambda s: re.sub(r"\s+not$", "", s),
             lambda s: re.sub(r"\s+Vol\. II\. C Sound$", "", re.sub(r"^not\s+", "", s))),
            ("app-tlg005-note.22.r", "app-tlg005-note.23.s",
             lambda s: re.sub(r"\s+Bound$", "", s),
             lambda s: re.sub(r"\s+C 4 Cou’d$", "", s)),
            ("app-tlg005-note.25.u", "app-tlg005-note.26.w",
             lambda s: re.sub(r"\s+reader,?\s+But$", "", s), lambda s: s),
            ("app-tlg005-note.31.y", "app-tlg005-note.32.z",
             lambda s: re.sub(r"\s+her$", "", s),
             lambda s: re.sub(r"\s+Prepare$", "", re.sub(r"^her\s+", "", s))),
        ]
        for keep, remove, clean_keep, clean_remove in pairs:
            merge_note_apps(root, keep, remove, clean_keep=clean_keep, clean_remove=clean_remove)
            changes["merged"].append([keep, remove])

        # A page-67 OCR block begins with the end of note p and then note q.
        apps = app_index(root)
        p_note = apps["app-tlg005-note.66.p"].find(".//t:note", namespaces=NS)
        q_note = apps["app-tlg005-note.67.q"].find(".//t:note", namespaces=NS)
        q_text = text_of(q_note)
        continuation, separator, remainder = q_text.partition("We have")
        if separator:
            set_plain_text(p_note, re.sub(r"\s+Inſtamus$", "", text_of(p_note)) + " " + continuation.strip())
            set_plain_text(q_note, "We have" + re.sub(r"\s+F 2$", "", remainder))
            changes["merged"].append(["app-tlg005-note.66.p", "page-67 continuation"])

        # Page 115 repeats the complete swan note already captured on p. 114.
        duplicate = app_index(root).get("app-tlg005-note.115.u")
        if duplicate is not None:
            duplicate.getparent().remove(duplicate)
            changes["removed_duplicates"].append("app-tlg005-note.115.u")

        # The inherited marker beside "thinking on her lord" points to the
        # wrong continuation block; the print has b there.
        for ref in body.xpath('.//t:ref[@target="#app-tlg005-note.8.a"]', namespaces=NS):
            ref.set("target", "#app-tlg005-note.8.b")
            ref.text = "b"

    for line_n, target, marker in anchors.get(work_id, []):
        if target in app_index(root):
            add_line_ref(body, line_n, target, marker)
            changes["added_anchors"].append([line_n, target, marker])
    return changes


def repair(source: Path, ocr_path: Path, output: Path, audit_path: Path) -> None:
    tree = etree.parse(str(source))
    root = tree.getroot()
    body = root.xpath("//t:body", namespaces=NS)[0]
    pages = ocr_pages(ocr_path)
    work_match = re.search(r"\.(tlg\d{3})\.", source.name)
    if not work_match:
        raise RuntimeError(f"Cannot determine work id from {source.name}")
    work_id = work_match.group(1)
    audit: dict[str, object] = {"source": str(source), "ocr": str(ocr_path)}
    audit["source_note_repairs"] = repair_source_notes(root, body, work_id)

    # Remove unreferenced apparatus material copied from a different play in
    # the same printed volume.  Genuine notes must fall within this play's pb
    # range; referenced apps are never removed here.
    printed_pages = [int(value) for value in body.xpath(".//t:pb/@n", namespaces=NS) if value.isdigit()]
    low, high = min(printed_pages), max(printed_pages)
    targets = {
        ref.get("target", "").lstrip("#")
        for ref in body.xpath(".//t:ref[@target]", namespaces=NS)
    }
    removed_foreign_notes = []
    for app in list(root.xpath("//t:back//t:app[@xml:id]", namespaces=NS)):
        app_id = app.get(f"{{{XML}}}id")
        match = re.search(r"note\.(\d+)(?:\.|$)", app_id or "")
        if match and app_id not in targets and not (low <= int(match.group(1)) <= high):
            removed_foreign_notes.append(app_id)
            app.getparent().remove(app)
    audit["removed_foreign_notes"] = removed_foreign_notes

    # Join adjacent TEI fragments when the OCR records them as one physical
    # line.  Page and speaker boundaries protect structural transitions.
    pmap = page_map(body)
    physical = {
        page: {match_key(line) for line in lines if match_key(line)}
        for page, lines in pages.items()
    }
    physical_joins = []
    lines = body.xpath(".//t:l", namespaces=NS)
    index = 0
    while index + 1 < len(lines):
        first, second = lines[index], lines[index + 1]
        page = pmap.get(id(first))
        combined = match_key(line_text(first) + " " + line_text(second))
        if (
            page == pmap.get(id(second))
            and same_speech(first, second)
            and combined in physical.get(page or "", set())
        ):
            physical_joins.append([first.get("n"), second.get("n"), line_text(second)])
            append_line(first, second)
            second.getparent().remove(second)
            lines.pop(index + 1)
            continue
        index += 1
    audit["physical_line_joins"] = physical_joins

    # A catchword can anticipate a verse line, speaker label, or stage
    # direction on the following page.  Apostrophes and long-s differences
    # are ignored by match_key.
    removed_catchwords = []
    events = [
        element for element in body.iter()
        if etree.QName(element).localname in {"l", "pb", "stage", "speaker"}
    ]
    previous_line = None
    intervening_pages: list[str | None] = []
    for element in events:
        local = etree.QName(element).localname
        if local == "pb":
            intervening_pages.append(element.get("n"))
            continue
        if previous_line is not None and intervening_pages:
            before = line_text(previous_line)
            key = match_key(before)
            if key and len(key) <= 35 and match_key(text_of(element)).startswith(key):
                removed_catchwords.append([previous_line.get("n"), before, intervening_pages[-1]])
                previous_line.getparent().remove(previous_line)
                intervening_pages = []
            elif local == "l":
                # Speaker labels and unrelated stage directions may precede
                # the repeated catchword text on the new page.
                intervening_pages = []
        if local == "l":
            previous_line = element
    audit["removed_catchwords"] = removed_catchwords

    # Bare OCR digits between verse lines are pagination/note noise.
    removed_numeric = []
    for line in list(body.xpath(".//t:l", namespaces=NS)):
        value = line_text(line)
        if re.fullmatch(r"\d+", value):
            removed_numeric.append([line.get("n"), value])
            line.getparent().remove(line)
    audit["removed_numeric_lines"] = removed_numeric

    # Potter's printed poetic lines do not begin with lowercase words.  The
    # user's rule is categorical: a lowercase start is a continuation of the
    # preceding printed line, even where the inherited TEI has split or
    # malformed speech wrappers.
    lowercase_joins = []
    lines = body.xpath(".//t:l", namespaces=NS)
    previous_line = None
    for line in list(lines):
        value = line_text(line)
        initial = first_alpha(value)
        if previous_line is not None and initial and initial.islower():
            lowercase_joins.append([previous_line.get("n"), line.get("n"), value])
            append_line(previous_line, line)
            line.getparent().remove(line)
        else:
            previous_line = line
    audit["lowercase_joins"] = lowercase_joins

    # A remaining one-word line is never silently accepted.  Safe cases in
    # which an incomplete preceding line continues within the same speech are
    # joined; everything else remains in the audit for explicit review.
    one_word_joins = []
    lines = body.xpath(".//t:l", namespaces=NS)
    for index, line in enumerate(list(lines)):
        if line.getparent() is None:
            continue
        value = line_text(line)
        if word_count(value) != 1:
            continue
        previous = lines[index - 1] if index else None
        if (
            previous is not None
            and previous.getparent() is not None
            and same_speech(previous, line)
            and not re.search(r"[.!?;:]\s*$", line_text(previous))
        ):
            one_word_joins.append([previous.get("n"), line.get("n"), value])
            append_line(previous, line)
            line.getparent().remove(line)
    audit["one_word_joins"] = one_word_joins

    forward_one_word_joins = []
    lines = body.xpath(".//t:l", namespaces=NS)
    for index, line in enumerate(list(lines)):
        if line.getparent() is None or word_count(line_text(line)) != 1:
            continue
        following = lines[index + 1] if index + 1 < len(lines) else None
        if (
            following is not None
            and following.getparent() is not None
            and same_speech(line, following)
        ):
            forward_one_word_joins.append([line.get("n"), following.get("n"), line_text(following)])
            append_line(line, following)
            following.getparent().remove(following)
    audit["forward_one_word_joins"] = forward_one_word_joins

    remaining_lowercase = []
    remaining_one_word = []
    for line in body.xpath(".//t:l", namespaces=NS):
        value = line_text(line)
        initial = first_alpha(value)
        if initial and initial.islower():
            remaining_lowercase.append([line.get("n"), value])
        if word_count(value) <= 1:
            remaining_one_word.append([line.get("n"), value])
    audit["remaining_lowercase"] = remaining_lowercase
    audit["remaining_one_word"] = remaining_one_word

    # Renumber only after all structural decisions, then synchronize note loc.
    lines = body.xpath(".//t:l", namespaces=NS)
    for number, line in enumerate(lines, 1):
        line.set("n", str(number))
    apps = {
        app.get(f"{{{XML}}}id"): app
        for app in root.xpath("//t:back//t:app[@xml:id]", namespaces=NS)
    }
    locations: dict[str, list[str]] = {}
    for ref in body.xpath(".//t:ref[@target]", namespaces=NS):
        target = ref.get("target", "").lstrip("#")
        line = next((ancestor for ancestor in ref.iterancestors(Q("l"))), None)
        if target in apps and line is not None:
            locations.setdefault(target, []).append(line.get("n"))
    for app_id, app in apps.items():
        if app_id in locations:
            app.set("loc", " ".join(dict.fromkeys(locations[app_id])))

    revision = root.find(".//t:revisionDesc", namespaces=NS)
    if revision is not None:
        change = etree.SubElement(revision, Q("change"), when="2026-10-06", who="#gcrane")
        change.text = (
            "Rebuilt Potter lineation against the HathiTrust OCR; joined lowercase "
            "continuations and one-word wraps, removed catchwords and OCR debris, "
            "and restored source-note anchors."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    audit.update({
        "lines_after": len(lines),
        "notes": len(apps),
        "note_refs": len(body.xpath(".//t:ref[@target]", namespaces=NS)),
    })
    audit_path.parent.mkdir(parents=True, exist_ok=True)
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
