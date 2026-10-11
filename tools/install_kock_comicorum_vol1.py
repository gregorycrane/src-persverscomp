#!/usr/bin/env python3
"""Split Kock, CAF I into CTS author/work files and register them in the viewer.

The extraction notebook necessarily treated some running heads as new authors.
AUTHOR_GROUPS records the canonical author boundaries established from the TLG
canon list; CONTINUATION_WORKS records running heads that continue a named work.
No source wording is changed by this installer.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI, "ti": CTS}
XLANG = f"{{{XML}}}lang"
XBASE = f"{{{XML}}}base"
XID = f"{{{XML}}}id"
VERSION = "kock1880-grc1"


def q(name: str) -> str:
    return f"{{{TEI}}}{name}"


# Inclusive section ranges in the notebook's 103 extracted author blocks.
# TLG identifiers and Latin names come from canon-keys.txt.
AUTHOR_GROUPS = (
    (1, 1, "0264", "SUSARION"),
    (2, 4, "0431", "CHIONIDES"),
    (5, 6, "0474", "MAGNES"),
    (7, 8, "0449", "ECPHANTIDES"),
    (9, 11, "0434", "CRATINUS"),
    (12, 13, "0433", "CRATES"),
    (14, 16, "0486", "PHERECRATES"),
    (17, 20, "0510", "TELECLIDES"),
    (21, 22, "0252", "HERMIPPUS"),
    (23, 23, "0477", "MYRTILUS"),
    (24, 24, "1780", "ALCIMENES"),
    (25, 26, "0492", "PHILONIDES"),
    (27, 30, "0461", "EUPOLIS"),
    (31, 33, "0496", "PHRYNICHUS"),
    (34, 45, "0019", "ARISTOPHANES"),
    (46, 53, "0497", "PLATO COMICUS"),
    (54, 54, "0420", "ARISTONYMUS"),
    (55, 57, "0403", "AMIPSIAS"),
    (58, 59, "0417", "ARCHIPPUS"),
    (60, 61, "0419", "ARISTOMENES"),
    (62, 63, "0426", "CALLIAS"),
    (64, 64, "0463", "HEGEMON"),
    (65, 65, "0472", "LYSIPPUS"),
    (66, 66, "0470", "LEUCO"),
    (67, 68, "0475", "METAGENES"),
    (69, 70, "0418", "ARISTAGORAS"),
    (71, 74, "0508", "STRATTIS"),
    (75, 79, "0513", "THEOPOMPUS"),
    (80, 83, "0400", "ALCAEUS COMICUS"),
    (84, 84, "0428", "CANTHARUS"),
    (85, 86, "0443", "DIOCLES COMICUS"),
    (87, 88, "0480", "NICOCHARES"),
    (89, 90, "0483", "NICOPHON"),
    (91, 91, "0459", "EUNICUS"),
    (92, 93, "0494", "PHILYLLIUS"),
    (94, 96, "0499", "POLYZELUS"),
    (97, 97, "0501", "SANNYRION"),
    (98, 98, "0439", "DEMETRIUS COMICUS"),
    (99, 100, "0414", "APOLLOPHANES"),
    (101, 102, "0429", "CEPHISODORUS"),
    (103, 103, "0453", "EPILYCUS"),
)


# A source work called ADHLOU DRAMATOS under these running heads is a page
# continuation of the named work, not a new anonymous-work section.
CONTINUATION_WORKS = {
    11: "ΔΡΑΠΕΤΙΔΕΣ", 16: "ΜΕΤΑΛΛΗΣ", 19: "ΗΣΙΟΔΟΙ",
    29: "ΑΥΤΟΛΥΚΟΣ", 32: "ΚΟΝΝΟΣ", 36: "ΑΝΑΓΥΡΟΣ",
    38: "ΓΗΡΥΤΑΔΗΣ", 39: "ΓΗΡΥΤΑΔΗΣ", 40: "ΚΩΚΑΛΟΣ",
    42: "ΤΡΙΦΑΛΗΣ", 43: "ΤΡΙΦΑΛΗΣ", 44: "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    45: "ΨΕΥΔΕΠΙΓΡΑΦΑ", 48: "ΚΛΕΟΦΩΝ", 51: "ΠΕΙΣΑΝΔΡΟΣ",
    53: "ΥΠΕΡΒΟΛΟΣ", 57: "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ",
    69: "ΜΑΜΜΑΚΥΘΟΣ", 73: "ΚΙΝΗΣΙΑΣ", 77: "ΗΔΥΧΑΡΗΣ",
    82: "ΚΑΛΛΙΣΤΩ", 83: "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    94: "ΔΗΜΟΤΥΝΔΑΡΕΩΣ", 96: "ΜΟΥΣΩΝ ΓΟΝΑΙ",
}


ALIASES = {
    "ΑΔΗΛΟΥ ΔΡΑΜΑΤΟΣ": "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ",
    "ΑΔΗΛΩΝ ΔΡ": "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ",
    "ΑΔΗΛΩΝ ΔΡ ΑΜΦΙΣΒΗΤΗΣΙΜΑ": "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ ΑΜΦΙΣΒΗΤΗΣΙΜΑ": "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    "ΑΜΦΙΣΒΗΤΗΣΙΜΟΝ": "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    "ΑΜΦΙΣΒΗΤΗΣΙΜΑ ΚΑΙ ΨΕΥΔΕΠΙΓΡΑΦΑ": "ΑΜΦΙΣΒΗΤΗΣΙΜΑ",
    "ΚΡΑΠΑΤΑΛΛΟΙ": "ΚΡΑΠΑΤΑΛΟΙ",
    "ΟΔΥΣΣΗΣ": "ΟΔΥΣΣΕΥΣ",
    "ΟΔΥΣΣΕΙΣ": "ΟΔΥΣΣΕΥΣ",
    "ΟΔΥΣΣΕΥΣΙ": "ΟΔΥΣΣΕΥΣ",
    "ΑΔΩΝΙΟΝ": "ΑΔΩΝΙΣ",
    "ΑΔΩΝΙΔΙ": "ΑΔΩΝΙΣ",
    "ΑΔΩΝΙΔΟΣ": "ΑΔΩΝΙΣ",
    "ΥΠΕΡΒΟΛΩ": "ΥΠΕΡΒΟΛΟΣ",
    "ΜΑΚΕΔΟΝΙΣΣΑΝ": "ΜΑΚΕΔΟΝΕΣ Η ΠΑΥΣΑΝΙΑΣ",
}


def plain(value: str | None) -> str:
    value = unicodedata.normalize("NFD", value or "").upper().replace("Σ", "Σ")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("Ϲ", "Σ").replace("ς", "Σ")
    return " ".join(re.findall(r"[A-ZΑ-Ω0-9]+", value))


def canonical_title(value: str | None) -> str:
    normalized = plain(value)
    return ALIASES.get(normalized, normalized or "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ")


GREEK_ASCII = str.maketrans({
    "Α": "a", "Β": "b", "Γ": "g", "Δ": "d", "Ε": "e", "Ζ": "z",
    "Η": "e", "Θ": "th", "Ι": "i", "Κ": "k", "Λ": "l", "Μ": "m",
    "Ν": "n", "Ξ": "x", "Ο": "o", "Π": "p", "Ρ": "r", "Σ": "s",
    "Τ": "t", "Υ": "y", "Φ": "ph", "Χ": "ch", "Ψ": "ps", "Ω": "o",
})


def slug(value: str) -> str:
    value = plain(value).translate(GREEK_ASCII).lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_") or "fragmenta"


def safe_ref(value: str | None, fallback: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = re.sub(r"[^\w\d]+", "_", value, flags=re.UNICODE).strip("_")
    return value or fallback


def source_index_to_author() -> dict[int, tuple[str, str]]:
    result = {}
    for start, end, tlg, name in AUTHOR_GROUPS:
        for index in range(start, end + 1):
            result[index] = (tlg, name)
    return result


def existing_work_slugs(data_dir: Path, tlg: str) -> dict[str, str]:
    result = {}
    root = data_dir / f"tlg{tlg}"
    if not root.exists():
        return result
    for metadata in root.glob("*/__cts__.xml"):
        try:
            tree = etree.parse(str(metadata))
            title = tree.xpath("string(/*[local-name()='work']/*[local-name()='title'][1])")
            if title:
                result[canonical_title(title)] = metadata.parent.name
        except etree.XMLSyntaxError:
            continue
    return result


def collect(source: Path):
    tree = etree.parse(str(source))
    sections = tree.xpath("//tei:div[@subtype='author']", namespaces=NS)
    if len(sections) != 103:
        raise ValueError(f"Expected 103 extracted author sections; found {len(sections)}")
    owners = source_index_to_author()
    grouped = defaultdict(lambda: defaultdict(list))
    skipped = []
    for index, author in enumerate(sections, 1):
        tlg, latin_name = owners[index]
        works = author.xpath("./tei:div[@subtype='work']", namespaces=NS)
        for work in works:
            title = canonical_title(work.get("n"))
            if index in CONTINUATION_WORKS and title == "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ":
                title = CONTINUATION_WORKS[index]
            fragments = work.xpath("./tei:div[@subtype='fragment']", namespaces=NS)
            if not fragments:
                skipped.append({"section": index, "author": latin_name, "title": title,
                                "reason": "heading has no fragment text"})
                continue
            grouped[(tlg, latin_name)][title].extend(deepcopy(fragment) for fragment in fragments)
    return tree, grouped, skipped


def make_header(source_tree, latin_name: str, title: str, has_lines: bool):
    header = deepcopy(source_tree.xpath("/tei:TEI/tei:teiHeader", namespaces=NS)[0])
    title_stmt = header.find(f".//{q('titleStmt')}")
    for old in list(title_stmt.findall(q("title"))):
        title_stmt.remove(old)
    etree.SubElement(title_stmt, q("title")).text = f"{latin_name}, {title}: fragments"
    etree.SubElement(title_stmt, q("title"), type="sub").text = (
        "Kock 1880: OCR-derived diplomatic TEI transcription")
    author_node = title_stmt.find(q("author"))
    if author_node is None:
        author_node = etree.SubElement(title_stmt, q("author"))
    author_node.text = latin_name.title()
    encoding = header.find(f".//{q('encodingDesc')}")
    for old in list(encoding.findall(q("refsDecl"))):
        encoding.remove(old)
    refs = etree.SubElement(encoding, q("refsDecl"), n="CTS")
    if has_lines:
        line = etree.SubElement(refs, q("cRefPattern"), n="line", matchPattern=r"(\w+)\.(\w+)",
            replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@subtype='fragment' and @n='$1']//tei:l[@n='$2'])")
        etree.SubElement(line, q("p")).text = "This pointer pattern extracts lines within fragments."
    fragment = etree.SubElement(refs, q("cRefPattern"), n="fragment", matchPattern=r"(\w+)",
        replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@subtype='fragment' and @n='$1'])")
    etree.SubElement(fragment, q("p")).text = "This pointer pattern extracts fragments."
    revision = header.find(f".//{q('revisionDesc')}")
    if revision is None:
        revision = etree.SubElement(header, q("revisionDesc"))
    change = etree.SubElement(revision, q("change"), when="2026-10-10")
    change.text = (
        "Split the volume-level OCR draft into canonical TLG author and work files. "
        "Running-head continuations were folded into their works; wording was not corrected. "
        "The page image remains authoritative and the transcription requires human review.")
    return header


def make_text(source_tree, tlg: str, work_slug: str, latin_name: str,
              title: str, fragments: list[etree._Element]):
    urn = f"urn:cts:greekLit:tlg{tlg}.{work_slug}.{VERSION}"
    root = etree.Element(q("TEI"), nsmap={None: TEI})
    has_lines = any(fragment.xpath(".//tei:l", namespaces=NS) for fragment in fragments)
    root.append(make_header(source_tree, latin_name, title, has_lines))
    text = etree.SubElement(root, q("text"))
    text.set(XBASE, urn)
    text.set(XLANG, "grc")
    body = etree.SubElement(text, q("body"), n=urn)
    body.set(XLANG, "grc")
    edition = etree.SubElement(body, q("div"), type="edition", n=urn)
    edition.set(XLANG, "grc")
    edition.set("corresp", f"urn:cite2:perseus:fragmentaryplays.v1:tlg{tlg}_{work_slug}")
    etree.SubElement(edition, q("head")).text = title
    used = set()
    for position, fragment in enumerate(fragments, 1):
        number = safe_ref(fragment.get("n"), str(position))
        base = number
        suffix = 2
        while number in used:
            number = f"{base}_{suffix}"
            suffix += 1
        used.add(number)
        fragment.set("n", number)
        fragment.set(XID, f"kock-{tlg}-{work_slug}-{safe_ref(number, str(position))}")
        fragment.set("corresp", edition.get("corresp"))
        line_used = set()
        for line_position, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1):
            line_number = safe_ref(line.get("n"), str(line_position))
            line_base = line_number
            line_suffix = 2
            while line_number in line_used:
                line_number = f"{line_base}_{line_suffix}"
                line_suffix += 1
            line_used.add(line_number)
            line.set("n", line_number)
            line.set(XID, f"{fragment.get(XID)}-l{safe_ref(line_number, str(line_position))}")
            line.set(XLANG, "grc")
        edition.append(fragment)
    return etree.ElementTree(root), urn


def write_textgroup(path: Path, tlg: str, latin_name: str):
    if path.exists():
        return
    root = etree.Element(f"{{{CTS}}}textgroup", nsmap={"ti": CTS},
                         urn=f"urn:cts:greekLit:tlg{tlg}", projid=f"greekLit:tlg{tlg}")
    etree.SubElement(root, f"{{{CTS}}}groupname", {XLANG: "eng"}).text = latin_name.title()
    path.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(str(path), encoding="UTF-8", xml_declaration=True,
                                  pretty_print=True)


def update_work_metadata(path: Path, tlg: str, work_slug: str, title: str, urn: str):
    work_urn = f"urn:cts:greekLit:tlg{tlg}.{work_slug}"
    if path.exists():
        tree = etree.parse(str(path))
        root = tree.getroot()
    else:
        root = etree.Element(f"{{{CTS}}}work", nsmap={"ti": CTS}, urn=work_urn,
                             groupUrn=f"urn:cts:greekLit:tlg{tlg}")
        root.set(XLANG, "grc")
        etree.SubElement(root, f"{{{CTS}}}title", {XLANG: "grc"}).text = title
        tree = etree.ElementTree(root)
    if not root.xpath("./ti:edition[@urn=$urn]", namespaces=NS, urn=urn):
        edition = etree.SubElement(root, f"{{{CTS}}}edition", urn=urn, workUrn=work_urn)
        edition.set(XLANG, "grc")
        etree.SubElement(edition, f"{{{CTS}}}label", {XLANG: "eng"}).text = (
            f"Greek (Kock, 1880; OCR draft): {title}")
        etree.SubElement(edition, f"{{{CTS}}}description", {XLANG: "eng"}).text = (
            "Fragments edited by Theodor Kock in Comicorum Atticorum Fragmenta, "
            "volume 1 (Leipzig, 1880). OCR-derived transcription requiring review.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def update_registry(path: Path, records: list[dict]):
    registry = json.loads(path.read_text(encoding="utf-8"))
    for record in records:
        key = f"tlg{record['tlg']}.{record['work']}"
        entry = registry.setdefault(key, {
            "textgroup": f"tlg{record['tlg']}", "work": record["work"],
            "title": record["title"], "fragmentary": True,
            "record_type": "fragmentary_play", "editions": {}, "appcrits": {},
            "translations": {}, "commentaries": {}, "treebanks": {},
            "fragment_editions": {},
            "object_urn": f"urn:cite2:perseus:fragmentaryplays.v1:tlg{record['tlg']}_{record['work']}",
            "source_title": record["title"], "source_edition": "kock1880",
        })
        entry.setdefault("fragment_editions", {})[VERSION] = {
            "path": record["path"], "urn": record["urn"],
            "label": f"Greek (Kock, 1880; OCR draft): {record['title']}",
            "class": "greek-text", "format": "tei_fragment_work",
            "corresp_axis": "fragment",
        }
        if entry.get("source_edition") not in (None, "kock1880"):
            entry["source_edition"] = "multiple-fragment-editions"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source_tree, grouped, skipped = collect(args.source)
    records = []
    for (tlg, latin_name), works in sorted(grouped.items()):
        write_textgroup(args.data_dir / f"tlg{tlg}" / "__cts__.xml", tlg, latin_name)
        known_slugs = existing_work_slugs(args.data_dir, tlg)
        used_slugs = set(known_slugs.values())
        for title, fragments in sorted(works.items()):
            work_slug = known_slugs.get(title, slug(title))
            base = work_slug
            counter = 2
            while work_slug in used_slugs and known_slugs.get(title) != work_slug:
                work_slug = f"{base}_{counter}"
                counter += 1
            used_slugs.add(work_slug)
            tree, urn = make_text(source_tree, tlg, work_slug, latin_name, title, fragments)
            work_dir = args.data_dir / f"tlg{tlg}" / work_slug
            destination = work_dir / f"tlg{tlg}.{work_slug}.{VERSION}.xml"
            work_dir.mkdir(parents=True, exist_ok=True)
            tree.write(str(destination), encoding="UTF-8", xml_declaration=True,
                       pretty_print=True)
            update_work_metadata(work_dir / "__cts__.xml", tlg, work_slug, title, urn)
            records.append({"tlg": tlg, "author": latin_name, "work": work_slug,
                            "title": title, "urn": urn, "path": str(destination),
                            "fragments": len(fragments)})
    if args.registry:
        update_registry(args.registry, records)
    report = {"generated": records, "skipped_empty_headings": skipped,
              "generated_files": len(records),
              "generated_fragments": sum(r["fragments"] for r in records)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("generated_files", "generated_fragments")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
