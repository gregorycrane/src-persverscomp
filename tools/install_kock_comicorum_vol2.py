#!/usr/bin/env python3
"""Split Kock, CAF II into canonical CTS author/work files.

The scan-first extraction preserves page typography, including running heads
that were sometimes interpreted as author boundaries.  This installer restores
the bibliographical hierarchy before publishing: canonical TLG authors own
work-level files, genitive running heads remain with their authors, and the few
mixed boundary blocks are split fragment by fragment.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from lxml import etree


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "kock_vol1_installer", HERE / "install_kock_comicorum_vol1.py"
)
base = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(base)

base.VERSION = VERSION = "kock1884-grc1"
NS = base.NS
CTS = base.CTS
XLANG = base.XLANG
VOLUME1_MAKE_HEADER = base.make_header


AUTHORS = {
    "antiphanes": ("0410", "ANTIPHANES"),
    "anaxandrides": ("0405", "ANAXANDRIDES"),
    "eubulus": ("0458", "EUBULUS"),
    "araros": ("0415", "ARAROS"),
    "nicostratus": ("0484", "NICOSTRATUS"),
    "philetaerus": ("0489", "PHILETAERUS"),
    "amphis": ("0404", "AMPHIS"),
    "ephippus": ("0450", "EPHIPPUS"),
    "anaxilas": ("0406", "ANAXILAS"),
    "aristophon": ("0421", "ARISTOPHON"),
    "epicrates": ("0451", "EPICRATES"),
    "cratinus_junior": ("0435", "CRATINUS JUNIOR"),
    "ophelio": ("0485", "OPHELIO"),
    "nausicrates": ("0478", "NAUSICRATES"),
    "euphanes": ("0396", "EUPHANES"),
    "alexis": ("0402", "ALEXIS"),
    "clearchus": ("0432", "CLEARCHUS"),
    "antidotus": ("0409", "ANTIDOTUS"),
    "axionicus": ("0424", "AXIONICUS"),
    # No TLG author records exist for these two minor comic poets in the
    # supplied canon-keys.txt; the 9001/9002 identifiers are explicitly local.
    "callicrates": ("9001", "CALLICRATES COMICUS [LOCAL ID]"),
    "epigenes": ("0452", "EPIGENES"),
    "dromon": ("9002", "DROMON COMICUS [LOCAL ID]"),
    "diodorus": ("0444", "DIODORUS"),
    "dionysius": ("0445", "DIONYSIUS"),
    "eriphus": ("0455", "ERIPHUS"),
    "eubulides": ("0457", "EUBULIDES"),
    "heniochus": ("0465", "HENIOCHUS"),
    "heraclides": ("0466", "HERACLIDES"),
    "heraclitus": ("1784", "[HERACLITUS] COMICUS"),
    "mnesimachus": ("0476", "MNESIMACHUS"),
    "simylus": ("0398", "SIMYLUS"),
    "sophilus": ("0502", "SOPHILUS"),
    "sotades": ("0505", "SOTADES"),
    "timotheus": ("0517", "TIMOTHEUS"),
    "timocles": ("0515", "TIMOCLES"),
    "xenarchus": ("0518", "XENARCHUS"),
    "theophilus": ("0512", "THEOPHILUS"),
    "philemon": ("0487", "PHILEMON"),
    "philemon_junior": ("0488", "PHILEMON JUNIOR"),
    "diphilus": ("0447", "DIPHILUS"),
}


# Inclusive ranges in the 130 extracted author/running-head blocks.
SECTION_RANGES = (
    (1, 23, "antiphanes"), (24, 27, "anaxandrides"),
    (28, 37, "eubulus"), (38, 39, "araros"),
    (40, 44, "nicostratus"), (45, 47, "philetaerus"),
    (48, 53, "amphis"), (54, 55, "ephippus"),
    (56, 56, "anaxilas"), (57, 63, "aristophon"),
    (64, 65, "epicrates"), (66, 68, "cratinus_junior"),
    (69, 69, "ophelio"), (70, 70, "nausicrates"),
    (71, 71, "euphanes"), (72, 92, "alexis"),
    (93, 93, "clearchus"), (94, 94, "antidotus"),
    (95, 96, "axionicus"), (97, 97, "callicrates"),
    (98, 99, "epigenes"), (100, 100, "dromon"),
    (101, 101, "diodorus"), (102, 102, "dionysius"),
    (103, 103, "eriphus"), (104, 104, "eubulides"),
    (105, 105, "heniochus"), (106, 106, "heraclides"),
    (107, 107, "heraclitus"), (108, 109, "mnesimachus"),
    (110, 110, "simylus"), (111, 111, "sophilus"),
    (112, 112, "sotades"), (113, 113, "timotheus"),
    (114, 116, "timocles"), (117, 118, "xenarchus"),
    (119, 122, "theophilus"), (123, 126, "philemon"),
    (127, 127, "philemon_junior"), (128, 130, "diphilus"),
)


# Whole works carried over a true author boundary.
WORK_OWNER_OVERRIDES = {
    (56, 0): "ephippus",
    (94, 0): "clearchus",
}


# Mixed work blocks: keys are (section, work index, fragment index).
FRAGMENT_OWNER_OVERRIDES = {
    (64, 0, 0): "aristophon",       # Aristophon fr. 16
    (95, 0, 0): "antidotus",        # Antidotus frr. 3–4
    (95, 0, 1): "antidotus",
    (103, 0, 0): "dionysius",       # Dionysius fr. 1; Eriphus fr. 7 follows
    (122, 0, 1): "philemon",        # Philemon, Pankratiastes fr. 53
}


# These boundary blocks really are anonymous fragments, despite a misleading
# next-author or composite running head.
KEEP_ANONYMOUS = {(56, 0), (64, 0), (68, 0), (94, 0), (103, 0)}
ANONYMOUS = {"ΑΔΗΛΟΥ ΔΡΑΜΑΤΟΣ", "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ", "ΑΔΗΛΑ ΔΡΑΜΑΤΑ"}


AUTHOR_HEADING_FORMS = {
    "ANTIPHANES", "ΑΝΤΙΦΑΝΗΣ", "ΑΝΤΙΦΑΝΟΥΣ", "ΑΝΑΞΑΝΔΡΙΔΗΣ", "ΑΝΑΞΑΝΔΡΙΔΟΥ",
    "ΕΥΒΟΥΛΟΣ", "ΕΥΒΟΥΛΟΥ", "ΕΥΒΟΥΛΟΥ ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ", "ΑΡΑΡΩΣ", "ΑΡΑΡΟΤΟΣ",
    "ΝΙΚΟΣΤΡΑΤΟΣ", "ΝΙΚΟΣΤΡΑΤΟΥ", "ΦΙΛΕΤΑΙΡΟΣ", "ΦΙΛΕΤΑΙΡΟΥ", "ΑΜΦΙΣ",
    "ΑΜΦΙΔΟΣ", "ΕΦΙΠΠΟΣ", "ΕΦΙΠΠΟΥ", "ΑΝΑΞΙΛΑΣ", "ΑΡΙΣΤΟΦΩΝ", "ΑΡΙΣΤΟΦΩΝΤΟΣ",
    "ΕΠΙΚΡΑΤΗΣ", "ΕΠΙΚΡΑΤΟΥΣ", "ΚΡΑΤΙΝΟΣ Ο ΝΕΩΤΕΡΟΣ", "ΚΡΑΤΙΝΟΣ", "ΩΦΕΛΙΩΝ",
    "ΝΑΥΣΙΚΡΑΤΗΣ", "ΕΥΦΑΝΗΣ", "ΑΛΕΞΙΣ", "ΑΛΕΞΙΔΟΣ", "ΚΛΕΑΡΧΟΣ", "ΑΝΤΙΔΟΤΟΣ",
    "ΑΞΙΟΝΙΚΟΣ", "ΑΞΙΟΝΙΚΟΥ", "ΚΑΛΛΙΚΡΑΤΗΣ", "ΕΠΙΓΕΝΗΣ", "ΕΠΙΓΕΝΟΥΣ", "ΔΡΟΜΩΝ",
    "ΔΙΟΔΩΡΟΣ", "ΔΙΟΝΥΣΙΟΥ", "ΕΡΙΦΟΣ", "ΕΥΒΟΥΛΙΔΗΣ", "ΗΝΙΟΧΟΣ", "ΗΡΑΚΛΕΙΔΗΣ",
    "ΗΡΑΚΛΕΙΤΟΣ", "ΜΝΗΣΙΜΑΧΟΣ", "ΜΝΗΣΙΜΑΧΟΥ", "ΣΙΜΥΛΟΣ", "ΣΩΦΙΛΟΣ", "ΣΩΤΑΔΗΣ",
    "ΤΙΜΟΘΕΟΣ", "ΤΙΜΟΚΛΗΣ", "ΤΙΜΟΚΛΕΟΥΣ", "ΞΕΝΑΡΧΟΣ", "ΞΕΝΑΡΧΟΥ", "ΘΕΟΦΙΛΟΣ",
    "ΘΕΟΦΙΛΟΥ", "ΦΙΛΗΜΩΝ", "ΦΙΛΗΜΟΝΟΣ", "PHILEMON", "ΦΙΛΗΜΩΝ Ο ΝΕΩΤΕΡΟΣ",
    "ΔΙΦΙΛΟΣ", "ΔΙΦΙΛΟΥ",
}


def section_owners():
    result = {}
    for start, end, owner in SECTION_RANGES:
        for section in range(start, end + 1):
            result[section] = owner
    return result


def work_title(section_index, work_index, section_heading, raw_title):
    title = base.canonical_title(raw_title)
    if title not in ANONYMOUS or (section_index, work_index) in KEEP_ANONYMOUS:
        return title
    heading = base.canonical_title(section_heading)
    if heading in AUTHOR_HEADING_FORMS or "ΑΔΗΛΩΝ ΔΡΑΜΑΤΩΝ" in heading:
        return title
    return heading


def collect(source: Path):
    tree = etree.parse(str(source))
    sections = tree.xpath("//tei:div[@subtype='author']", namespaces=NS)
    if len(sections) != 130:
        raise ValueError(f"Expected 130 extracted author/running-head blocks; found {len(sections)}")
    owners = section_owners()
    grouped = defaultdict(lambda: defaultdict(list))
    skipped = []
    for section_index, section in enumerate(sections, 1):
        default_owner = owners[section_index]
        for work_index, work in enumerate(
            section.xpath("./tei:div[@subtype='work']", namespaces=NS)
        ):
            fragments = work.xpath("./tei:div[@subtype='fragment']", namespaces=NS)
            if not fragments:
                skipped.append({
                    "section": section_index,
                    "heading": section.get("n"),
                    "title": base.canonical_title(work.get("n")),
                    "reason": "heading has no separately quoted fragment text",
                })
                continue
            title = work_title(section_index, work_index, section.get("n"), work.get("n"))
            work_owner = WORK_OWNER_OVERRIDES.get((section_index, work_index), default_owner)
            for fragment_index, fragment in enumerate(fragments):
                owner = FRAGMENT_OWNER_OVERRIDES.get(
                    (section_index, work_index, fragment_index), work_owner
                )
                grouped[AUTHORS[owner]][title].append(deepcopy(fragment))
    return tree, grouped, skipped


def make_header(source_tree, latin_name, title, has_lines):
    header = VOLUME1_MAKE_HEADER(source_tree, latin_name, title, has_lines)
    for node in header.iter():
        if node.text:
            node.text = node.text.replace("Kock 1880", "Kock 1884")
            node.text = node.text.replace("volume-level OCR draft", "volume-level OCR draft")
    return header


base.make_header = make_header


def update_work_metadata(path, tlg, work_slug, title, urn):
    work_urn = f"urn:cts:greekLit:tlg{tlg}.{work_slug}"
    if path.exists():
        tree = etree.parse(str(path)); root = tree.getroot()
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
            f"Greek (Kock, 1884; OCR draft): {title}"
        )
        etree.SubElement(edition, f"{{{CTS}}}description", {XLANG: "eng"}).text = (
            "Fragments edited by Theodor Kock in Comicorum Atticorum Fragmenta, "
            "volume 2 (Leipzig, 1884). Scan-first OCR transcription requiring review."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def update_registry(path, records):
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
            "source_title": record["title"], "source_edition": "kock1884",
        })
        entry.setdefault("fragment_editions", {})[VERSION] = {
            "path": record["path"], "urn": record["urn"],
            "label": f"Greek (Kock, 1884; OCR draft): {record['title']}",
            "class": "greek-text", "format": "tei_fragment_work",
            "corresp_axis": "fragment",
        }
        if entry.get("source_edition") not in (None, "kock1884"):
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
        base.write_textgroup(args.data_dir / f"tlg{tlg}" / "__cts__.xml", tlg, latin_name)
        known_slugs = base.existing_work_slugs(args.data_dir, tlg)
        used_slugs = set(known_slugs.values())
        for title, fragments in sorted(works.items()):
            work_slug = known_slugs.get(title, base.slug(title))
            candidate = work_slug; counter = 2
            while candidate in used_slugs and known_slugs.get(title) != candidate:
                candidate = f"{work_slug}_{counter}"; counter += 1
            work_slug = candidate; used_slugs.add(work_slug)
            tree, urn = base.make_text(source_tree, tlg, work_slug, latin_name, title, fragments)
            work_dir = args.data_dir / f"tlg{tlg}" / work_slug
            destination = work_dir / f"tlg{tlg}.{work_slug}.{VERSION}.xml"
            work_dir.mkdir(parents=True, exist_ok=True)
            tree.write(str(destination), encoding="UTF-8", xml_declaration=True, pretty_print=True)
            update_work_metadata(work_dir / "__cts__.xml", tlg, work_slug, title, urn)
            records.append({"tlg": tlg, "author": latin_name, "work": work_slug,
                            "title": title, "urn": urn, "path": str(destination),
                            "fragments": len(fragments)})
    if args.registry:
        update_registry(args.registry, records)
    report = {
        "generated": records, "skipped_empty_headings": skipped,
        "generated_files": len(records),
        "generated_fragments": sum(record["fragments"] for record in records),
        "local_authorities": {"tlg9001": "Callicrates Comicus", "tlg9002": "Dromon Comicus"},
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("generated_files", "generated_fragments")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
