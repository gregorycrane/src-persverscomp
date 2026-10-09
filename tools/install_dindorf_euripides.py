#!/usr/bin/env python3
"""Normalize and install Dindorf's Euripidean fragment TEI.

The notebook transcribes page-local headings faithfully enough for review, but
some running headers and italicized cited play names were promoted to section
headings.  It also assigned a corpus-wide extraction counter to ``@n``.  This
installer restores Dindorf's printed, per-play fragment numbering and stable
work identities without changing the transcribed Greek or apparatus.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI, "ti": CTS}
XID = f"{{{XML}}}id"
VERSION = "dindorf1893-grc1"
EDITION_URN = f"urn:cts:greekLit:tlg0006.fragmenta.{VERSION}"

# Section index is intentional: repeated page headers have identical @n values.
SECTION_TARGETS = (
    "aigeys", "aiolos", "alexandros", "alexandros",
    "alkmeon_a_et_b", "alkmeon_a_et_b", "alkmeon_a_et_b",
    "alkmeon_a_et_b", "alkmeon_a_et_b", "alkmene",
    "alope", "alope", "alope", "andromeda", "andromeda", "andromeda",
    "antigone", "antiope", "antiope", "antiope", "antiope",
    "archelaos", "ayge", "aytolykos_satyrikos",
    "bellerophontes", "bellerophontes", "bellerophontes",
    "boysiris_satyrikos", "danae", "danae", "diktys", "diktys",
    "epeios", "erechtheys", "erechtheys", "erechtheys",
    "eyrystheys_satyrikos", "theseye", "theseye", "thyestes",
    "ino", "ino", "ixion", "ixion", "ippolytos", "kadmos",
    "kresphontes", "kressai", "kressai", "kressai", "likymnios",
    "melanippe_e_sophe", "melanippe_e_desmotis", "melanippe_e_desmotis",
    "meleagros", "oidipots", "oinets", "oinomaos", "palamedes",
    "peirithoys", "peliades", "peleys", "pleisthenes", "polyidos",
    "polyidos", "protesilaos", "radamanoys", "stheneboia",
    "skiron_satyrikos", "skyrioi", "syleys_satyrikos",
    "syleys_satyrikos", "tennes", "telephos", "temenidai", "ypsipyle",
    "phaethon", "philoktetes", "philoktetes", "philoktetes", "phoinix",
    "phoinix", "phrixos", "phrixos", "chrysippos",
    "incertarvm_fabvlarvm_fragmenta", "incertarvm_fabvlarvm_fragmenta",
    "incertarvm_fabvlarvm_fragmenta", "incertarvm_fabvlarvm_fragmenta",
    "incertarvm_fabvlarvm_fragmenta", "incertarvm_fabvlarvm_fragmenta",
    "incertarvm_fabvlarvm_fragmenta", "incertarvm_fabvlarvm_fragmenta",
    "incertarvm_fabvlarvm_fragmenta", "incertarvm_fabvlarvm_fragmenta",
    "incertarvm_fabvlarvm_fragmenta",
    "epistolae", "epistolae", "epistolae", "epistolae",
    "epigramma_euripidi_adscriptum",
)

TITLES = {
    "aigeys": "ΑΙΓΕΥΣ", "aiolos": "ΑΙΟΛΟΣ", "alexandros": "ΑΛΕΞΑΝΔΡΟΣ",
    "alkmeon_a_et_b": "ΑΛΚΜΑΙΩΝ Α ΚΑΙ Β", "alkmene": "ΑΛΚΜΗΝΗ",
    "alope": "ΑΛΟΠΗ", "andromeda": "ΑΝΔΡΟΜΕΔΑ", "antigone": "ΑΝΤΙΓΟΝΗ",
    "antiope": "ΑΝΤΙΟΠΗ", "archelaos": "ΑΡΧΕΛΑΟΣ", "ayge": "ΑΥΓΗ",
    "aytolykos_satyrikos": "ΑΥΤΟΛΥΚΟΣ ΣΑΤΥΡΙΚΟΣ",
    "bellerophontes": "ΒΕΛΛΕΡΟΦΟΝΤΗΣ", "boysiris_satyrikos": "ΒΟΥΣΙΡΙΣ ΣΑΤΥΡΙΚΟΣ",
    "danae": "ΔΑΝΑΗ", "diktys": "ΔΙΚΤΥΣ", "epeios": "ΕΠΕΙΟΣ",
    "erechtheys": "ΕΡΕΧΘΕΥΣ", "eyrystheys_satyrikos": "ΕΥΡΥΣΘΕΥΣ ΣΑΤΥΡΙΚΟΣ",
    "theseye": "ΘΗΣΕΥΣ", "thyestes": "ΘΥΕΣΤΗΣ", "ino": "ΙΝΩ",
    "ixion": "ΙΞΙΩΝ", "ippolytos": "ΙΠΠΟΛΥΤΟΣ", "kadmos": "ΚΑΔΜΟΣ",
    "kresphontes": "ΚΡΕΣΦΟΝΤΗΣ", "kressai": "ΚΡΗΣΣΑΙ", "kretes": "ΚΡΗΤΕΣ",
    "likymnios": "ΛΙΚΥΜΝΙΟΣ", "melanippe_e_sophe": "ΜΕΛΑΝΙΠΠΗ Η ΣΟΦΗ",
    "melanippe_e_desmotis": "ΜΕΛΑΝΙΠΠΗ Η ΔΕΣΜΩΤΙΣ", "meleagros": "ΜΕΛΕΑΓΡΟΣ",
    "oidipots": "ΟΙΔΙΠΟΥΣ", "oinets": "ΟΙΝΕΥΣ", "oinomaos": "ΟΙΝΟΜΑΟΣ",
    "palamedes": "ΠΑΛΑΜΗΔΗΣ", "peirithoys": "ΠΕΙΡΙΘΟΥΣ", "peliades": "ΠΕΛΙΑΔΕΣ",
    "peleys": "ΠΗΛΕΥΣ", "pleisthenes": "ΠΛΕΙΣΘΕΝΗΣ", "polyidos": "ΠΟΛΥΙΔΟΣ",
    "protesilaos": "ΠΡΩΤΕΣΙΛΑΟΣ", "radamanoys": "ΡΑΔΑΜΑΝΘΥΣ",
    "stheneboia": "ΣΘΕΝΕΒΟΙΑ", "skiron_satyrikos": "ΣΚΙΡΩΝ ΣΑΤΥΡΙΚΟΣ",
    "skyrioi": "ΣΚΥΡΙΑΙ", "syleys_satyrikos": "ΣΥΛΕΥΣ ΣΑΤΥΡΙΚΟΣ",
    "tennes": "ΤΕΝΝΗΣ", "telephos": "ΤΗΛΕΦΟΣ", "temenidai": "ΤΗΜΕΝΙΔΑΙ",
    "ypsipyle": "ΥΨΙΠΥΛΗ", "phaethon": "ΦΑΕΘΩΝ", "philoktetes": "ΦΙΛΟΚΤΗΤΗΣ",
    "phoinix": "ΦΟΙΝΙΞ", "phrixos": "ΦΡΙΞΟΣ", "chrysippos": "ΧΡΥΣΙΠΠΟΣ",
    "incertarvm_fabvlarvm_fragmenta": "INCERTARUM FABULARUM FRAGMENTA",
    "epistolae": "ΕΠΙΣΤΟΛΑΙ", "epigramma_euripidi_adscriptum": "EPIGRAMMA EURIPIDI ADSCRIPTUM",
}

# Misidentified boundaries recoverable from printed local numbering and text.
GLOBAL_OVERRIDES = {
    "265": "ayge", "314": "bellerophontes", "383": "theseye",
    "462": "kresphontes", "475": "kretes", "476": "kretes",
    "481": "likymnios", "482": "likymnios", "618": "peleys",
    "638": "polyidos", "639": "polyidos", "640": "polyidos", "641": "polyidos",
    "651": "protesilaos", "652": "protesilaos",
}


def q(local: str) -> str:
    return f"{{{TEI}}}{local}"


def printed_number(fragment) -> str | None:
    note = fragment.find(q("note"))
    text = " ".join("".join(note.itertext()).split()) if note is not None else ""
    match = re.match(r"^(\d+)(?:\s*[,–-]\s*(\d+))?\s*[.]", text)
    if not match:
        return None
    return match.group(1) if not match.group(2) else f"{match.group(1)}-{match.group(2)}"


def number_start(value: str) -> int | None:
    match = re.match(r"^(\d+)", value or "")
    return int(match.group(1)) if match else None


def number_end(value: str) -> int | None:
    nums = re.findall(r"\d+", value or "")
    return int(nums[-1]) if nums else None


def normalize(source: Path):
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition.set("n", EDITION_URN)
    edition.set(f"{{{XML}}}base", EDITION_URN)
    edition.getparent().set(f"{{{XML}}}base", EDITION_URN)
    sections = edition.xpath("./tei:div[@subtype='section']", namespaces=NS)
    if len(sections) != len(SECTION_TARGETS):
        raise ValueError(f"Expected {len(SECTION_TARGETS)} page-level sections, found {len(sections)}")

    containers = {}
    fragments_by_work = defaultdict(list)
    seen_original = {}
    nonplays = {"incertarvm_fabvlarvm_fragmenta", "epistolae", "epigramma_euripidi_adscriptum"}

    for index, (section, default_work) in enumerate(zip(sections, SECTION_TARGETS)):
        for fragment in section.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            original = fragment.get("n") or ""
            work = GLOBAL_OVERRIDES.get(original, default_work)
            # Page 684 repeated the end of Alcmaeon fragment 4 at page 685.
            duplicate_key = (work, original)
            if duplicate_key in seen_original and original == "71":
                prior = seen_original[duplicate_key]
                for child in list(fragment):
                    fragment.remove(child)
                    prior.append(child)
                continue
            seen_original[duplicate_key] = fragment
            section.remove(fragment)
            fragment.set("data-extraction-n", original)
            fragment.set("n", printed_number(fragment) or "")
            fragments_by_work[work].append(fragment)
        edition.remove(section)

    for work, fragments in fragments_by_work.items():
        last = 0
        for fragment in fragments:
            label = fragment.get("n")
            if not label:
                original = fragment.get("data-extraction-n")
                if original == "nulla":
                    label = "testimonium"
                elif original == "incertum":
                    label = "incertum"
                elif work == "epistolae":
                    label = {"Β΄": "2", "Γ΄": "3", "Δ΄": "4", "5": "5"}.get(original, original)
                else:
                    label = str(last + 1)
                fragment.set("n", label)
            end = number_end(label)
            if end is not None:
                last = max(last, end)

        # The source pages can present continuations before the start of a
        # work; printed number, not extraction order, determines reading order.
        fragments.sort(key=lambda f: (
            number_start(f.get("n")) is None,
            number_start(f.get("n")) or 10**9,
            f.get("n"),
        ))
        container = etree.Element(q("div"))
        container.set("type", "textpart")
        container.set("subtype", "section" if work in nonplays else "play")
        container.set("n", work)
        container.set(XID, f"euripides-dindorf-{work.replace('_', '-')}")
        container.set("corresp", f"urn:cite2:perseus:fragmentaryplays.v1:tlg0006_{work}")
        etree.SubElement(container, q("head")).text = TITLES[work]
        used = set()
        for fragment in fragments:
            label = fragment.get("n")
            if label in used:
                suffix = 2
                while f"{label}-{suffix}" in used:
                    suffix += 1
                label = f"{label}-{suffix}"
                fragment.set("n", label)
            used.add(label)
            fragment.attrib.pop("data-extraction-n", None)
            safe = re.sub(r"[^0-9A-Za-z]+", "-", label).strip("-") or "unit"
            fragment.set(XID, f"euripides-dindorf-{work.replace('_', '-')}-{safe}")
            fragment.set("corresp", container.get("corresp"))
            for line_index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1):
                line.set("n", str(line_index))
                line.set(XID, f"{fragment.get(XID)}-l{line_index}")
                line.set(f"{{{XML}}}lang", "grc")
            container.append(fragment)
        containers[work] = container
        edition.append(container)

    refs = tree.xpath("//tei:encodingDesc/tei:refsDecl", namespaces=NS)[0]
    for child in list(refs):
        refs.remove(child)
    refs.text = None
    outer = etree.SubElement(refs, q("citeStructure"), match="/TEI/text/body", use="@xml:base")
    section = etree.SubElement(outer, q("citeStructure"), unit="work",
                               match="div/div[@subtype='play' or @subtype='section']", use="@n")
    fragment = etree.SubElement(section, q("citeStructure"), unit="fragment",
                                match="div[@subtype='fragment']", use="@n")
    etree.SubElement(fragment, q("citeStructure"), unit="line", match="lg/l", use="@n")
    revision = tree.xpath("//tei:revisionDesc", namespaces=NS)[0]
    change = etree.SubElement(revision, q("change"), when="2026-10-08")
    change.text = ("Normalized page-local headings to stable Euripidean work identities and "
                   "restored Dindorf's printed per-work fragment numbering; transcription unchanged.")
    return tree


def update_cts(path: Path):
    tree = etree.parse(str(path))
    root = tree.getroot()
    if not root.xpath(f"ti:edition[@urn='{EDITION_URN}']", namespaces=NS):
        edition = etree.SubElement(root, f"{{{CTS}}}edition", urn=EDITION_URN,
                                   workUrn="urn:cts:greekLit:tlg0006.fragmenta")
        edition.set(f"{{{XML}}}lang", "grc")
        etree.SubElement(edition, f"{{{CTS}}}label", {f"{{{XML}}}lang": "eng"}).text = (
            "Greek (Dindorf, 1893; OCR draft)")
        etree.SubElement(edition, f"{{{CTS}}}description", {f"{{{XML}}}lang": "eng"}).text = (
            "Euripidean fragments edited by Wilhelm Dindorf in Poetarum scenicorum "
            "Graecorum, pages 654–715. OCR-derived transcription requiring review.")
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    destination = args.data_dir / "tlg0006/fragments/source" / f"tlg0006.fragmenta.{VERSION}.xml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree = normalize(args.source)
    tree.write(str(destination), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    update_cts(args.data_dir / "tlg0006/fragments/__cts__.xml")
    print(destination)


if __name__ == "__main__":
    main()
