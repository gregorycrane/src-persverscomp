#!/usr/bin/env python3
"""Install the reviewed Dindorf Aeschylus fragment TEI and CTS metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI, "ti": CTS}
XID = f"{{{XML}}}id"
VERSION = "dindorf1893-grc1"
EDITION_URN = f"urn:cts:greekLit:tlg0085.fragmenta.{VERSION}"

# Explicit identities avoid making opaque or unstable work IDs from OCR text.
SECTION_WORKS = {
    "αθαμασ": "athamas", "αιτναι": "aitnaiai", "αμυμωνη": "amymone",
    "αργειοι": "argeioi", "βασσαριδεσ": "bassarai",
    "γλαυκοσ-ποντιοσ": "glaykos_pontios", "γλαυκοσ-ποτνιευσ": "glaykos_potnieys",
    "δαναιδεσ": "danaides", "δικτυουλκοι": "diktyoylkoi",
    "διονυσου-τροφοι": "dionysoy_trophoi", "ελευσινιοι": "eleysinioi",
    "επιγονοι": "epigonoi", "ευρωπη-η-καρεσ": "kares", "ηδωνοι": "edonoi",
    "ηλιαδεσ": "heliades", "ηρακλειδαι": "herakleidai",
    "θαλαμοποιοι": "thalamopoioi", "θεωροι-η-ισθμιασται": "theoroi",
    "θρηισσαι": "threissai", "ιερειαι": "iereiai", "ιξιων": "ixion",
    "ιφιγενεια": "iphigeneia", "καβειροι": "kabeiroi", "καλλιστω": "kallisto",
    "κερκυων": "kerkyon", "κηρυκεσ": "kerykes", "κιρκη": "kirke",
    "κρησσαι": "kressai", "λαιοσ": "laios", "λεων": "leon",
    "λυκουργοσ": "lykourgos", "μυρμιδονεσ": "myrmidones", "μυσοι": "mysoi",
    "νεανισκοι": "neaniskoi", "νηρηιδεσ": "nereides", "νιοβη": "niobe",
    "ξαντριαι": "xantriai", "οιδιπουσ": "oidipoys", "οπλων-κρισισ": "oplon_krisis",
    "οστολογοι": "ostologoi", "παλαμηδησ": "palamedes", "πενθευσ": "pentheys",
    "περραιβιδεσ": "perraibides", "πηνελοπη": "penelope",
    "προμηθευσ-πυρφοροσ": "prometheys_pyrphoros",
    "προμηθευσ-λυομενοσ": "prometheys_lyomenos", "προπομποι": "propompoi",
    "πρωτευσ": "proteys", "σαλαμινιαι": "salaminai", "σεμελη-η-υδροφοροι": "semele",
    "σισυφοσ": "sisyphos", "σισυφοσ-πετροκυλιστησ": "sisyphos",
    "σφιγξ": "sphigx", "τηλεφοσ": "telephos", "τοξοτιδεσ": "toxotides",
    "τροφοι": "trophoi", "φιλοκτητησ": "philoktetes", "φινευσ": "phineys",
    "φοινισσαι": "phoinissai", "φορκιδεσ": "phorkides", "φρυγεσ-η-εκτοροσ-λυτρα": "phryges",
    "ψυχαγωγοι": "psychagogoi", "ψυχοστασια": "psychostasia",
    "ωρειθυια": "oreithyia", "αδηλων-δραματων": "incertae",
    "ελεγεια": "elegeia", "epigramma-aeschylo-adscriptum": "epigramma_aeschylo_adscriptum",
}
RUNNING_HEADERS = {"αισχυλου", "αποσπασματια", "αποσπασματα"}
NON_PLAY_WORKS = {"incertae", "elegeia", "epigramma_aeschylo_adscriptum"}


def qname(local):
    return f"{{{TEI}}}{local}"


def normalize_fragment_number(value):
    value = (value or "").strip()
    if value == "335. 336":
        return "335-336"
    if value == "ANTHOLOG. PALAT. VII, 255":
        return "anthol-pal-7-255"
    return re.sub(r"\s+", "-", value)


def normalize(source: Path):
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition.set("n", EDITION_URN)
    edition.set(f"{{{XML}}}base", EDITION_URN)
    edition.getparent().set(f"{{{XML}}}base", EDITION_URN)
    sections = edition.xpath("./tei:div[@subtype='section']", namespaces=NS)
    targets = {}
    last_target = None

    for section in list(sections):
        source_key = section.get("n")
        if source_key in RUNNING_HEADERS:
            first = section.xpath("./tei:div[@subtype='fragment'][1]/@xml:id", namespaces=NS)
            # Page 597 opens the Theoroi material before the repeated title;
            # all other such nodes are running headers continuing the prior work.
            slug = "theoroi" if first == ["frag_80bb45c78f"] else last_target
        else:
            slug = SECTION_WORKS.get(source_key)
            if slug is None:
                raise ValueError(f"No work identity for Dindorf section {source_key!r}")
            last_target = slug

        target = targets.get(slug)
        if target is None:
            target = section
            targets[slug] = target
            target.set("n", slug)
            target.set("subtype", "section" if slug in NON_PLAY_WORKS else "play")
            target.set(XID, f"aeschylus-dindorf-{slug.replace('_', '-')}")
            target.set("corresp", f"urn:cite2:perseus:fragmentaryplays.v1:{slug}")
            if source_key in RUNNING_HEADERS:
                head = target.find(qname("head"))
                if head is not None:
                    target.remove(head)
        elif target is not section:
            for child in list(section):
                if child.tag != qname("head"):
                    section.remove(child)
                    target.append(child)
            edition.remove(section)

    # Consolidate same-number continuations and give every line a stable ID.
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
                line.set("n", line.get("n") or str(index))
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
    urn = EDITION_URN
    existing = root.xpath(f"ti:edition[@urn='{urn}']", namespaces=NS)
    if not existing:
        edition = etree.SubElement(root, f"{{{CTS}}}edition", urn=urn,
                                   workUrn="urn:cts:greekLit:tlg0085.fragmenta")
        edition.set(f"{{{XML}}}lang", "grc")
        etree.SubElement(edition, f"{{{CTS}}}label", {f"{{{XML}}}lang": "eng"}).text = (
            "Greek (Dindorf, 1893; OCR draft)")
        etree.SubElement(edition, f"{{{CTS}}}description", {f"{{{XML}}}lang": "eng"}).text = (
            "Aeschylus, fragments edited by Wilhelm Dindorf in Poetarum scenicorum "
            "Graecorum (London, 1893), pages 593–615. OCR-derived transcription requiring review.")
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def add_nauck_alignments(dindorf_path: Path, nauck_path: Path):
    """Persist accepted text matches in the canonical Dindorf TEI."""
    from pipeline.aeschylus_fragment_concordance import build_dindorf, merge_work_views
    from pipeline.fragment_collections import build as build_nauck

    _, concordance = merge_work_views(
        build_dindorf(dindorf_path), build_nauck(nauck_path))
    matches = {item["dindorf"]: item["nauck"] for item in concordance}
    tree = etree.parse(str(dindorf_path))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    for container in edition.xpath(
        "./tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        work = container.get("n")
        for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            source_urn = f"{EDITION_URN}:{work}.{fragment.get('n')}"
            if source_urn in matches:
                fragment.set("sameAs", matches[source_urn])
            else:
                fragment.attrib.pop("sameAs", None)
    revision = tree.xpath("//tei:revisionDesc", namespaces=NS)[0]
    change = etree.SubElement(revision, qname("change"), when="2026-10-08")
    change.text = (
        f"Recorded {len(matches)} conservative Dindorf–Nauck fragment correspondences "
        "from normalized quoted-Greek similarity; unmatched fragments remain unlinked.")
    tree.write(str(dindorf_path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    return len(matches)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    destination = (args.data_dir / "tlg0085/fragments/source" /
                   f"tlg0085.fragmenta.{VERSION}.xml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree = normalize(args.source)
    tree.write(str(destination), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    nauck = destination.with_name("tlg0085.fragmenta.nauck1889grc1.xml")
    if nauck.exists():
        print(f"alignments={add_nauck_alignments(destination, nauck)}")
    update_cts(args.data_dir / "tlg0085/fragments/__cts__.xml")
    print(destination)


if __name__ == "__main__":
    main()
