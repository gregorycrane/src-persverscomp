#!/usr/bin/env python3
"""Install and normalize Dindorf's Sophoclean fragment TEI.

The source notebook deliberately transcribes page-local headings.  This tool
turns those headings into stable Sophoclean work identities, folds running
headers into the preceding work, and adds CTS metadata.  It does not rewrite
the fragment text.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI, "ti": CTS}
XID = f"{{{XML}}}id"
VERSION = "dindorf1893-grc1"
EDITION_URN = f"urn:cts:greekLit:tlg0011.fragmenta.{VERSION}"

# Printed headings are retained in <head>; these values are stable route IDs.
SECTION_WORKS = {
    "αθαμασ-α-β": "athamas_a_kai_b",
    "αιασ-λοκροσ": "aias_lokros",
    "αιγευσ": "aigeys",
    "αιθιοπεσ": "aithiopes",
    "αιχμαλωτιδεσ": "aichmalotides",
    "ακρισιοσ-η-λαρισσαιοι": "akrisios",
    "αλεξανδροσ": "alexandros",
    "αλητησ": "aletes",
    "αλκμαιων": "alkmeon",
    "αλεαδαι": "aleadai",
    "αμφιαρεωσ": "amphiareos_satyrikos",
    "αμυκοσ": "amykos_satyrikos",
    "αμφιτρυων": "amphitryon",
    "ανδρομαχη": "andromache",
    "ανδρομεδα": "andromeda",
    "αντηνοριδαι": "antenoridai",
    "ατρευσ-η-μυκηναιαι": "atreys_e_mykenaiai",
    "αχαιων-συλλογοσ-η-συνδειπνον-η-συνδειπνοι": "achaion_syllogos_e_syndeipnoi",
    "αχαιων-συλλογοσ": "achaion_syllogos",
    "αχιλλεωσ-ερασται": "achilleos_erastai",
    "δαιδαλοσ": "daidalos",
    "δαναη": "danae",
    "διονυσιακοσ": "dionysiskos_satyrikos",
    "δολοπεσ": "dolopes",
    "ελενη-ελενησ-αρπαγη-ελενησ-απαιτησισ-ελενησ-γαμοσ": "elenes_apaitesis",
    "αποσπασμα-αδεσποτον": "elenes_gamos_satyrikos",
    "επιγονοι": "epigonoi",
    "ερισ": "eris",
    "εριφυλη": "eriphyle",
    "ερμιονη": "ermione",
    "ευμηλοσ": "eymelos",
    "ευρυαλοσ": "eyryalos",
    "σωστηρεσ": "soteres",
    "ηρακλησ-επι-ταιναρωι": "erakles_epi_tainaroi_satyroi_erakleiskos",
    "ηριγονη": "erigone",
    "θαμυρασ": "thamyras",
    "θησευσ": "theseys",
    "θυεστησ-εν-σικυωνι-η-σικυωνιοσ": "thyestes_en_sikyoni",
    "ιναχοσ": "inachos",
    "ιξιων": "ixion",
    "ιοβατησ": "iobates",
    "ιολαοσ": "iolaos",
    "ιππονοοσ": "ipponoys",
    "ιφιγενεια": "iphigeneia",
    "ιχνευται": "ichneytai_satyroi",
    "ιων": "ion",
    "καμικιοι-η-μινωσ": "kamikoi",
    "κηδαλιων": "kedalion",
    "κλυταιμνηστρα": "klytaimestra",
    "κολχιδεσ": "kolchides",
    "κολχοι": "kolchides",
    "κρεουσα": "kreoysa",
    "κρισισ": "krisis",
    "κωφοι": "kophoi",
    "κωφοι-σατυροι": "kophoi",
    "λακαιναι": "lakainai",
    "λαοκοων": "laokoon",
    "λημνιαι": "lemniai",
    "μελεαγροσ": "meleagros",
    "μυσοι": "mysoi",
    "μωμοσ": "momos",
    "ναυπλιοσ-καταπλεων": "nayplios_katapleon",
    "ναυπλιοσ": "nayplios_pyrkaeys",
    "ναυσικαα-η-πλυντριαι": "naysikaa",
    "νιοβη": "niobe",
    "νιπτρα-η-οδυσσευσ-ακανθοπληξ": "odysseys_akanthoplex",
    "ξοανηφοροι": "xoanephoroi",
    "οδυσσευσ-μαινομενοσ": "odysseys_mainomenos",
    "οινευσ": "oineys",
    "οινομαοσ-η-ιπποδαμεια": "oinomaos",
    "οινομαοσ": "oinomaos",
    "παλαμηδησ": "palamedes",
    "πανδωρα-η-σφυροκοποι": "pandora",
    "πελιασ": "pelias",
    "πηλευσ": "peleys",
    "ποιμενεσ": "poimenes",
    "πολυιδοσ-η-μαντεισ": "manteis",
    "πολυξενη": "polyxene",
    "πριαμοσ": "priamos",
    "προκρισ": "prokris",
    "ριζοτομοι": "rizotomoi",
    "σαλμωνευσ": "salmoneys",
    "σινων": "sinon",
    "σισυφοσ": "sisyphos",
    "σκυθαι": "skythai",
    "σκυριαι": "skyrioi",
    "τευκροσ": "teykros",
    "τηλεφοσ": "telephos",
    "τηρευσ": "tereys",
    "τριπτολεμοσ": "triptolemos",
    "τρωιλοσ": "troilos",
    "τυμπανισται": "tympanistai",
    "τυνδαρεωσ": "tyndareos",
    "τυρω-α-β": "tyro",
    "τυροι": "tyro",
    "υβρισ": "ybris",
    "υδροφοροι": "ydrophoroi",
    "φαιακεσ": "phaiakes",
    "φαιδρα": "phaidra",
    "φθιωτιδεσ": "phthiotides",
    "φιλοκτητησ-εν-τροιαι": "philoktetes",
    "φινευσ-α-β": "phineys",
    "φοινιξ": "phoinix",
    "φριξοσ": "phrixos",
    "φρυγεσ": "phryges",
    "χρυσησ": "chryses",
    "ωρειθυια": "oreithyia",
    "αδηλων-δραματων": "uncertain_play_fragments",
}
RUNNING_HEADERS = {"αποσπασματα", "σοφοκλεουσ"}
NON_PLAY_WORKS = {"uncertain_play_fragments"}

# Page-local extraction put Dindorf 114 beneath a repeated Amphiareos heading,
# although its source citation explicitly says Amykos.  This is attribution
# repair, not textual emendation.
FRAGMENT_WORK_OVERRIDES = {
    ("αμφιαρεωσ", "114"): "amykos_satyrikos",
}


def qname(local):
    return f"{{{TEI}}}{local}"


def normalize_fragment_number(value):
    value = re.sub(r"\s+", "", (value or "").strip())
    return re.sub(r"[,.;]+", "-", value).strip("-")


def normalize(source: Path):
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition.set("n", EDITION_URN)
    edition.set(f"{{{XML}}}base", EDITION_URN)
    edition.getparent().set(f"{{{XML}}}base", EDITION_URN)
    sections = edition.xpath("./tei:div[@subtype='section']", namespaces=NS)
    targets = {}
    last_target = None

    def target_for(slug, source_section):
        target = targets.get(slug)
        if target is None:
            target = etree.Element(qname("div"))
            target.set("type", "textpart")
            target.set("subtype", "section" if slug in NON_PLAY_WORKS else "play")
            target.set("n", slug)
            target.set(XID, f"sophocles-dindorf-{slug.replace('_', '-')}")
            target.set("corresp", f"urn:cite2:perseus:fragmentaryplays.v1:sophocles-{slug}")
            head = source_section.find(qname("head"))
            if head is not None:
                target.append(etree.fromstring(etree.tostring(head)))
            targets[slug] = target
            edition.append(target)
        return target

    for section in list(sections):
        source_key = section.get("n")
        if source_key in RUNNING_HEADERS:
            if last_target is None:
                raise ValueError(f"Running header precedes a real work: {source_key}")
            default_slug = last_target
        else:
            default_slug = SECTION_WORKS.get(source_key)
            if default_slug is None:
                raise ValueError(f"No work identity for Dindorf section {source_key!r}")
            last_target = default_slug
        for child in list(section):
            if child.tag == qname("head"):
                continue
            slug = default_slug
            if child.tag == qname("div") and child.get("subtype") == "fragment":
                slug = FRAGMENT_WORK_OVERRIDES.get(
                    (source_key, normalize_fragment_number(child.get("n"))), slug)
            section.remove(child)
            target_for(slug, section).append(child)
        edition.remove(section)

    # Consolidate same-number page continuations and stabilize citations.
    for slug, container in targets.items():
        seen = {}
        for fragment in list(container.xpath("./tei:div[@subtype='fragment']", namespaces=NS)):
            number = normalize_fragment_number(fragment.get("n"))
            fragment.set("n", number)
            fragment.set("corresp", container.get("corresp"))
            if number in seen:
                prior = seen[number]
                for child in list(fragment):
                    fragment.remove(child)
                    prior.append(child)
                container.remove(fragment)
                fragment = prior
            else:
                seen[number] = fragment
            fragment_id = fragment.get(XID)
            for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1):
                line.set("n", str(index))
                line.set(XID, f"{fragment_id}-l{index}")
                line.set(f"{{{XML}}}lang", "grc")

    refs = tree.xpath("//tei:encodingDesc/tei:refsDecl", namespaces=NS)[0]
    for child in list(refs):
        refs.remove(child)
    refs.text = None
    outer = etree.SubElement(refs, qname("citeStructure"),
                             match="/TEI/text/body", use="@xml:base")
    section_cite = etree.SubElement(
        outer, qname("citeStructure"), unit="section",
        match="div/div[@subtype='play' or @subtype='section']", use="@n")
    fragment_cite = etree.SubElement(
        section_cite, qname("citeStructure"), unit="fragment",
        match="div[@subtype='fragment']", use="@n")
    etree.SubElement(fragment_cite, qname("citeStructure"), unit="line",
                     match="lg/l", use="@n")
    return tree


def update_cts(path: Path):
    tree = etree.parse(str(path))
    root = tree.getroot()
    existing = root.xpath(f"ti:edition[@urn='{EDITION_URN}']", namespaces=NS)
    if not existing:
        edition = etree.SubElement(root, f"{{{CTS}}}edition", urn=EDITION_URN,
                                   workUrn="urn:cts:greekLit:tlg0011.fragmenta")
        edition.set(f"{{{XML}}}lang", "grc")
        etree.SubElement(edition, f"{{{CTS}}}label", {f"{{{XML}}}lang": "eng"}).text = (
            "Greek (Dindorf; OCR draft)")
        etree.SubElement(edition, f"{{{CTS}}}description", {f"{{{XML}}}lang": "eng"}).text = (
            "Sophocles, fragments edited by Wilhelm Dindorf in Poetarum scenicorum "
            "Graecorum, pages 616–653. OCR-derived transcription requiring review.")
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    destination = (args.data_dir / "tlg0011/fragments/source" /
                   f"tlg0011.fragmenta.{VERSION}.xml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree = normalize(args.source)
    tree.write(str(destination), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    update_cts(args.data_dir / "tlg0011/fragments/__cts__.xml")
    print(destination)


if __name__ == "__main__":
    main()
