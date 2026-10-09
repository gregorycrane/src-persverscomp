"""Parse Dindorf's Aeschylean fragments and align them with Nauck.

The editions retain their own fragment numbers.  A shared PMV card is made
only when normalized quoted Greek provides positive evidence of identity.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from lxml import etree

from pipeline.fragment_collections import materialize_work_views
from pipeline.sophocles_fragment_concordance import align_fragments


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DINDORF = "dindorf1893-grc1"
NAUCK = "nauck1889-grc1"


def _text(element):
    return " ".join("".join(element.itertext()).split())


def build_play_level(data_root: Path, version: str) -> dict:
    """Read one edition from the canonical play-level CTS package.

    Each XML file is now a genuine CTS work edition.  This function derives
    PMV's transient collection model without reintroducing an aggregate source
    file as a second authority.
    """
    data_root = Path(data_root)
    paths = sorted(data_root.glob(f"*/tlg0085.*.{version}.xml"))
    if not paths:
        raise FileNotFoundError(f"No tlg0085 play-level {version} files in {data_root}")
    fragments, works, attributions = [], {}, []
    editor = "Wilhelm Dindorf" if version == DINDORF else "Augustus Nauck"
    label = ("Greek (Dindorf, 1893; OCR draft)" if version == DINDORF
             else "Greek (Nauck, 1889; OCR draft)")

    for source in paths:
        tree = etree.parse(str(source))
        edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
        edition_urn = edition.get("n")
        urn_parts = edition_urn.split(":")[-1].split(".")
        work = urn_parts[1]
        object_urn = edition.get("corresp")
        title = edition.xpath("string(tei:head[1])", namespaces=NS).strip()
        record_id = f"aeschylus-{version}-{work}"
        targets = []
        for fragment in edition.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            number = fragment.get("n")
            source_urn = f"{edition_urn}:{number}"
            lines = [
                {"ref": line.get("n") or str(index),
                 "source_id": line.get(XML_ID), "text": _text(line)}
                for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1)
            ]
            context = "\n\n".join(
                _text(child) for child in fragment
                if etree.QName(child).localname not in {"head", "lg"} and _text(child)
            )
            fragments.append({
                "number": number, "source_id": fragment.get(XML_ID),
                "edition": version, "source_fragment_urn": source_urn,
                "same_as": (fragment.get("sameAs") or "").split(),
                "lines": lines, "context": context,
                "play_title": title, "play_work": work, "play_urn": object_urn,
            })
            targets.append(source_urn)
        record_type = ("fragment_collection" if "fragmentarycollections" in object_urn
                       else "fragmentary_play")
        works[record_id] = {
            "id": record_id, "work": work, "object_urn": object_urn,
            "title": title, "source_title": title, "source": source.name,
            "selector": f"{source.name}#edition", "record_type": record_type,
            "introduction": "\n\n".join(
                _text(child) for child in edition
                if etree.QName(child).localname not in {"head", "div", "pb"}
                and _text(child)
            ),
        }
        if targets:
            attribution_id = f"{version}-tlg0085-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": editor, "edition": version,
                "play_urn": object_urn, "corresp": targets,
            })

    return {
        "schema_version": 5, "textgroup": "tlg0085", "author": "Aeschylus",
        "corpus_title": "Aeschylus, Fragments", "source_label": label,
        "canonical_source": str(data_root), "source_format": "tei-play-level",
        "versions": [{"short_id": version, "edition_urn": None,
                      "label": label, "source": str(data_root)}],
        "fragments": fragments, "works": works, "attributions": attributions,
    }


def build_dindorf(source: Path) -> dict:
    """Read the normalized TEI installation into PMV's transient model."""
    source = Path(source)
    tree = etree.parse(str(source))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition_urn = edition.get("n")
    fragments, works, attributions = [], {}, []

    for container in edition.xpath(
        "./tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        work = container.get("n")
        container_id = container.get(XML_ID)
        object_urn = container.get("corresp")
        title = container.xpath("string(tei:head[1])", namespaces=NS).strip()
        targets = []
        for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            number = fragment.get("n")
            citation = f"{work}.{number}"
            source_urn = f"{edition_urn}:{citation}"
            lines = [
                {"ref": line.get("n") or str(index),
                 "source_id": line.get(XML_ID), "text": _text(line)}
                for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1)
            ]
            context = "\n\n".join(
                _text(child) for child in fragment
                if etree.QName(child).localname not in {"head", "lg"} and _text(child)
            )
            record = {
                "number": number, "source_id": fragment.get(XML_ID),
                "edition": DINDORF, "source_fragment_urn": source_urn,
                "same_as": (fragment.get("sameAs") or "").split(),
                "lines": lines, "context": context,
                "play_title": title, "play_work": work, "play_urn": object_urn,
            }
            fragments.append(record)
            targets.append(source_urn)
        works[container_id] = {
            "id": container_id, "work": work, "object_urn": object_urn,
            "title": title, "source_title": title, "source": source.name,
            "selector": f"#{container_id}",
            "record_type": ("fragmentary_play" if container.get("subtype") == "play"
                            else "fragment_collection"),
            "introduction": "\n\n".join(
                _text(child) for child in container
                if etree.QName(child).localname not in {"head", "div", "pb"} and _text(child)
            ),
        }
        if targets:
            attribution_id = f"{DINDORF}-tlg0085-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": "Wilhelm Dindorf", "edition": DINDORF,
                "play_urn": object_urn, "corresp": targets,
            })

    return {
        "schema_version": 4, "textgroup": "tlg0085", "author": "Aeschylus",
        "corpus_title": "Aeschylus, Fragments",
        "source_label": "Dindorf's sources and notes",
        "canonical_source": source.name, "source_format": "tei",
        "versions": [{
            "short_id": DINDORF, "edition_urn": edition_urn,
            "label": "Greek (Dindorf, 1893; OCR draft)", "source": source.name,
        }],
        "fragments": fragments, "works": works, "attributions": attributions,
    }


def safe_card_id(label):
    return re.sub(r"[^0-9A-Za-z_-]+", "-", label).strip("-")


def merge_work_views(dindorf_source, nauck_source):
    """Return aligned lost-play views and a reviewable concordance."""
    dindorf = materialize_work_views(dindorf_source)
    nauck = materialize_work_views(nauck_source)
    dworks = {work["work"]: deepcopy(work) for work in dindorf["works"].values()}
    nworks = {work["work"]: deepcopy(work) for work in nauck["works"].values()}
    versions = {v["short_id"]: deepcopy(v)
                for v in dindorf_source["versions"] + nauck_source["versions"]}
    works, concordance = {}, []

    for slug in dict.fromkeys([*dworks, *nworks]):
        dw, nw = dworks.get(slug), nworks.get(slug)
        template = deepcopy(dw or nw)
        dfrags = deepcopy((dw or {}).get("fragments", []))
        nfrags = deepcopy((nw or {}).get("fragments", []))
        pairs = align_fragments(dfrags, nfrags)
        d_pairs = {id(d): (n, score, method) for d, n, score, method in pairs}
        used_n = {id(n) for _, n, _, _ in pairs}
        cards = []
        for fragment in dfrags:
            pair = d_pairs.get(id(fragment))
            if pair:
                other, score, method = pair
                label = f"D{fragment['number']}=N{other['number']}"
                fragment["same_as"] = [other["source_fragment_urn"]]
                other["same_as"] = [fragment["source_fragment_urn"]]
                cards.append({"label": label, "dindorf": fragment, "nauck": other})
                concordance.append({
                    "work": slug, "card": label,
                    "dindorf": fragment["source_fragment_urn"],
                    "nauck": other["source_fragment_urn"],
                    "confidence": round(score, 4), "method": method,
                })
            else:
                cards.append({"label": f"D{fragment['number']}", "dindorf": fragment})
        cards.extend({"label": f"N{f['number']}", "nauck": f}
                     for f in nfrags if id(f) not in used_n)
        template["work"] = slug
        template["id"] = f"aeschylus-{slug.replace('_', '-')}"
        template["object_urn"] = (dw or nw).get("object_urn")
        template["title"] = ((dw or {}).get("source_title")
                             or (nw or {}).get("source_title") or slug)
        template["fragments"] = dfrags + nfrags
        present = ([DINDORF] if dfrags else []) + ([NAUCK] if nfrags else [])
        template["versions"] = [deepcopy(versions[v]) for v in present]
        for version in template["versions"]:
            version["edition_urn"] = (
                f"urn:cts:greekLit:tlg0085.{slug}.{version['short_id']}")
        template["cards"] = cards
        template["line_count"] = sum(len(f.get("lines", [])) for f in template["fragments"])
        template["evidence_only"] = not bool(cards)
        template["status"] = "Fragmentary text" if cards else "Evidence only"
        works[template["id"]] = template
    return works, concordance


def update_play_level_registry(registry_path: Path, data_root: Path) -> None:
    """Replace aggregate Aeschylus fragment records with CTS work editions."""
    registry_path, data_root = Path(registry_path), Path(data_root)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    canonical = {}
    cts_ns = {"ti": "http://chs.harvard.edu/xmlns/cts"}
    for metadata_path in sorted(data_root.glob("*/__cts__.xml")):
        edition_paths = sorted(metadata_path.parent.glob(
            "tlg0085.*.dindorf1893-grc1.xml")) + sorted(metadata_path.parent.glob(
            "tlg0085.*.nauck1889-grc1.xml"))
        if not edition_paths:
            continue
        metadata = etree.parse(str(metadata_path))
        work_element = metadata.getroot()
        work_urn = work_element.get("urn")
        slug = work_urn.rsplit(".", 1)[-1]
        title = metadata.xpath("string(/ti:work/ti:title[1])", namespaces=cts_ns).strip()
        editions = {}
        for edition_path in edition_paths:
            short_id = edition_path.stem.split(".")[-1]
            edition_urn = f"urn:cts:greekLit:tlg0085.{slug}.{short_id}"
            label = metadata.xpath(
                "string(/ti:work/ti:edition[@urn=$urn]/ti:label[1])",
                namespaces=cts_ns, urn=edition_urn).strip()
            editions[short_id] = {
                "path": str(edition_path), "urn": edition_urn,
                "label": label or short_id, "class": "greek-text",
                "format": "tei_fragment_work", "corresp_axis": "fragment",
            }
        source_tree = etree.parse(str(edition_paths[0]))
        object_urn = source_tree.xpath(
            "string(//tei:div[@type='edition']/@corresp)", namespaces=NS).strip()
        record_type = ("fragment_collection" if "fragmentarycollections" in object_urn
                       else "fragmentary_play")
        record = {
            "textgroup": "tlg0085", "work": slug, "title": title,
            "fragmentary": True, "record_type": record_type,
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {},
            "fragment_editions": editions, "object_urn": object_urn,
            "source_title": title,
            "source_edition": ("multiple-fragment-editions"
                               if len(editions) > 1 else short_id.rsplit("-grc", 1)[0]),
        }
        if record_type == "fragment_collection":
            record["fragment_collection"] = True
        canonical[f"tlg0085.{slug}"] = record

    stale = {key for key, record in registry.items()
             if key.startswith("tlg0085.")
             and (record.get("fragmentary") or record.get("fragment_corpus"))}
    retained = [(key, record) for key, record in registry.items()
                if key not in stale and key not in canonical]
    core_aeschylus = [key for key, record in retained
                      if record.get("textgroup") == "tlg0085"]
    insert_after = core_aeschylus[-1] if core_aeschylus else None
    ordered = {}
    inserted = False
    for key, record in retained:
        ordered[key] = record
        if key == insert_after:
            ordered.update(canonical)
            inserted = True
    if not inserted:
        ordered.update(canonical)
    registry_path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_registry(registry_path: Path, dindorf_path: Path, nauck_path: Path) -> None:
    """Register both TEI sources for the corpus and every applicable play."""
    registry_path, dindorf_path, nauck_path = map(Path, (
        registry_path, dindorf_path, nauck_path))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    dindorf = build_dindorf(dindorf_path)
    from pipeline.fragment_collections import build as build_nauck
    nauck = build_nauck(nauck_path)
    dindorf_edition = {
        "path": str(dindorf_path),
        "urn": f"urn:cts:greekLit:tlg0085.fragmenta.{DINDORF}",
        "label": "Greek (Dindorf, 1893; OCR draft)",
        "class": "greek-text", "format": "tei_fragment_collection",
        "corresp_axis": "work",
    }
    nauck_edition = {
        "path": str(nauck_path),
        "urn": f"urn:cts:greekLit:tlg0085.fragmenta.{NAUCK}",
        "label": "Greek (Nauck, 1889; transcription preview) (OCR draft)",
        "class": "greek-text", "format": "tei_fragment_collection",
        "corresp_axis": "work",
    }
    aggregate = registry["tlg0085.fragmenta"]
    aggregate.setdefault("fragment_editions", {})[NAUCK] = nauck_edition
    aggregate["fragment_editions"][DINDORF] = dindorf_edition
    aggregate["source_edition"] = "multiple-fragment-editions"
    aggregate["fragment_corpus"] = True

    # Bring all old Aeschylean Nauck records into line with the TEI-first rule.
    for key, record in registry.items():
        if key.startswith("tlg0085.") and NAUCK in record.get("fragment_editions", {}):
            record["fragment_editions"][NAUCK] = nauck_edition

    for work in nauck["works"].values():
        slug = work["work"]
        key = f"tlg0085.{slug}"
        record = registry.setdefault(key, {
            "textgroup": "tlg0085", "work": slug,
            "title": work["source_title"], "fragmentary": True,
            "record_type": work["record_type"],
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {}, "fragment_editions": {},
            "object_urn": work["object_urn"],
        })
        record.setdefault("fragment_editions", {})[NAUCK] = nauck_edition
        if work["record_type"] == "fragment_collection":
            record["fragment_collection"] = True

    for work in dindorf["works"].values():
        slug = work["work"]
        key = f"tlg0085.{slug}"
        record = registry.setdefault(key, {
            "textgroup": "tlg0085", "work": slug,
            "title": work["source_title"], "fragmentary": True,
            "record_type": work["record_type"],
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {}, "fragment_editions": {},
            "object_urn": work["object_urn"],
        })
        record["source_title"] = work["source_title"]
        record.setdefault("fragment_editions", {})[DINDORF] = dindorf_edition
        if work["record_type"] == "fragment_collection":
            record["fragment_collection"] = True
        record["source_edition"] = "multiple-fragment-editions" if (
            NAUCK in record["fragment_editions"]) else "dindorf1893"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
