"""Parse Dindorf's Euripidean fragments and align them with Nauck."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from lxml import etree

from pipeline.fragment_collections import materialize_work_views
from pipeline.sophocles_fragment_concordance import align_fragments


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
DINDORF = "dindorf1893-grc1"
NAUCK = "nauck1889grc1"
TEXTGROUP = "tlg0006"


def _text(element):
    return " ".join("".join(element.itertext()).split())


def build_dindorf(source: Path) -> dict:
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
            source_urn = f"{edition_urn}:{work}.{number}"
            lines = [
                {"ref": line.get("n") or str(index), "source_id": line.get(XML_ID),
                 "text": _text(line)}
                for index, line in enumerate(fragment.xpath(".//tei:l", namespaces=NS), 1)
            ]
            context = "\n\n".join(
                _text(child) for child in fragment
                if etree.QName(child).localname not in {"head", "lg"} and _text(child)
            )
            fragments.append({
                "number": number, "source_id": fragment.get(XML_ID),
                "edition": DINDORF, "source_fragment_urn": source_urn,
                "same_as": (fragment.get("sameAs") or "").split(),
                "lines": lines, "context": context, "play_title": title,
                "play_work": work, "play_urn": object_urn,
            })
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
            attribution_id = f"{DINDORF}-{TEXTGROUP}-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": "Wilhelm Dindorf", "edition": DINDORF,
                "play_urn": object_urn, "corresp": targets,
            })
    return {
        "schema_version": 4, "textgroup": TEXTGROUP, "author": "Euripides",
        "corpus_title": "Euripides, Fragments",
        "source_label": "Dindorf's sources and notes",
        "canonical_source": source.name, "source_format": "tei",
        "versions": [{"short_id": DINDORF, "edition_urn": edition_urn,
                      "label": "Greek (Dindorf, 1893; OCR draft)",
                      "source": source.name}],
        "fragments": fragments, "works": works, "attributions": attributions,
    }


def merge_work_views(dindorf_source, nauck_source):
    dindorf = materialize_work_views(dindorf_source)
    nauck = materialize_work_views(nauck_source)
    dworks = {w["work"]: deepcopy(w) for w in dindorf["works"].values()}
    nworks = {w["work"]: deepcopy(w) for w in nauck["works"].values()}
    versions = {v["short_id"]: deepcopy(v)
                for v in dindorf_source["versions"] + nauck_source["versions"]}
    works, concordance = {}, []
    for slug in dict.fromkeys([*dworks, *nworks]):
        dw, nw = dworks.get(slug), nworks.get(slug)
        template = deepcopy(dw or nw)
        dfrags = deepcopy((dw or {}).get("fragments", []))
        nfrags = deepcopy((nw or {}).get("fragments", []))
        pairs = align_fragments(dfrags, nfrags)
        paired_d = {id(d): (n, score, method) for d, n, score, method in pairs}
        paired_n = {id(n) for _, n, _, _ in pairs}
        cards = []
        for fragment in dfrags:
            pair = paired_d.get(id(fragment))
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
                     for f in nfrags if id(f) not in paired_n)
        template["work"] = slug
        template["id"] = f"euripides-{slug.replace('_', '-')}"
        template["object_urn"] = (dw or nw).get("object_urn")
        template["title"] = ((dw or {}).get("source_title")
                             or (nw or {}).get("source_title") or slug)
        template["source_title"] = template["title"]
        template["fragments"] = dfrags + nfrags
        present = ([DINDORF] if dfrags else []) + ([NAUCK] if nfrags else [])
        template["versions"] = [deepcopy(versions[v]) for v in present]
        for version in template["versions"]:
            if not version.get("edition_urn"):
                version["edition_urn"] = (
                    f"urn:cts:greekLit:tlg0006.{slug}.{version['short_id']}")
        template["cards"] = cards
        template["line_count"] = sum(len(f.get("lines", [])) for f in template["fragments"])
        template["evidence_only"] = not bool(cards)
        template["status"] = "Fragmentary text" if cards else "Evidence only"
        works[template["id"]] = template
    return works, concordance


def aggregate_work(works, versions):
    cards, fragments = [], []
    for work in works.values():
        fragments.extend(work.get("fragments", []))
        for card in work.get("cards", []):
            item = deepcopy(card)
            item["label"] = f"{work['work']}-{card['label']}"
            cards.append(item)
    return {
        "id": "euripides-fragmenta", "work": "fragmenta",
        "title": "Euripides, Fragments", "source_title": "FRAGMENTA",
        "object_urn": "urn:cts:greekLit:tlg0006.fragmenta",
        "fragments": fragments, "cards": cards, "versions": versions,
        "status": "Fragmentary text", "fragment_corpus": True,
    }


def update_registry(registry_path: Path, dindorf_path: Path) -> None:
    registry_path, dindorf_path = Path(registry_path), Path(dindorf_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = build_dindorf(dindorf_path)
    edition = {
        "path": str(dindorf_path),
        "urn": f"urn:cts:greekLit:{TEXTGROUP}.fragmenta.{DINDORF}",
        "label": "Greek (Dindorf, 1893; OCR draft)",
        "class": "greek-text", "format": "tei_fragment_collection",
        "corresp_axis": "work",
    }
    aggregate = registry[f"{TEXTGROUP}.fragmenta"]
    aggregate.setdefault("fragment_editions", {})[DINDORF] = edition
    aggregate["source_edition"] = "multiple-fragment-editions"
    aggregate["fragment_corpus"] = True
    for work in source["works"].values():
        slug = work["work"]
        key = f"{TEXTGROUP}.{slug}"
        record = registry.setdefault(key, {
            "textgroup": TEXTGROUP, "work": slug,
            "title": work["source_title"], "fragmentary": True,
            "record_type": work["record_type"], "editions": {}, "appcrits": {},
            "translations": {}, "commentaries": {}, "treebanks": {},
            "fragment_editions": {}, "object_urn": work["object_urn"],
        })
        record.setdefault("fragment_editions", {})[DINDORF] = edition
        record.setdefault("source_title", work["source_title"])
        if work["record_type"] == "fragment_collection":
            record["fragment_collection"] = True
        record["source_edition"] = "multiple-fragment-editions" if (
            NAUCK in record["fragment_editions"]) else "dindorf1893"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def persist_alignments(dindorf_path: Path, concordance: list[dict]) -> int:
    links = {match["dindorf"]: match["nauck"] for match in concordance}
    tree = etree.parse(str(dindorf_path))
    edition = tree.xpath("//tei:div[@type='edition']", namespaces=NS)[0]
    edition_urn = edition.get("n")
    recorded = 0
    for container in edition.xpath(
        "./tei:div[@subtype='play' or @subtype='section']", namespaces=NS
    ):
        work = container.get("n")
        for fragment in container.xpath("./tei:div[@subtype='fragment']", namespaces=NS):
            source_urn = f"{edition_urn}:{work}.{fragment.get('n')}"
            if source_urn in links:
                fragment.set("sameAs", links[source_urn])
                recorded += 1
            else:
                fragment.attrib.pop("sameAs", None)
    revision = tree.xpath("//tei:revisionDesc", namespaces=NS)[0]
    change = etree.SubElement(revision, f"{{{NS['tei']}}}change", when="2026-10-08")
    change.text = (f"Recorded {recorded} conservative Dindorf-to-Nauck correspondences "
                   "from normalized quoted-Greek similarity.")
    tree.write(str(dindorf_path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    return recorded
