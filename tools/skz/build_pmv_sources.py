#!/usr/bin/env python3
"""Convert Farnoosh Shamsian's SKZ tables into native PMV sources.

The upstream repository supplies one sentence-level table, word-alignment
pairs, named entities, and a place gazetteer.  PMV consumes TEI files, its
token-alignment JSON shape, and the small place-reference CSV shape used by
the map.  This script is the reproducible bridge between those formats.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "sources" / "skz" / "upstream"
GENERATED = ROOT / "sources" / "skz" / "generated"
CTS_TEXTGROUP_DIR = GENERATED / "data" / "skz"
CTS_WORK_DIR = CTS_TEXTGROUP_DIR / "inscription"
PLACE_CSV = ROOT / "lodcache" / "citations_skz.csv"

WORK_KEY = "skz.inscription"
SOURCE_URL = "https://github.com/farnoosh-shamsian/SKZ"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("", TEI_NS)

VERSIONS = {
    "canaliderossi2004-grc1": {
        "column": "Greek",
        "label": "Greek (Canali De Rossi, 2004; PHI digital text)",
        "lang": "grc",
        "description": "Greek version of the trilingual inscription",
    },
    "huyse1999-xpr1": {
        "column": "Parthian transliteratlion",
        "label": "Parthian transliteration (Huyse, 1999; via Parthian Sources)",
        "lang": "xpr-Latn",
        "description": "Parthian transliteration",
    },
    "huyse1999-xpr2": {
        "column": "Parthian transcription",
        "label": "Parthian transcription (Huyse, 1999; via Parthian Sources)",
        "lang": "xpr-Latn",
        "description": "Parthian transcription",
    },
    "huyse1999-pal1": {
        "column": "Middle Persian transcription",
        "label": "Middle Persian transcription (Huyse, 1999; Shamsian)",
        "lang": "pal-Latn",
        "description": "Middle Persian transcription",
    },
}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        rows = []
        for raw in reader:
            rows.append({(key or "").strip(): (value or "").strip()
                         for key, value in raw.items()})
        return rows


def _sentence_rows() -> list[dict[str, str]]:
    rows = _read_tsv(UPSTREAM / "SKZ-sentence-level.tsv")
    for row in rows:
        # Preserve the upstream spellings while hiding its two header typos
        # behind stable internal names.
        if "Parthian transčription" in row:
            row["Parthian transcription"] = row.pop("Parthian transčription")
        row["Middle Persian transcription"] = row.pop("Middle Persian transčription")
        match = re.fullmatch(r"ŠKZ Line\s+(\d+)", row["Gr. ŠKZ Lines"])
        if not match:
            raise ValueError(f"Unrecognized SKZ line label: {row['Gr. ŠKZ Lines']!r}")
        row["line"] = match.group(1)
    if len(rows) != 51:
        raise ValueError(f"Expected 51 SKZ lines, found {len(rows)}")
    return rows


def _indent(element: ET.Element, level: int = 0) -> None:
    """Backport ElementTree.indent for the Python 3.8 build environment."""
    whitespace = "\n" + level * "  "
    child_whitespace = "\n" + (level + 1) * "  "
    if len(element):
        if not element.text or not element.text.strip():
            element.text = child_whitespace
        for child in element:
            _indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = child_whitespace
        element[-1].tail = whitespace


def _tei(version: str, cfg: dict[str, str], rows: list[dict[str, str]]) -> ET.ElementTree:
    q = lambda name: f"{{{TEI_NS}}}{name}"
    urn = f"urn:cts:iranianLit:{WORK_KEY}.{version}"
    root = ET.Element(q("TEI"))
    header = ET.SubElement(root, q("teiHeader"), {f"{{{XML_NS}}}lang": "eng"})
    file_desc = ET.SubElement(header, q("fileDesc"))
    title_stmt = ET.SubElement(file_desc, q("titleStmt"))
    ET.SubElement(title_stmt, q("title")).text = (
        "The trilingual inscription of Šābuhr I at the Kaʿba-ye Zartošt (ŠKZ)"
    )
    ET.SubElement(title_stmt, q("author")).text = "Šābuhr I"
    resp = ET.SubElement(title_stmt, q("respStmt"))
    ET.SubElement(resp, q("resp")).text = "Corpus preparation and alignment"
    ET.SubElement(resp, q("name")).text = "Farnoosh Shamsian and Monica Berti"
    publication = ET.SubElement(file_desc, q("publicationStmt"))
    ET.SubElement(publication, q("publisher")).text = "Perseus Digital Library"
    availability = ET.SubElement(publication, q("availability"), {"status": "free"})
    ET.SubElement(availability, q("licence"), {"target": LICENSE_URL}).text = (
        "Creative Commons Attribution-ShareAlike 4.0 International"
    )
    source_desc = ET.SubElement(file_desc, q("sourceDesc"))
    bibl = ET.SubElement(source_desc, q("bibl"))
    bibl.text = (
        f"{cfg['description']} from Farnoosh Shamsian's open SKZ corpus. "
        "Line numbering follows Huyse (1999). Source: "
    )
    ref = ET.SubElement(bibl, q("ref"), {"target": SOURCE_URL})
    ref.text = SOURCE_URL

    encoding = ET.SubElement(header, q("encodingDesc"))
    # HookTest/CapiTainS currently consumes the CTS cRefPattern form rather
    # than TEI's newer citeStructure vocabulary.  Keep the most-specific
    # level first, as CTS expects.
    refs_decl = ET.SubElement(encoding, q("refsDecl"), {"n": "CTS"})
    segment_pattern = ET.SubElement(refs_decl, q("cRefPattern"), {
        "n": "segment",
        "matchPattern": r"(\w+)\.(\w+)",
        "replacementPattern": (
            "#xpath(/tei:TEI/tei:text/tei:body/tei:div/"
            "tei:div[@subtype='section' and @n='$1']/tei:p[@n='$2'])"
        ),
    })
    ET.SubElement(segment_pattern, q("p")).text = "This pattern extracts a segment within an inscription line."
    line_pattern = ET.SubElement(refs_decl, q("cRefPattern"), {
        "n": "line",
        "matchPattern": r"(\w+)",
        "replacementPattern": (
            "#xpath(/tei:TEI/tei:text/tei:body/tei:div/"
            "tei:div[@subtype='section' and @n='$1'])"
        ),
    })
    ET.SubElement(line_pattern, q("p")).text = "This pattern extracts an inscription line."
    profile = ET.SubElement(header, q("profileDesc"))
    usage = ET.SubElement(profile, q("langUsage"))
    ET.SubElement(usage, q("language"), {"ident": cfg["lang"]}).text = cfg["description"]

    # HookTest's CapiTainS TEI profile discovers both the version URN and the
    # document language on the same ``text`` node.  Keeping xml:base on body
    # makes the citation XPath work, but leaves the witness invisible to the
    # CTS inventory checks.
    text = ET.SubElement(root, q("text"), {
        f"{{{XML_NS}}}base": urn,
        f"{{{XML_NS}}}lang": cfg["lang"],
    })
    body = ET.SubElement(text, q("body"))
    edition = ET.SubElement(body, q("div"), {
        "n": urn, "type": "edition", f"{{{XML_NS}}}lang": cfg["lang"],
    })
    for row in rows:
        section = ET.SubElement(edition, q("div"), {
            "type": "textpart", "subtype": "section", "n": row["line"],
        })
        ET.SubElement(section, q("p"), {"n": "1"}).text = row[cfg["column"]]
    _indent(root)
    return ET.ElementTree(root)


def _write_tei(tree: ET.ElementTree, path: Path) -> None:
    body = ET.tostring(tree.getroot(), encoding="utf-8")
    path.write_bytes(
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b'<?xml-model href="https://epidoc.stoa.org/schema/latest/tei-epidoc.rng" '
        b'schematypens="http://relaxng.org/ns/structure/1.0"?>\n'
        + body + b"\n"
    )


def _write_cts_metadata() -> None:
    CTS_TEXTGROUP_DIR.mkdir(parents=True, exist_ok=True)
    CTS_WORK_DIR.mkdir(parents=True, exist_ok=True)
    (CTS_TEXTGROUP_DIR / "__cts__.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<ti:textgroup xmlns:ti="http://chs.harvard.edu/xmlns/cts"
  projid="iranianLit:skz" urn="urn:cts:iranianLit:skz">
  <ti:groupname xml:lang="eng">Šābuhr I</ti:groupname>
</ti:textgroup>
""", encoding="utf-8")

    editions = []
    for version, cfg in VERSIONS.items():
        urn = f"urn:cts:iranianLit:{WORK_KEY}.{version}"
        editions.append(f"""  <ti:edition urn="{urn}" workUrn="urn:cts:iranianLit:{WORK_KEY}" xml:lang="{cfg['lang']}">
    <ti:label xml:lang="eng">{cfg['label']}</ti:label>
    <ti:description xml:lang="eng">{cfg['description']}; 51 lines aligned by Farnoosh Shamsian.</ti:description>
  </ti:edition>""")
    (CTS_WORK_DIR / "__cts__.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<ti:work xmlns:ti="http://chs.harvard.edu/xmlns/cts"
  groupUrn="urn:cts:iranianLit:skz" projid="iranianLit:inscription"
  urn="urn:cts:iranianLit:skz.inscription" xml:lang="grc">
  <ti:title xml:lang="eng">Trilingual inscription at the Kaʿba-ye Zartošt (ŠKZ)</ti:title>
""" + "\n".join(editions) + "\n</ti:work>\n",
        encoding="utf-8",
    )


def _norm(token: str) -> str:
    token = unicodedata.normalize("NFC", token).lower()
    while token and unicodedata.category(token[0])[0] in {"P", "S"}:
        token = token[1:]
    while token and unicodedata.category(token[-1])[0] in {"P", "S"}:
        token = token[:-1]
    return token.strip()


def _tokens(text: str) -> list[str]:
    return [token for token in text.split() if token]


def _occurrences(text: str, phrase: str) -> list[list[int]]:
    display = _tokens(text)
    haystack = [_norm(token) for token in display]
    needles = [_norm(token) for token in _tokens(phrase)]
    if not needles or any(not token for token in needles):
        return []
    width = len(needles)
    return [list(range(index, index + width))
            for index in range(len(haystack) - width + 1)
            if haystack[index:index + width] == needles]


def _alignment_json(
    sentence_rows: list[dict[str, str]], target_column: str, pair_column: str,
    target_version: str,
) -> tuple[dict, int]:
    by_line = {row["line"]: row for row in sentence_rows}
    segments: dict[str, dict] = {
        f"{line}.1": {
            "source_text": row["Greek"],
            "target_text": row[target_column],
            "alignments": [],
        }
        for line, row in by_line.items()
    }
    unmatched = 0
    for source_row, pair in enumerate(_read_tsv(UPSTREAM / "alignment-pairs.tsv"), start=2):
        line_match = re.search(r"(\d+)", pair.get("Line", ""))
        if not line_match:
            unmatched += 1
            continue
        line = line_match.group(1)
        greek = pair.get("Greek", "")
        target = pair.get(pair_column, "")
        if not greek or not target or line not in by_line:
            unmatched += 1
            continue
        src_occ = _occurrences(by_line[line]["Greek"], greek)
        tgt_occ = _occurrences(by_line[line][target_column], target)
        try:
            frequency = max(1, int(pair.get("Frequency in line", "1")))
        except ValueError:
            frequency = 1
        matched = min(frequency, len(src_occ), len(tgt_occ))
        if matched == 0:
            unmatched += 1
            continue
        for occurrence in range(matched):
            segments[f"{line}.1"]["alignments"].append({
                "src_indices": src_occ[occurrence],
                "tgt_indices": tgt_occ[occurrence],
                "src_tokens": _tokens(greek),
                "tgt_tokens": _tokens(target),
                "score": 1.0,
                "meta": {
                    "relation": "manual-Ugarit",
                    "reference": f"ŠKZ line {line}",
                    "upstream_row": source_row,
                },
            })
        if matched < frequency:
            unmatched += 1

    source_version = "canaliderossi2004-grc1"
    payload = {
        "alignment_meta": {
            "source_urn": f"urn:cts:iranianLit:{WORK_KEY}.{source_version}",
            "target_urn": f"urn:cts:iranianLit:{WORK_KEY}.{target_version}",
            "method": "manual-word-and-phrase-alignment",
            "aligner": "Farnoosh Shamsian",
            "description": f"Greek to {target_column} word and phrase alignments.",
            "source": SOURCE_URL,
            "license": "CC BY-SA 4.0",
        },
        "segments": segments,
    }
    return payload, unmatched


def _place_rows() -> tuple[list[dict[str, str]], int]:
    places = _read_tsv(UPSTREAM / "skz-places.tsv")
    entities = _read_tsv(UPSTREAM / "named-entities.tsv")
    index: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for place in places:
        lines = [value.strip() for value in place["lines"].split(";") if value.strip()]
        forms = [value.strip() for value in place["greek_forms"].split(";") if value.strip()]
        for line in lines:
            for form in forms:
                index[(line, _norm(form))].append(place)

    output, unmatched = [], 0
    seen = set()
    for entity in entities:
        if entity.get("Category") not in {"#LOC", "#LOCderiv"}:
            continue
        line_match = re.search(r"(\d+)", entity.get("Line", ""))
        if not line_match:
            unmatched += 1
            continue
        line = line_match.group(1)
        candidates = index.get((line, _norm(entity.get("Greek", ""))), [])
        if not candidates:
            # Some Greek rows are blank or restored differently.  The line is
            # already a strong constraint; use either Iranian surface form.
            candidates = [place for place in places
                          if line in {v.strip() for v in place["lines"].split(";")}
                          and ((entity.get("Parthian") and entity["Parthian"] in place["parthian_forms"])
                               or (entity.get("Middle Persian") and entity["Middle Persian"] in place["mp_forms"]))]
        if not candidates:
            unmatched += 1
            continue
        place = candidates[0]
        key = (line, place["place_id"], entity.get("Greek", ""), entity.get("Category", ""))
        if key in seen:
            continue
        seen.add(key)
        forms = [entity.get(name, "") for name in ("Greek", "Parthian", "Middle Persian")]
        output.append({
            "citation": line,
            "mention_type": entity["Category"].lstrip("#"),
            "mention_name": " / ".join(value for value in forms if value),
            "place_id": place["place_id"],
            "place_name": place["label"],
            "lat": place["latitude"],
            "lon": place["longitude"],
            "feature_type": place["type"],
            "certainty": place["certainty"],
            "coord_source": place["coord_source"],
            "coord_precision": place["coord_precision"],
            "place_note": place["note"],
            "resolution_note": place["resolution"],
        })
    return output, unmatched


def main() -> None:
    _write_cts_metadata()
    rows = _sentence_rows()
    for version, cfg in VERSIONS.items():
        path = CTS_WORK_DIR / f"{WORK_KEY}.{version}.xml"
        _write_tei(_tei(version, cfg, rows), path)

    for target_column, pair_column, target_version in (
        ("Parthian transcription", "Parthian", "huyse1999-xpr2"),
        ("Middle Persian transcription", "Middle Persian", "huyse1999-pal1"),
    ):
        payload, unmatched = _alignment_json(
            rows, target_column, pair_column, target_version
        )
        name = f"canaliderossi2004-grc1__{target_version}.json"
        (CTS_WORK_DIR / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        groups = sum(len(segment["alignments"]) for segment in payload["segments"].values())
        print(f"{name}: {groups} alignment groups; {unmatched} upstream pair rows unmatched")

    place_rows, unmatched_places = _place_rows()
    with PLACE_CSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "citation", "mention_type", "mention_name", "place_id",
            "place_name", "lat", "lon", "feature_type", "certainty",
            "coord_source", "coord_precision", "place_note", "resolution_note",
        ])
        writer.writeheader()
        writer.writerows(place_rows)
    print(f"{PLACE_CSV.name}: {len(place_rows)} place attestations; "
          f"{unmatched_places} named-place rows unmatched")


if __name__ == "__main__":
    main()
