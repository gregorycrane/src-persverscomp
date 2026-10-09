#!/usr/bin/env python3
"""Normalize and install Dindorf's Aristophanic fragment TEI."""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import re
import unicodedata

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI, "ti": CTS}
XID = f"{{{XML}}}id"
VERSION = "dindorf1893-grc1"
EDITION_URN = f"urn:cts:greekLit:tlg0019.fragmenta.{VERSION}"

# These are page-extraction sections, not editorial work identities.  Repeated
# values intentionally fold page continuations into one work.
SECTION_TARGETS = (
    "daitaleis", "daitaleis", "babylonioi", "proagon", "proagon",
    "amphiareos", "ploutos_a", "aiolosikon", "kokalos", "anagyros",
    "georgoi", "gerytades", "daidalos", "daidalos", "daidalos",
    "danaides", "dramata_e_kentauros", "dramata_e_niobos", "dramata",
    "heroes", "thesmophoriazousai_deuterai", "thesmophoriazousai_deuterai",
    "lemniai", "nauagos", "nesoi", "olkades", "pelargoi", "poiesis",
    "polyidos", "skenas_katalambanousai", "tagenistai", "telmeses",
    "telmeses", "triphales", "phoinissai", "horai",
    "adelon_dramaton", "adelon_dramaton", "adelon_dramaton",
    "adelon_dramaton", "adelon_dramaton", "adelon_dramaton",
    "adelon_dramaton", "adelon_dramaton", "adelon_dramaton",
    "fragmenta_dubia",
)

TITLES = {
    "daitaleis": "ΔΑΙΤΑΛΕΙΣ", "babylonioi": "ΒΑΒΥΛΩΝΙΟΙ",
    "proagon": "ΠΡΟΑΓΩΝ", "amphiareos": "ΑΜΦΙΑΡΕΩΣ",
    "ploutos_a": "ΠΛΟΥΤΟΣ Α", "aiolosikon": "ΑΙΟΛΟΣΙΚΩΝ",
    "kokalos": "ΚΩΚΑΛΟΣ", "anagyros": "ΑΝΑΓΥΡΟΣ",
    "georgoi": "ΓΕΩΡΓΟΙ", "gerytades": "ΓΗΡΥΤΑΔΗΣ",
    "daidalos": "ΔΑΙΔΑΛΟΣ", "danaides": "ΔΑΝΑΙΔΕΣ",
    "dramata_e_kentauros": "ΔΡΑΜΑΤΑ Η ΚΕΝΤΑΥΡΟΣ",
    "dramata_e_niobos": "ΔΡΑΜΑΤΑ Η ΝΙΟΒΟΣ", "dramata": "ΔΡΑΜΑΤΑ",
    "heroes": "ΗΡΩΕΣ",
    "thesmophoriazousai_deuterai": "ΘΕΣΜΟΦΟΡΙΑΖΟΥΣΑΙ ΔΕΥΤΕΡΑΙ",
    "lemniai": "ΛΗΜΝΙΑΙ", "nauagos": "ΝΑΥΑΓΟΣ", "nesoi": "ΝΗΣΟΙ",
    "olkades": "ΟΛΚΑΔΕΣ", "pelargoi": "ΠΕΛΑΡΓΟΙ", "poiesis": "ΠΟΙΗΣΙΣ",
    "polyidos": "ΠΟΛΥΙΔΟΣ",
    "skenas_katalambanousai": "ΣΚΗΝΑΣ ΚΑΤΑΛΑΜΒΑΝΟΥΣΑΙ",
    "tagenistai": "ΤΑΓΗΝΙΣΤΑΙ", "telmeses": "ΤΕΛΜΗΣΗΣ",
    "triphales": "ΤΡΙΦΑΛΗΣ", "phoinissai": "ΦΟΙΝΙΣΣΑΙ", "horai": "ΩΡΑΙ",
    "adelon_dramaton": "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ",
    "fragmenta_dubia": "FRAGMENTA DUBIA",
}

NONPLAYS = {"adelon_dramaton", "fragmenta_dubia"}


def q(local: str) -> str:
    return f"{{{TEI}}}{local}"


def text(element) -> str:
    return " ".join("".join(element.itertext()).split())


def local_number(fragment) -> str | None:
    """Read Dindorf's parenthesized, per-work number from the source note."""
    note = fragment.find(q("note"))
    value = text(note) if note is not None else ""
    match = re.match(
        r"^(?:\d+\s*[a-z]?\s*\.\s*)?\(\s*(\d+)\s*([a-z]?)\s*\.\s*\)",
        value, flags=re.I,
    )
    if match:
        return match.group(1) + (match.group(2).lower() if match.group(2) else "")
    return None


def number_key(value: str) -> tuple[int, str]:
    match = re.match(r"^(\d+)\s*([a-z]?)", value or "", flags=re.I)
    return ((int(match.group(1)), match.group(2).lower())
            if match else (10**9, value or ""))


def dedupe_georgoi(fragments):
    """Remove the demonstrable repeated column on printed page 724."""
    kept = []
    fingerprints = {}
    for fragment in fragments:
        normalized = unicodedata.normalize("NFKD", text(fragment)).casefold()
        fingerprint = "".join(char for char in normalized if char.isalnum())
        prior = fingerprints.get(fingerprint)
        if prior is None:
            fingerprints[fingerprint] = fragment
            kept.append(fragment)
        elif len(etree.tostring(fragment)) > len(etree.tostring(prior)):
            kept[kept.index(prior)] = fragment
            fingerprints[fingerprint] = fragment
    return kept


def assign_local_numbers(fragments, work):
    """Restore printed local numbering while retaining genuine gaps."""
    explicit = [local_number(fragment) for fragment in fragments]
    labels = []
    current = 0
    for index, fragment in enumerate(fragments):
        label = explicit[index]
        if label is None and work in NONPLAYS:
            raw = fragment.get("n") or ""
            # Incerta pages already use the local series except for the final
            # page, whose notes explicitly carry 232-243.
            if number_key(raw)[0] <= 243:
                label = re.sub(r"\s+", "", raw).lower()
        if label is None:
            label = str(current + 1)
        current = max(current, number_key(label)[0])
        labels.append(label)

    # Explicit anchors reveal omissions (for example Amphiaraos 1-22 has one
    # absent record).  Fill backwards between anchors instead of silently
    # closing such printed gaps.
    for right, label in enumerate(explicit):
        if label is None:
            continue
        right_number = number_key(label)[0]
        left = right - 1
        while left >= 0 and explicit[left] is None:
            candidate = right_number - (right - left)
            if candidate > 0 and (left == 0 or number_key(labels[left - 1])[0] < candidate):
                labels[left] = str(candidate)
            left -= 1
    return labels


def normalize(source: Path):
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition.set("n", EDITION_URN)
    edition.set(f"{{{XML}}}base", EDITION_URN)
    edition.getparent().set(f"{{{XML}}}base", EDITION_URN)
    sections = edition.xpath("./tei:div[@subtype='section']", namespaces=NS)
    if len(sections) != len(SECTION_TARGETS):
        raise ValueError(f"Expected {len(SECTION_TARGETS)} page sections, found {len(sections)}")

    grouped = defaultdict(list)
    for index, (section, default_work) in enumerate(zip(sections, SECTION_TARGETS)):
        for fragment in section.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            original = re.sub(r"\s+", "", fragment.get("n") or "").lower()
            work = default_work
            # Printed page 721 continues Ploutos A (107-108) before the new
            # Aiolosikon heading at corpus fragment 109.
            if index == 7 and number_key(original)[0] <= 108:
                work = "ploutos_a"
            section.remove(fragment)
            grouped[work].append(fragment)
        edition.remove(section)

    if "georgoi" in grouped:
        grouped["georgoi"] = dedupe_georgoi(grouped["georgoi"])

    for work, fragments in grouped.items():
        labels = assign_local_numbers(fragments, work)
        container = etree.Element(q("div"))
        container.set("type", "textpart")
        container.set("subtype", "section" if work in NONPLAYS else "play")
        container.set("n", work)
        container.set(XID, f"aristophanes-dindorf-{work.replace('_', '-')}")
        collection = ("fragmentarycollections.v1" if work in NONPLAYS
                      else "fragmentaryplays.v1")
        container.set("corresp", f"urn:cite2:perseus:{collection}:tlg0019_{work}")
        etree.SubElement(container, q("head")).text = TITLES[work]
        used = set()
        numbered_fragments = sorted(
            zip(fragments, labels), key=lambda pair: number_key(pair[1]))
        for fragment, label in numbered_fragments:
            if label in used:
                suffix = 2
                while f"{label}-{suffix}" in used:
                    suffix += 1
                label = f"{label}-{suffix}"
            used.add(label)
            fragment.set("n", label)
            safe = re.sub(r"[^0-9A-Za-z]+", "-", label).strip("-") or "unit"
            fragment.set(XID, f"aristophanes-dindorf-{work.replace('_', '-')}-{safe}")
            fragment.set("corresp", container.get("corresp"))
            for line_index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1):
                line.set("n", str(line_index))
                line.set(XID, f"{fragment.get(XID)}-l{line_index}")
                line.set(f"{{{XML}}}lang", "grc")
            container.append(fragment)
        edition.append(container)

    refs = tree.xpath("//tei:encodingDesc/tei:refsDecl", namespaces=NS)[0]
    for child in list(refs):
        refs.remove(child)
    refs.text = None
    outer = etree.SubElement(refs, q("citeStructure"), match="/TEI/text/body", use="@xml:base")
    work_cite = etree.SubElement(
        outer, q("citeStructure"), unit="work",
        match="div/div[@subtype='play' or @subtype='section']", use="@n")
    fragment_cite = etree.SubElement(
        work_cite, q("citeStructure"), unit="fragment",
        match="div[@subtype='fragment']", use="@n")
    etree.SubElement(fragment_cite, q("citeStructure"), unit="line", match="lg/l", use="@n")
    revision = tree.xpath("//tei:revisionDesc", namespaces=NS)[0]
    change = etree.SubElement(revision, q("change"), when="2026-10-09")
    change.text = (
        "Folded page-local headings into stable Aristophanic work identities, restored "
        "Dindorf's per-work numbering, and removed demonstrable duplicate page-724 records; "
        "transcribed content otherwise unchanged. Geras is absent from the source extraction."
    )
    return tree


def write_cts(path: Path):
    root = etree.Element(f"{{{CTS}}}work", nsmap={"ti": CTS})
    root.set("urn", "urn:cts:greekLit:tlg0019.fragmenta")
    root.set("groupUrn", "urn:cts:greekLit:tlg0019")
    root.set(f"{{{XML}}}lang", "grc")
    etree.SubElement(root, f"{{{CTS}}}title", {f"{{{XML}}}lang": "eng"}).text = "Fragments"
    edition = etree.SubElement(
        root, f"{{{CTS}}}edition", urn=EDITION_URN,
        workUrn="urn:cts:greekLit:tlg0019.fragmenta")
    edition.set(f"{{{XML}}}lang", "grc")
    etree.SubElement(edition, f"{{{CTS}}}label", {f"{{{XML}}}lang": "eng"}).text = (
        "Greek (Dindorf, 1893; OCR draft)")
    etree.SubElement(edition, f"{{{CTS}}}description", {f"{{{XML}}}lang": "eng"}).text = (
        "Aristophanic fragments edited by Wilhelm Dindorf in Poetarum scenicorum "
        "Graecorum, pages 716-745. OCR-derived transcription requiring review.")
    path.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(
        str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    destination = (args.data_dir / "tlg0019/fragments/source" /
                   f"tlg0019.fragmenta.{VERSION}.xml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalize(args.source).write(
        str(destination), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    write_cts(args.data_dir / "tlg0019/fragments/__cts__.xml")
    print(destination)


if __name__ == "__main__":
    main()
