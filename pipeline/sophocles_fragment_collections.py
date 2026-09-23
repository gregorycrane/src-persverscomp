"""Normalize Pearson's three-volume Sophocles fragments for PMV.

The source XML is retained unchanged.  This adapter creates a stand-off JSON
collection, including printed volume/page provenance for every fragment.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from pathlib import Path

from lxml import etree

NS = {"t": "http://www.tei-c.org/ns/1.0"}
TEI = "{%s}" % NS["t"]
VERSION = "pearson1917-grc1"
TEXTGROUP = "tlg0011"
EDITION_URN = f"urn:cts:greekLit:{TEXTGROUP}.fragmenta.{VERSION}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# A heading printed between fragments starts the work represented by the next
# numbered fragment.  Multiple headings at the same boundary represent
# evidence-only titles followed by the title to which fragments are assigned.
VOLUME_ONE_BOUNDARIES = [
    (0, ["ΑΘΑΜΑΣ Α ΚΑΙ Β"]), (10, ["ΑΙΑΣ ΛΟΚΡΟΣ"]),
    (18, ["ΑΙΓΕΥΣ"]), (25, ["ΑΙΓΙΣΘΟΣ"]), (27, ["ΑΙΘΙΟΠΕΣ"]),
    (33, ["ΑΙΧΜΑΛΩΤΙΔΕΣ"]), (59, ["ΑΚΡΙΣΙΟΣ"]), (76, ["ΑΛΕΑΔΑΙ"]),
    (91, ["ΑΛΕΞΑΝΔΡΟΣ"]), (100, ["ΑΛΗΤΗΣ"]),
    (110, ["ΑΜΥΚΟΣ ΣΑΤΥΡΙΚΟΣ"]), (112, ["ΑΜΦΙΑΡΕΩΣ ΣΑΤΥΡΙΚΟΣ"]),
    (121, ["ΑΜΦΙΤΡΥΩΝ"]), (124, ["ΑΝΔΡΟΜΑΧΗ"]), (125, ["ΑΝΔΡΟΜΕΔΑ"]),
    (136, ["ΑΝΤΗΝΟΡΙΔΑΙ"]), (139, ["ΑΤΡΕΥΣ Η ΜΥΚΗΝΑΙΑΙ"]),
    (141, ["ΑΧΑΙΩΝ ΣΥΛΛΟΓΟΣ"]), (148, ["ΑΧΙΛΛΕΩΣ ΕΡΑΣΤΑΙ"]),
    (157, ["ΔΑΙΔΑΛΟΣ"]), (164, ["ΔΑΝΑΗ"]),
    (170, ["ΔΙΟΝΥΣΙΣΚΟΣ ΣΑΤΥΡΙΚΟΣ"]), (173, ["ΔΟΛΟΠΕΣ"]),
    (175, ["ΕΛΕΝΗΣ ΑΠΑΙΤΗΣΙΣ"]), (180, ["ΕΛΕΝΗΣ ΓΑΜΟΣ ΣΑΤΥΡΙΚΟΣ"]),
    (184, ["ΕΠΙΓΟΝΟΙ", "ΕΡΙΦΥΛΗ"]), (198, ["ΕΡΙΣ"]),
    (201, ["ΕΡΜΙΟΝΗ"]), (203, ["ΕΥΜΗΛΟΣ"]),
    (205, ["ΕΥΡΥΑΛΟΣ", "ΕΥΡΥΠΥΛΟΣ"]), (222, ["ΕΥΡΥΣΑΚΗΣ"]),
    (223, ["ΗΡΑΚΛΗΣ ΕΠΙ ΤΑΙΝΑΡΩΙ ΣΑΤΥΡΟΙ ΗΡΑΚΛΕΙΣΚΟΣ"]),
    (234, ["ΗΡΙΓΟΝΗ"]), (236, ["ΘΑΜΥΡΑΣ"]), (245, ["ΘΗΣΕΥΣ"]),
    (246, ["ΘΥΕΣΤΗΣ ΕΝ ΣΙΚΥΩΝΙ"]), (269, ["ΙΒΗΡΕΣ", "ΙΝΑΧΟΣ"]),
    (295, ["ΙΞΙΩΝ"]), (296, ["ΙΟΒΑΤΗΣ"]), (299, ["ΙΠΠΟΝΟΥΣ"]),
    (304, ["ΙΦΙΓΕΝΕΙΑ"]), (313, ["ΙΧΝΕΥΤΑΙ ΣΑΤΥΡΟΙ"]),
]

GREEK = str.maketrans({
    "Α":"A", "Β":"B", "Γ":"G", "Δ":"D", "Ε":"E", "Ζ":"Z",
    "Η":"E", "Θ":"Th", "Ι":"I", "Κ":"K", "Λ":"L", "Μ":"M",
    "Ν":"N", "Ξ":"X", "Ο":"O", "Π":"P", "Ρ":"R", "Σ":"S",
    "Τ":"T", "Υ":"Y", "Φ":"Ph", "Χ":"Ch", "Ψ":"Ps", "Ω":"O",
    "ς":"s", "ϲ":"s",
})


def content(element):
    return " ".join("".join(element.itertext()).split())


def roman(volume):
    return ("I", "II", "III")[int(volume) - 1]


def transliterate(title):
    normalized = unicodedata.normalize("NFD", title.upper())
    plain = "".join(c for c in normalized if not unicodedata.combining(c))
    plain = plain.translate(GREEK)
    plain = re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-").lower()
    return plain or "untitled"


def display_title(title):
    return transliterate(title).replace("-", " ").title()


def page_data(fragment, volume):
    preceding = fragment.xpath("preceding::t:pb[1]", namespaces=NS)
    pages = []
    if preceding and preceding[0].get("n"):
        pages.append(preceding[0].get("n"))
    for pb in fragment.xpath(".//t:pb", namespaces=NS):
        if pb.get("n") and pb.get("n") not in pages:
            pages.append(pb.get("n"))
    return {
        "volume": str(volume), "page": pages[0] if pages else None,
        "pages": pages,
        "page_refs": [{"volume": str(volume), "page": p,
                       **({"facs": pb.get("facs")} if pb.get("facs") else {})}
                      for p in pages
                      for pb in [next((x for x in fragment.getroottree().xpath(
                          "//t:pb[@n=$page]", namespaces=NS, page=p)
                          if x.get("facs")), etree.Element("pb"))]],
    }


def parse_fragment(fragment, volume):
    number = fragment.get("n")
    line_nodes = fragment.xpath('.//t:quote[@type="fragtext"]//t:l', namespaces=NS)
    if not line_nodes:
        line_nodes = fragment.xpath(".//t:lg/t:l", namespaces=NS)
    lines = [{"ref": line.get("n") or str(i), "source_id": line.get(XML_ID),
              "text": content(line)} for i, line in enumerate(line_nodes, 1)]
    excluded = set(fragment.xpath('.//t:quote[@type="fragtext"]', namespaces=NS))
    context_parts = []
    for child in fragment:
        if child in excluded or etree.QName(child).localname in {"head", "pb"}:
            continue
        text = content(child)
        if text:
            context_parts.append(text)
    record = {
        "number": number, "source_id": fragment.get(XML_ID), "lines": lines,
        "context": "\n\n".join(context_parts), "edition": VERSION,
        "source_fragment_urn": f"{EDITION_URN}:{number}", "same_as": [],
    }
    record.update(page_data(fragment, volume))
    return record


def make_work(title, index, source, selector, evidence_only=False):
    slug = transliterate(title)
    record_id = f"sophocles-{slug}"
    return record_id, {
        "id": record_id, "work": slug.replace("-", "_"),
        "object_urn": f"urn:cite2:perseus:fragmentaryplays.v1:{record_id}",
        "title": display_title(title), "source_title": title,
        "source": source, "selector": selector, "introduction": "",
        "evidence_only": evidence_only, "order": index,
    }


def build(sources):
    paths = [Path(source) for source in sources]
    if len(paths) != 3:
        raise ValueError("Pearson collection requires volumes 1, 2, and 3")
    fragments = []
    works = {}
    assignments = {}
    order = 0

    # Volume I lacks play containers, so use the printed heading boundaries.
    tree = etree.parse(str(paths[0]))
    vol1 = {int(f.get("n")): f for f in tree.xpath(
        '//t:div[@type="textpart"][@n]', namespaces=NS)}
    boundaries = []
    for after, titles in VOLUME_ONE_BOUNDARIES:
        for title in titles[:-1]:
            order += 1
            rid, work = make_work(title, order, paths[0].name,
                                  f"after-fragment-{after}", True)
            works[rid] = work
        title = titles[-1]
        order += 1
        rid, work = make_work(title, order, paths[0].name, f"after-fragment-{after}")
        works[rid] = work
        boundaries.append((after + 1, rid))
    for i, (start, rid) in enumerate(boundaries):
        end = boundaries[i + 1][0] - 1 if i + 1 < len(boundaries) else 318
        for number in range(start, end + 1):
            if number in vol1:
                assignments[str(number)] = rid
                fragments.append(parse_fragment(vol1[number], 1))

    # Volume II explicitly encodes play containers.
    tree = etree.parse(str(paths[1]))
    for play in tree.xpath('//t:div[@subtype="play"]', namespaces=NS):
        title = play.get("n") or "Untitled"
        order += 1
        source_fragments = play.xpath('./t:div[@type="textpart"][@n]', namespaces=NS)
        rid, work = make_work(title, order, paths[1].name,
                              f"fragments-{source_fragments[0].get('n') if source_fragments else 'none'}",
                              not source_fragments)
        works[rid] = work
        for frag in source_fragments:
            assignments[frag.get("n")] = rid
            fragments.append(parse_fragment(frag, 2))

    # The first two volumes supply the named play headings.  Volume III adds
    # collection-level containers for fragments whose play is uncertain or
    # whose authenticity is disputed; those containers are not play titles.
    play_headings = len(works)

    # Volume III is explicitly divided into uncertain and dubious/spurious.
    tree = etree.parse(str(paths[2]))
    volume_three_fragments = tree.xpath('//t:div[@type="textpart"][@n]', namespaces=NS)
    for idx, (title, first, last) in enumerate((
        ("Uncertain-play fragments", 731, 1116),
        ("Dubious and spurious fragments", 1117, 1129),
    ), 1):
        order += 1
        rid, work = make_work(title, order, paths[2].name, f"volume-3-section-{idx}")
        works[rid] = work
        for frag in volume_three_fragments:
            number = int(frag.get("n"))
            if first <= number <= last:
                assignments[frag.get("n")] = rid
                fragments.append(parse_fragment(frag, 3))

    # Pearson's missing no. 314 is the separately installed Ichneutae.
    ich = next(k for k in works if k.startswith("sophocles-ichneytai"))
    works[ich]["external_work_urn"] = "urn:cts:greekLit:tlg0011.tlg008"
    works[ich]["external_fragment"] = "314"

    fragments.sort(key=lambda f: int(f["number"]))
    attributions = []
    for rid, work in works.items():
        refs = [f["source_fragment_urn"] for f in fragments
                if assignments.get(f["number"]) == rid]
        if refs:
            attributions.append({
                "id": f"{VERSION}-{work['work']}",
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{VERSION}-{work['work']}",
                "resp": "A. C. Pearson", "edition": VERSION,
                "play_urn": work["object_urn"], "corresp": refs,
            })
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()
    return {
        "schema_version": 4, "textgroup": TEXTGROUP, "author": "Sophocles",
        "corpus_title": "Fragments", "source_label": "Pearson's notes and apparatus",
        "source_sha256": digest,
        "versions": [{"short_id": VERSION, "edition_urn": EDITION_URN,
                      "label": "Greek with commentary (A. C. Pearson, 1917) (OCR draft)",
                      "source": [p.name for p in paths]}],
        "fragments": fragments, "works": works, "attributions": attributions,
        "collections": [{"id": "sophocles-fragments", "title": "Fragments",
                         "author": "Sophocles", "textgroup": TEXTGROUP,
                         "members": list(works)}],
        "scope": {"play_headings": play_headings,
                  "included_fragments": len(fragments),
                  "missing_fragment_numbers": [314], "volumes": 3},
        "editorial_note": "Pearson's volume and printed-page boundaries are retained for image comparison. Fragment 314 is linked to the separately installed Ichneutae.",
    }


def write_collection(sources, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build(sources), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
