"""Build the TEI-first Nauck tragic-fragment corpus.

The diplomatic source is ``nauck.tragfrag-2.xml``.  It contains a malformed
TEI namespace declaration, which is repaired while importing.  The complete
source remains the canonical transcription; author files are deterministic
TEI derivatives used for CTS discovery and publication.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


TEI = "http://www.tei-c.org/ns/1.0"
CTS = "http://chs.harvard.edu/xmlns/cts"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI}
VERSION = "nauck1889grc1"
CORPUS_ID = "nauck1889"
SOURCE_NAME = "nauck.tragfrag-2.xml"
XML_ID = f"{{{XML}}}id"
FRAGMENT_NUMBER = re.compile(r"^\d+(?:[a-z])?$", re.IGNORECASE)
GREEK_TRANSLITERATION = str.maketrans({
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "φ": "ph", "χ": "ch", "ψ": "ps", "ω": "o",
})


@dataclass(frozen=True)
class AuthorSpec:
    textgroup: str
    name: str
    chapters: tuple[int, ...]
    split_marker: str | None = None
    before_marker: bool = False


AUTHORS = (
    AuthorSpec("tlg0011", "Sophocles", (4, 5, 6)),
    AuthorSpec("tlg0006", "Euripides", (7, 8, 9)),
    AuthorSpec("tlg0302", "Choerilus", (10,)),
    AuthorSpec("tlg0303", "Phrynichus", (11,)),
    AuthorSpec("tlg1833", "Pratinas", (12,)),
    AuthorSpec("tlg0305", "Aristias", (13,)),
    AuthorSpec("tlg0306", "Aristarchus", (14,)),
    AuthorSpec("tlg0307", "Neophron", (15,)),
    AuthorSpec("tlg0308", "Ion of Chios", (16,)),
    AuthorSpec("tlg0309", "Achaeus", (17,)),
    AuthorSpec("tlg0312", "Philocles", (18,), "MELANTHIVS", True),
    AuthorSpec("tlg0344", "Melanthius", (18,), "MELANTHIVS", False),
    AuthorSpec("tlg0311", "Iophon", (19,)),
    AuthorSpec("tlg0482", "Nicomachus", (20,)),
    AuthorSpec("tlg0315", "Sthenelus", (21,)),
    AuthorSpec("tlg0318", "Agathon", (22,)),
    AuthorSpec("tlg0313", "Theognis", (23,)),
    AuthorSpec("tlg0316", "Xenocles", (24,)),
    AuthorSpec("tlg0319", "Critias", (25,)),
    AuthorSpec("tlg0322", "Dicaeogenes", (26,)),
    AuthorSpec("tlg0320", "Diogenes of Athens", (27,)),
    AuthorSpec("tlg0325", "Astydamas", (28,)),
    AuthorSpec("tlg0326", "Sophocles the Younger", (29,)),
    AuthorSpec("tlg0331", "Polyidus", (30,)),
    AuthorSpec("tlg1848", "Meletus", (31,)),
    AuthorSpec("tlg0328", "Chaeremon", (32,)),
    AuthorSpec("tlg0323", "Antiphon", (33,)),
    AuthorSpec("tlg0330", "Dionysius", (34,)),
    AuthorSpec("tlg0327", "Carcinus", (35,)),
    AuthorSpec("tlg0329", "Theodectes", (36,)),
    AuthorSpec("tlg0332", "Cleaenetus", (37,)),
    AuthorSpec("tlg0334", "Diogenes of Sinope", (38,)),
    AuthorSpec("tlg0336", "Crates", (39,)),
    AuthorSpec("tlg0337", "Python", (40,)),
    AuthorSpec("tlg0339", "Moschion", (41,)),
    AuthorSpec("tlg0216", "Alexander Aetolus", (42,)),
    AuthorSpec("tlg0341", "Lycophron", (43,)),
    AuthorSpec("tlg0335", "Philiscus", (44,)),
    AuthorSpec("tlg0338", "Sosiphanes", (45,)),
    AuthorSpec("tlg0340", "Sositheus", (46,)),
    AuthorSpec("tlg0604", "Ptolemy Philopator", (47,)),
    AuthorSpec("tlg0321", "Aeschylus of Alexandria", (48,)),
    AuthorSpec("tlg0345", "Apollonides", (49,)),
    AuthorSpec("tlg0348", "Biotus", (50,)),
    AuthorSpec("tlg1256", "Chares", (51,)),
    AuthorSpec("tlg0349", "Demonax", (52,)),
    AuthorSpec("tlg0351", "Hippothoon", (53,)),
    AuthorSpec("tlg0352", "Isidorus", (54,)),
    AuthorSpec("tlg1511", "Mimnermus", (55,)),
    AuthorSpec("tlg0324", "Patrocles of Thurii", (56,)),
    AuthorSpec("tlg0346", "Pompeius Macer", (57,)),
    AuthorSpec("tlg0347", "Serapion", (58,), "ZENODOTVS", True),
    AuthorSpec("tlg0354", "Zenodotus", (58,), "ZENODOTVS", False),
    AuthorSpec("tlg0355", "Zopyrus", (59,)),
    AuthorSpec("tlg0301", "Thespis", (60,)),
    AuthorSpec("tragfragadesp", "Adespota", (62,)),
)

# Catalog evidence copied from lsj_author_source_coverage.numbers (CSV export).
# The first value is the Perseus author authority URN; the second is the LSJ
# coverage row. Local tragfrag identifiers have no safe catalog match there.
AUTHORITY_EVIDENCE = {
    "tlg0309": ("urn:cite:perseus:author.9.1", "4"),
    "tlg0321": ("urn:cite:perseus:author.33.1", "20"),
    "tlg0323": ("urn:cite:perseus:author.124.1", "109"),
    "tlg0345": ("urn:cite:perseus:author.149.1", "129"),
    "tlg0306": ("urn:cite:perseus:author.187.1", "173"),
    "tlg0305": ("urn:cite:perseus:author.190.1", "176"),
    "tlg0325": ("urn:cite:perseus:author.223.1", "217"),
    "tlg0348": ("urn:cite:perseus:author.278.1", "248"),
    "tlg0327": ("urn:cite:perseus:author.324.1", "270"),
    "tlg0328": ("urn:cite:perseus:author.347.1", "290"),
    "tlg1256": ("urn:cite:perseus:author.350.1", "296"),
    "tlg0302": ("urn:cite:perseus:author.360.1", "307"),
    "tlg0332": ("urn:cite:perseus:author.376.1", "316"),
    "tlg0319": ("urn:cite:perseus:author.424.1", "358"),
    "tlg0322": ("urn:cite:perseus:author.473.1", "411"),
    "tlg0320": ("urn:cite:perseus:author.491.1", "432"),
    "tlg0334": ("urn:cite:perseus:author.495.1", "437"),
    "tlg0330": ("urn:cite:perseus:author.503.1", "444"),
    "tlg0351": ("urn:cite:perseus:author.742.1", "648"),
    "tlg0308": ("urn:cite:perseus:author.765.1", "668"),
    "tlg0311": ("urn:cite:perseus:author.766.1", "669"),
    "tlg0352": ("urn:cite:perseus:author.774.1", "672"),
    "tlg0341": ("urn:cite:perseus:author.857.1", "721"),
    "tlg0344": ("urn:cite:perseus:author.912.1", "771"),
    "tlg1511": ("urn:cite:perseus:author.937.1", "802"),
    "tlg0339": ("urn:cite:perseus:author.947.1", "815"),
    "tlg0307": ("urn:cite:perseus:author.967.1", "835"),
    "tlg0482": ("urn:cite:perseus:author.985.1", "852"),
    "tlg0324": ("urn:cite:perseus:author.1047.1", "902"),
    "tlg0335": ("urn:cite:perseus:author.1088.1", "942"),
    "tlg0312": ("urn:cite:perseus:author.1099.1", "952"),
    "tlg0303": ("urn:cite:perseus:author.1122.1", "978"),
    "tlg0346": ("urn:cite:perseus:author.1161.1", "1012"),
    "tlg1833": ("urn:cite:perseus:author.1175.1", "1018"),
    "tlg0329": ("urn:cite:perseus:author.1379.1", "1169"),
    "tlg0313": ("urn:cite:perseus:author.1387.1", "1176"),
    "tlg0301": ("urn:cite:perseus:author.1398.1", "1191"),
    "tlg0316": ("urn:cite:perseus:author.1492.1", "1237"),
    "tlg0216": ("urn:cite:perseus:author.59.1", "44"),
}

# TLG textgroups verified directly in canon-keys.txt. Each matching catalog
# block identifies the named author and a tragic work from TrGF volume 1.
CANON_KEY_EVIDENCE = {
    "tlg0315": "0315",  # Sthenelus
    "tlg0318": "0318",  # Agathon
    "tlg0326": "0326",  # Sophocles Junior
    "tlg0331": "0331",  # Polyidus
    "tlg0336": "0336",  # Crates of Thebes
    "tlg0337": "0337",  # Python
    "tlg0338": "0338",  # Sosiphanes
    "tlg0340": "0340",  # Sositheus
    "tlg0347": "0347",  # Serapion
    "tlg0349": "0349",  # Demonax
    "tlg0354": "0354",  # Zenodotus
    "tlg0355": "0355",  # Zopyrus
    "tlg0604": "0604",  # Ptolemy IV Philopator
    "tlg1848": "1848",  # Meletus Junior
}


def qname(local: str) -> str:
    return f"{{{TEI}}}{local}"


def ctsname(local: str) -> str:
    return f"{{{CTS}}}{local}"


def text(element: etree._Element) -> str:
    return " ".join("".join(element.itertext()).split())


def load_source(path: Path) -> etree._ElementTree:
    raw = path.read_bytes()
    bad = b"http ://www.tei-c.org/ns/1 .0"
    if bad not in raw:
        raise ValueError(f"Expected malformed namespace was not found in {path}")
    raw = raw.replace(bad, TEI.encode())
    raw = raw.replace(b"http ://www.stoa.org/", b"http://www.stoa.org/")
    parser = etree.XMLParser(remove_blank_text=True, huge_tree=True)
    return etree.ElementTree(etree.fromstring(raw, parser))


def source_chapters(tree: etree._ElementTree) -> dict[int, etree._Element]:
    nodes = tree.xpath("//tei:div[@type='edition']/tei:div[@type='textpart']", namespaces=NS)
    return {int(node.get("n")): node for node in nodes}


def source_nodes(spec: AuthorSpec, chapters: dict[int, etree._Element]) -> list[etree._Element]:
    nodes = [copy.deepcopy(node) for chapter in spec.chapters for node in chapters[chapter]]
    if spec.split_marker:
        marker = next(i for i, node in enumerate(nodes) if text(node) == spec.split_marker)
        nodes = nodes[:marker] if spec.before_marker else nodes[marker + 1 :]
    return nodes


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower().translate(GREEK_TRANSLITERATION)
    value = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-").lower()
    return value[:64] or "untitled"


def work_id(value: str) -> str:
    """Return a readable, CTS-safe identifier derived from a printed title."""
    return slug(value).replace("-", "_")


def is_title(node: etree._Element) -> bool:
    value = text(node)
    if not value or len(value) > 120 or value[-1:] in ".;:,?!":
        return False
    if etree.QName(node).localname == "head":
        return True
    letters = [char for char in value if char.isalpha()]
    return bool(letters) and all(char == char.upper() for char in letters)


def author_source_labels(spec: AuthorSpec) -> set[str]:
    labels = {spec.name.upper()}
    labels.update({
        "Sophocles": "SOPHOCLES",
        "Euripides": "EVRIPIDES",
        "Neophron": "NEOPHRON",
        "Meletus": "MELETVS",
        "Chaeremon": "CHAEREMON",
        "Carcinus": "CARCINVS",
        "Hippothoon": "HIPPOTHOON",
        "Sositheus": "SOSITHEVS",
    }.get(spec.name, "") for _ in (0,))
    labels.discard("")
    return labels


def make_header(spec: AuthorSpec, source_path: Path) -> etree._Element:
    header = etree.Element(qname("teiHeader"))
    file_desc = etree.SubElement(header, qname("fileDesc"))
    title_stmt = etree.SubElement(file_desc, qname("titleStmt"))
    etree.SubElement(title_stmt, qname("title")).text = f"Fragments of {spec.name}"
    etree.SubElement(title_stmt, qname("author"), ref=f"urn:cts:greekLit:{spec.textgroup}").text = spec.name
    etree.SubElement(title_stmt, qname("editor")).text = "August Nauck"
    publication = etree.SubElement(file_desc, qname("publicationStmt"))
    etree.SubElement(publication, qname("publisher")).text = "Perseus Digital Library"
    etree.SubElement(publication, qname("availability")).append(etree.Element(qname("p")))
    publication[-1][0].text = "Derived scholarly transcription; verify against page images before quotation."
    source_desc = etree.SubElement(file_desc, qname("sourceDesc"))
    bibl = etree.SubElement(source_desc, qname("bibl"))
    bibl.text = "August Nauck, Tragicorum Graecorum Fragmenta, second edition (Leipzig: Teubner, 1889)."
    etree.SubElement(source_desc, qname("ptr"), target=f"../../../nauck1889/source/{source_path.name}")
    encoding = etree.SubElement(header, qname("encodingDesc"))
    refs = etree.SubElement(encoding, qname("refsDecl"), n="CTS")
    etree.SubElement(
        refs,
        qname("citeStructure"),
        unit="fragment",
        match="//tei:div[@subtype='fragment']",
        use="@n",
    )
    revision = etree.SubElement(header, qname("revisionDesc"))
    etree.SubElement(revision, qname("change"), when="2026-10-07").text = (
        f"Extracted deterministically from {SOURCE_NAME}; repaired the malformed TEI namespace URI."
    )
    return header


def normalize_author(spec: AuthorSpec, nodes: list[etree._Element], source_path: Path) -> etree._ElementTree:
    root = etree.Element(qname("TEI"), nsmap={None: TEI})
    root.set(XML_ID, f"{spec.textgroup}-nauck1889")
    root.append(make_header(spec, source_path))
    text_el = etree.SubElement(root, qname("text"))
    body = etree.SubElement(text_el, qname("body"))
    edition_urn = f"urn:cts:greekLit:{spec.textgroup}.fragmenta.{VERSION}"
    edition = etree.SubElement(body, qname("div"), type="edition", n=edition_urn)
    labels = author_source_labels(spec)
    current_container = edition
    current_fragment = None
    used_work_ids: set[str] = set()
    fragment_ids: set[str] = set()
    last_fragment_number = ""
    skip_first_author_title = not (
        spec.name == "Choerilus" or (spec.split_marker and not spec.before_marker)
    )
    first_title_seen = False

    for node in nodes:
        value = text(node)
        local = etree.QName(node).localname
        if value in labels:
            first_title_seen = True
            continue
        if local == "head" and value == "TRAGICI MINORES":
            continue
        if local == "p" and FRAGMENT_NUMBER.fullmatch(value):
            # In the flat source, a printed line-number milestone can look
            # exactly like a fragment-number paragraph. A small number inside
            # a fragment whose Nauck number is already in the hundreds is a
            # continuation milestone, not a new fragment.
            previous_number = current_fragment.get("n") if current_fragment is not None else last_fragment_number
            if (
                current_fragment is not None
                and value.isdigit()
                and previous_number.isdigit()
                and int(value) < 100 <= int(previous_number)
            ):
                etree.SubElement(current_fragment, qname("milestone"), unit="sourceLine", n=value)
                continue
            source_number = value
            if spec.textgroup == "tlg0011" and value == "2058":
                value = "205"
            elif spec.textgroup == "tlg0328" and previous_number == "14" and value == "5":
                value = "15"
            frag_id = f"{spec.textgroup}-fr{value.lower()}"
            suffix = 2
            while frag_id in fragment_ids:
                frag_id = f"{spec.textgroup}-fr{value.lower()}-{suffix}"
                suffix += 1
            fragment_ids.add(frag_id)
            current_fragment = etree.SubElement(
                current_container,
                qname("div"),
                type="textpart",
                subtype="fragment",
                n=value,
                corresp=current_container.get("corresp", f"urn:cite2:perseus:fragmentaryplays.v1:{spec.textgroup}-incertae"),
            )
            current_fragment.set(XML_ID, frag_id)
            last_fragment_number = value
            etree.SubElement(current_fragment, qname("head")).text = value
            if source_number != value:
                etree.SubElement(current_fragment, qname("note"), type="sourceNumber").text = (
                    f"Source transcription reads {source_number}; normalized from the surrounding sequence."
                )
            continue
        if is_title(node):
            if not first_title_seen:
                first_title_seen = True
                if skip_first_author_title:
                    continue
            current_fragment = None
            source_title = value
            kind = "section" if any(word in source_title for word in ("INCERT", "DVBIA", "SPVRIA")) else "play"
            title_work_id = work_id(source_title)
            base_work_id = title_work_id
            duplicate = 2
            while title_work_id in used_work_ids:
                title_work_id = f"{base_work_id}_{duplicate}"
                duplicate += 1
            used_work_ids.add(title_work_id)
            play_id = f"{spec.textgroup}-{title_work_id.replace('_', '-')}"
            current_container = etree.SubElement(
                edition,
                qname("div"),
                type="textpart",
                subtype=kind,
                n=title_work_id,
                corresp=(
                    "urn:cite2:perseus:fragmentaryplays.v1:"
                    f"{spec.textgroup}_{title_work_id}"
                ),
            )
            current_container.set(XML_ID, play_id)
            heading = etree.SubElement(current_container, qname("head"))
            heading.text = source_title
            continue
        destination = current_fragment if current_fragment is not None else current_container
        destination.append(node)

    # The flat OCR source sometimes places a short authorial quotation in the
    # first paragraph after the fragment number instead of in <lg>/<l>. That
    # loses both lineation and the text needed for cross-edition concordance.
    # Promote only self-contained Greek paragraphs: source notices normally
    # contain Latin letters and/or a bibliographic colon, while these quoted
    # lemmata and verses do not.
    for fragment in edition.xpath(".//tei:div[@subtype='fragment'][not(.//tei:l)]", namespaces=NS):
        paragraphs = fragment.xpath("./tei:p[1]", namespaces=NS)
        if not paragraphs:
            continue
        paragraph = paragraphs[0]
        value = text(paragraph)
        greek = len(re.findall(r"[\u0370-\u03ff\u1f00-\u1fff]", value))
        latin = len(re.findall(r"[A-Za-z]", value))
        if greek < 5 or greek / max(1, greek + latin) < 0.7 or ":" in value:
            continue
        group = etree.Element(qname("lg"), type="fragment")
        line = etree.SubElement(group, qname("l"), n="1")
        line.text = paragraph.text
        for child in list(paragraph):
            paragraph.remove(child)
            line.append(child)
        group.tail = paragraph.tail
        paragraph.tail = None
        fragment.replace(paragraph, group)

    line_number = 0
    for fragment in edition.xpath(".//tei:div[@subtype='fragment']", namespaces=NS):
        line_number = 0
        for line in fragment.xpath(".//tei:l", namespaces=NS):
            line_number += 1
            line.set("n", line.get("n") or str(line_number))
            line.set(XML_ID, f"{fragment.get(XML_ID)}-l{line_number}")
            line.set(f"{{{XML}}}lang", line.get(f"{{{XML}}}lang") or "grc")
    return etree.ElementTree(root)


def write_xml(tree: etree._ElementTree, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def textgroup_cts(spec: AuthorSpec) -> etree._ElementTree:
    root = etree.Element(
        ctsname("textgroup"),
        nsmap={"ti": CTS},
        urn=f"urn:cts:greekLit:{spec.textgroup}",
        projid=f"greekLit:{spec.textgroup}",
    )
    etree.SubElement(root, ctsname("groupname"), {f"{{{XML}}}lang": "eng"}).text = spec.name
    return etree.ElementTree(root)


def work_cts(spec: AuthorSpec) -> etree._ElementTree:
    work_urn = f"urn:cts:greekLit:{spec.textgroup}.fragmenta"
    root = etree.Element(
        ctsname("work"),
        nsmap={"ti": CTS},
        urn=work_urn,
        groupUrn=f"urn:cts:greekLit:{spec.textgroup}",
    )
    root.set(f"{{{XML}}}lang", "grc")
    etree.SubElement(root, ctsname("title"), {f"{{{XML}}}lang": "eng"}).text = "Fragments"
    version = etree.SubElement(
        root,
        ctsname("edition"),
        urn=f"{work_urn}.{VERSION}",
        workUrn=work_urn,
    )
    version.set(f"{{{XML}}}lang", "grc")
    etree.SubElement(version, ctsname("label"), {f"{{{XML}}}lang": "eng"}).text = "Greek (Nauck, 1889; transcription preview) (OCR draft)"
    etree.SubElement(version, ctsname("description"), {f"{{{XML}}}lang": "eng"}).text = (
        f"Fragments attributed to {spec.name} in Nauck's Tragicorum Graecorum Fragmenta."
    )
    return etree.ElementTree(root)


def write_authority(specs: tuple[AuthorSpec, ...], path: Path) -> None:
    root = etree.Element(qname("TEI"), nsmap={None: TEI})
    header = etree.SubElement(root, qname("teiHeader"))
    fd = etree.SubElement(header, qname("fileDesc"))
    ts = etree.SubElement(fd, qname("titleStmt"))
    etree.SubElement(ts, qname("title")).text = "Nauck tragic-fragment author authority list"
    ps = etree.SubElement(fd, qname("publicationStmt"))
    etree.SubElement(ps, qname("p")).text = "Perseus Digital Library"
    sd = etree.SubElement(fd, qname("sourceDesc"))
    etree.SubElement(sd, qname("p")).text = f"Derived from {SOURCE_NAME}."
    etree.SubElement(sd, qname("p")).text = (
        "CTS textgroups reconciled against lsj_author_source_coverage.numbers; "
        "the corresponding LSJ coverage row is recorded on each matched person."
    )
    etree.SubElement(sd, qname("p")).text = (
        "Additional tragic authors were reconciled against canon-keys.txt; "
        "their TLG canon keys are recorded on each matched person."
    )
    text_node = etree.SubElement(root, qname("text"))
    body = etree.SubElement(text_node, qname("body"))
    people = etree.SubElement(body, qname("listPerson"))
    for spec in specs:
        person = etree.SubElement(people, qname("person"))
        person.set(XML_ID, spec.textgroup)
        etree.SubElement(person, qname("persName")).text = spec.name
        etree.SubElement(person, qname("idno"), type="CTS").text = f"urn:cts:greekLit:{spec.textgroup}"
        etree.SubElement(person, qname("idno"), type="source-chapter").text = ",".join(map(str, spec.chapters))
        if spec.textgroup in AUTHORITY_EVIDENCE:
            authority_urn, coverage_row = AUTHORITY_EVIDENCE[spec.textgroup]
            etree.SubElement(person, qname("idno"), type="PerseusAuthor").text = authority_urn
            etree.SubElement(person, qname("idno"), type="LSJCoverageRow").text = coverage_row
        if spec.textgroup in CANON_KEY_EVIDENCE:
            etree.SubElement(person, qname("idno"), type="TLGCanonKey").text = (
                CANON_KEY_EVIDENCE[spec.textgroup]
            )
        if spec.textgroup.startswith("tragfrag"):
            etree.SubElement(person, qname("note"), type="identifierStatus").text = (
                "Stable local identifier; reconcile with an external author authority when available."
            )
    write_xml(etree.ElementTree(root), path)


def write_corpus_manifest(specs: tuple[AuthorSpec, ...], data_dir: Path, path: Path) -> None:
    xi = "http://www.w3.org/2001/XInclude"
    root = etree.Element(qname("teiCorpus"), nsmap={None: TEI, "xi": xi})
    root.set(XML_ID, CORPUS_ID)
    header = etree.SubElement(root, qname("teiHeader"))
    fd = etree.SubElement(header, qname("fileDesc"))
    ts = etree.SubElement(fd, qname("titleStmt"))
    etree.SubElement(ts, qname("title")).text = "Tragicorum Graecorum Fragmenta"
    etree.SubElement(ts, qname("editor")).text = "August Nauck"
    ps = etree.SubElement(fd, qname("publicationStmt"))
    etree.SubElement(ps, qname("p")).text = "TEI corpus manifest"
    sd = etree.SubElement(fd, qname("sourceDesc"))
    etree.SubElement(sd, qname("bibl")).text = "Nauck, Tragicorum Graecorum Fragmenta, 2nd ed. (1889)."
    for textgroup, version in (
        ("tlg0085", "nauck1889-grc1"),
        ("tlg0011", VERSION),
        ("tlg0006", VERSION),
    ):
        editions = sorted(
            (data_dir / textgroup).glob(f"*/{textgroup}.*.{version}.xml"))
        if not editions:
            raise FileNotFoundError(
                f"No play-level Nauck {textgroup} editions found")
        for edition in editions:
            etree.SubElement(
                root, f"{{{xi}}}include",
                href="../" + str(edition.relative_to(path.parent.parent)))
    for spec in specs:
        if spec.textgroup in {"tlg0011", "tlg0006"}:
            continue
        author_path = data_dir / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.{VERSION}.xml"
        etree.SubElement(root, f"{{{xi}}}include", href="../" + str(author_path.relative_to(path.parent.parent)))
    write_xml(etree.ElementTree(root), path)


def registry_record(spec: AuthorSpec, data_dir: Path) -> dict:
    source = data_dir / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.{VERSION}.xml"
    return {
        "textgroup": spec.textgroup,
        "work": "fragmenta",
        "title": f"{spec.name}, Fragments",
        "fragmentary": True,
        "record_type": "fragment_author_collection",
        "source_edition": CORPUS_ID,
        "editions": {},
        "appcrits": {},
        "translations": {},
        "commentaries": {},
        "treebanks": {},
        "fragment_editions": {
            VERSION: {
                "path": str(source),
                "urn": f"urn:cts:greekLit:{spec.textgroup}.fragmenta.{VERSION}",
                "label": "Greek (Nauck, 1889; transcription preview) (OCR draft)",
                "class": "greek-text",
                "format": "tei_fragment_collection",
                "corresp_axis": "work",
            }
        },
        "object_urn": f"urn:cite2:perseus:fragmentaryauthors.v1:{spec.textgroup}",
    }


def play_registry_records(spec: AuthorSpec, data_dir: Path) -> dict[str, dict]:
    source = data_dir / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.{VERSION}.xml"
    tree = etree.parse(str(source))
    records = {}
    for container in tree.xpath(
        "//tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        title = container.xpath("string(tei:head[1])", namespaces=NS).strip()
        title_work_id = container.get("n")
        record = registry_record(spec, data_dir)
        record.update({
            "work": title_work_id,
            "title": title,
            "source_title": title,
            "record_type": (
                "fragmentary_play" if container.get("subtype") == "play"
                else "fragment_collection"
            ),
            "object_urn": container.get("corresp"),
        })
        records[f"{spec.textgroup}.{title_work_id}"] = record
    return records


def publication_model(source: Path) -> dict:
    """Read one generated author TEI as an aggregate publication model."""
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition_urn = edition.get("n")
    textgroup = edition_urn.split(":")[-1].split(".", 1)[0]
    author = tree.xpath("string(//tei:titleStmt/tei:author[1])", namespaces=NS)
    fragments = []
    fragments_by_id = {}
    for fragment in edition.xpath(".//tei:div[@subtype='fragment']", namespaces=NS):
        number = fragment.get("n")
        lines = [
            {"ref": line.get("n") or str(index), "source_id": line.get(XML_ID), "text": text(line)}
            for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1)
        ]
        context = "\n\n".join(
            text(child) for child in fragment
            if etree.QName(child).localname not in {"head", "lg", "milestone"} and text(child)
        )
        record = {
            "number": number,
            "source_id": fragment.get(XML_ID),
            "edition": VERSION,
            "source_fragment_urn": f"{edition_urn}:{number}",
            "same_as": [],
            "lines": lines,
            "context": context,
        }
        fragments.append(record)
        fragments_by_id[fragment.get(XML_ID)] = record
    works = {}
    attributions = []
    for container in edition.xpath(
        ".//tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        container_id = container.get(XML_ID)
        title_work_id = container.get("n")
        object_urn = container.get("corresp")
        printed_title = container.xpath("string(tei:head[1])", namespaces=NS).strip()
        works[container_id] = {
            "id": container_id,
            "work": title_work_id,
            "object_urn": object_urn,
            "title": printed_title,
            "source_title": printed_title,
            "source": source.name,
            "selector": f"#{container_id}",
            "record_type": (
                "fragmentary_play" if container.get("subtype") == "play"
                else "fragment_collection"
            ),
            "introduction": "\n\n".join(
                text(child) for child in container
                if etree.QName(child).localname not in {"head", "div"} and text(child)
            ),
        }
        targets = [
            fragments_by_id[fragment.get(XML_ID)]["source_fragment_urn"]
            for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS)
        ]
        for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            record = fragments_by_id[fragment.get(XML_ID)]
            record.update({
                "play_title": printed_title,
                "play_work": title_work_id,
                "play_urn": object_urn,
            })
        if targets:
            attribution_id = f"{VERSION}-{spec_safe_id(textgroup)}-{title_work_id}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": "Perseus",
                "edition": VERSION,
                "play_urn": object_urn,
                "corresp": targets,
            })
    return {
        "schema_version": 4,
        "textgroup": textgroup,
        "author": author,
        "corpus_title": f"{author}, Fragments",
        "source_label": "Nauck’s notes",
        "canonical_source": source.name,
        "source_format": "tei",
        "versions": [{
            "short_id": VERSION,
            "edition_urn": edition_urn,
            "label": "Greek (Nauck, 1889; transcription preview) (OCR draft)",
            "source": source.name,
        }],
        "fragments": fragments,
        "works": works,
        "attributions": attributions,
    }


def spec_safe_id(value: str) -> str:
    """Keep generated CITE object identifiers independent of punctuation."""
    return re.sub(r"[^0-9A-Za-z_-]+", "_", value)


def update_registry(specs: tuple[AuthorSpec, ...], registry_path: Path, data_dir: Path) -> None:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = {
        key: value for key, value in registry.items()
        if not (isinstance(value, dict) and value.get("source_edition") == CORPUS_ID)
    }
    for spec in specs:
        registry[f"{spec.textgroup}.fragmenta"] = registry_record(spec, data_dir)
        registry.update(play_registry_records(spec, data_dir))
    # Sophocles has a second, independently numbered fragment edition.  Keep
    # it in the same registry records used by the aligned PMV work shards.
    from pipeline.sophocles_fragment_concordance import NAUCK_WORK_ALIASES
    pearson_path = (Path(__file__).resolve().parents[1] / "experimental" /
                    "sophocles" / "fragment-collections.json")
    if pearson_path.exists():
        pearson = json.loads(pearson_path.read_text(encoding="utf-8"))
        pearson_edition = {
            "path": str(pearson_path),
            "urn": "urn:cts:greekLit:tlg0011.fragmenta.pearson1917-grc1",
            "label": "Greek with commentary (A. C. Pearson, 1917) (OCR draft)",
            "class": "greek-text", "format": "json_fragment_collection",
            "corresp_axis": "work",
        }
        aggregate = registry["tlg0011.fragmenta"]
        aggregate["fragment_editions"]["pearson1917-grc1"] = pearson_edition
        aggregate["source_edition"] = "multiple-fragment-editions"
        for work in pearson.get("works", {}).values():
            slug = work["work"]
            key = f"tlg0011.{slug}"
            record = registry.setdefault(key, {
                "textgroup": "tlg0011", "work": slug,
                "title": work.get("source_title") or work.get("title", slug),
                "fragmentary": True, "record_type": "fragmentary_play",
                "source_edition": "multiple-fragment-editions",
                "editions": {}, "appcrits": {}, "translations": {},
                "commentaries": {}, "treebanks": {}, "fragment_editions": {},
                "object_urn": work.get("object_urn"),
                "source_title": work.get("source_title") or work.get("title", slug),
            })
            record.setdefault("fragment_editions", {})["pearson1917-grc1"] = pearson_edition
            if "nauck1889grc1" in record["fragment_editions"]:
                record["source_edition"] = "multiple-fragment-editions"
        for nauck_slug, canonical_slug in NAUCK_WORK_ALIASES.items():
            old_key, canonical_key = f"tlg0011.{nauck_slug}", f"tlg0011.{canonical_slug}"
            if old_key == canonical_key or old_key not in registry or canonical_key not in registry:
                continue
            nauck_edition = registry[old_key].get("fragment_editions", {}).get("nauck1889grc1")
            if nauck_edition:
                registry[canonical_key].setdefault("fragment_editions", {})["nauck1889grc1"] = nauck_edition
                registry[canonical_key]["source_edition"] = "multiple-fragment-editions"
                registry[old_key]["canonical_fragment_work"] = canonical_key
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(source: Path, data_dir: Path, registry_path: Path | None = None) -> dict:
    tree = load_source(source)
    chapters = source_chapters(tree)
    corpus_dir = data_dir / CORPUS_ID
    master = corpus_dir / "source" / "nauck1889.tragicorum-graecorum-fragmenta.xml"
    revision = tree.find(".//tei:revisionDesc", NS)
    if revision is None:
        header = tree.find(".//tei:teiHeader", NS)
        revision = etree.SubElement(header, qname("revisionDesc"))
    etree.SubElement(revision, qname("change"), when="2026-10-07").text = (
        f"Imported from {source}; repaired its malformed TEI namespace URI without altering textual content."
    )
    write_xml(tree, master)
    counts = {}
    for spec in AUTHORS:
        author_tree = normalize_author(spec, source_nodes(spec, chapters), master)
        source_out = data_dir / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.{VERSION}.xml"
        write_xml(author_tree, source_out)
        if spec.textgroup not in {"tlg0011", "tlg0006"}:
            write_xml(textgroup_cts(spec), data_dir / spec.textgroup / "__cts__.xml")
        write_xml(work_cts(spec), data_dir / spec.textgroup / "fragments/__cts__.xml")
        counts[spec.textgroup] = {
            "author": spec.name,
            "fragments": len(author_tree.xpath("//tei:div[@subtype='fragment']", namespaces=NS)),
            "lines": len(author_tree.xpath("//tei:l", namespaces=NS)),
            "plays": len(author_tree.xpath("//tei:div[@subtype='play']", namespaces=NS)),
        }
    write_authority(AUTHORS, corpus_dir / "authority.xml")
    write_corpus_manifest(AUTHORS, data_dir, corpus_dir / "corpus.xml")
    (corpus_dir / "build-report.json").write_text(
        json.dumps({"source": str(source), "authors": counts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if registry_path:
        update_registry(AUTHORS, registry_path, data_dir)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    counts = build(args.source, args.data_dir, args.registry)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
