"""Add Dindorf to the aligned Sophocles fragment views.

All three editions retain their own numbering.  Cards are joined only by the
same conservative normalized-quoted-Greek tests used for Pearson and Nauck.
The requested display order is Dindorf, Nauck, Pearson.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from lxml import etree

from pipeline.fragment_collections import materialize_work_views
from pipeline.sophocles_fragment_concordance import (
    NAUCK,
    PEARSON,
    align_fragments,
    merge_work_views as merge_pearson_nauck,
)


NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DINDORF = "dindorf1893-grc1"
FIELD_ORDER = (
    ("dindorf", DINDORF, "D"),
    ("nauck", NAUCK, "N"),
    ("pearson", PEARSON, "P"),
)


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
                "edition": DINDORF, "source_fragment_urn": source_urn,
                "same_as": (fragment.get("sameAs") or "").split(),
                "lines": lines, "context": context,
                "play_title": title, "play_work": work, "play_urn": object_urn,
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
            attribution_id = f"{DINDORF}-tlg0011-{work}"
            attributions.append({
                "id": attribution_id,
                "urn": f"urn:cite2:perseus:fragmentattributions.v1:{attribution_id}",
                "resp": "Wilhelm Dindorf", "edition": DINDORF,
                "play_urn": object_urn, "corresp": targets,
            })

    return {
        "schema_version": 4, "textgroup": "tlg0011", "author": "Sophocles",
        "corpus_title": "Sophocles, Fragments",
        "source_label": "Dindorf's sources and notes",
        "canonical_source": source.name, "source_format": "tei",
        "versions": [{
            "short_id": DINDORF, "edition_urn": edition_urn,
            "label": "Greek (Dindorf; OCR draft)", "source": source.name,
        }],
        "fragments": fragments, "works": works, "attributions": attributions,
    }


def _label(card):
    bits = []
    for field, _, prefix in FIELD_ORDER:
        if card.get(field):
            bits.append(f"{prefix}{card[field]['number']}")
    return "=".join(bits)


def _link_card(card):
    fragments = [card[field] for field, _, _ in FIELD_ORDER if card.get(field)]
    urns = [fragment["source_fragment_urn"] for fragment in fragments]
    for fragment in fragments:
        fragment["same_as"] = [urn for urn in urns if urn != fragment["source_fragment_urn"]]
    card["label"] = _label(card)


def _attach_dindorf(cards, dfrags, pfrags, nfrags):
    """Attach Dindorf fragments to Pearson/Nauck cards with one-to-one matches."""
    card_by_urn = {}
    for index, card in enumerate(cards):
        for field in ("pearson", "nauck"):
            fragment = card.get(field)
            if fragment:
                card_by_urn[fragment["source_fragment_urn"]] = index

    candidates = []
    for field, targets in (("nauck", nfrags), ("pearson", pfrags)):
        for dindorf, other, score, method in align_fragments(dfrags, targets):
            card_index = card_by_urn.get(other["source_fragment_urn"])
            if card_index is not None:
                candidates.append((score, dindorf, other, field, method, card_index))
    candidates.sort(key=lambda item: item[0], reverse=True)
    used_d, used_cards, matches = set(), set(), []
    for score, dindorf, other, field, method, card_index in candidates:
        durn = dindorf["source_fragment_urn"]
        if durn in used_d or card_index in used_cards:
            continue
        cards[card_index]["dindorf"] = dindorf
        used_d.add(durn)
        used_cards.add(card_index)
        matches.append({
            "work": dindorf["play_work"], "dindorf": durn,
            field: other["source_fragment_urn"],
            "confidence": round(score, 4), "method": method,
        })
    for fragment in dfrags:
        if fragment["source_fragment_urn"] not in used_d:
            cards.append({"dindorf": fragment})
    for card in cards:
        _link_card(card)
    return matches


def merge_three_work_views(pearson_source, nauck_source, dindorf_source):
    """Return aligned work views and reviewable pairwise correspondences."""
    base_works, concordance = merge_pearson_nauck(
        materialize_work_views(pearson_source),
        materialize_work_views(nauck_source),
    )
    dindorf = materialize_work_views(dindorf_source)
    dworks = {work["work"]: deepcopy(work) for work in dindorf["works"].values()}
    versions = {
        version["short_id"]: deepcopy(version)
        for version in (dindorf_source.get("versions", [])
                        + nauck_source.get("versions", [])
                        + pearson_source.get("versions", []))
    }
    by_slug = {work["work"]: deepcopy(work) for work in base_works.values()}
    works = {}
    for slug in dict.fromkeys([*by_slug, *dworks]):
        base, dw = by_slug.get(slug), dworks.get(slug)
        template = deepcopy(base or dw)
        cards = deepcopy((base or {}).get("cards", []))
        pfrags = [f for f in deepcopy((base or {}).get("fragments", []))
                  if f.get("edition") == PEARSON]
        nfrags = [f for f in deepcopy((base or {}).get("fragments", []))
                  if f.get("edition") == NAUCK]
        # Cards contain their own deep-copied fragment objects; align against
        # those so attached relations and rendered segments stay in one graph.
        pfrags = [c["pearson"] for c in cards if c.get("pearson")]
        nfrags = [c["nauck"] for c in cards if c.get("nauck")]
        dfrags = deepcopy((dw or {}).get("fragments", []))
        concordance.extend(_attach_dindorf(cards, dfrags, pfrags, nfrags))
        template["work"] = slug
        template["id"] = f"sophocles-{slug.replace('_', '-')}"
        template["object_urn"] = ((base or dw).get("object_urn")
                                  or f"urn:cite2:perseus:fragmentaryplays.v1:sophocles-{slug}")
        template["title"] = ((base or {}).get("source_title")
                             or (dw or {}).get("source_title") or slug)
        template["source_title"] = template["title"]
        template["cards"] = cards
        template["fragments"] = [
            card[field] for card in cards
            for field, _, _ in FIELD_ORDER if card.get(field)
        ]
        present = []
        for _, version, _ in FIELD_ORDER:
            if any(fragment.get("edition") == version for fragment in template["fragments"]):
                present.append(version)
        template["versions"] = [deepcopy(versions[v]) for v in present]
        template["line_count"] = sum(len(f.get("lines", [])) for f in template["fragments"])
        template["evidence_only"] = not bool(cards)
        template["status"] = "Fragmentary text" if cards else "Evidence only"
        works[template["id"]] = template
    return works, concordance


def aggregate_work(works, versions):
    """Build the author-level view from already play-constrained cards."""
    cards, fragments = [], []
    for work in works.values():
        fragments.extend(work.get("fragments", []))
        for card in work.get("cards", []):
            item = deepcopy(card)
            item["label"] = f"{work['work']}-{card['label']}"
            cards.append(item)
    return {
        "id": "sophocles-fragmenta", "work": "fragmenta",
        "title": "Sophocles, Fragments", "source_title": "FRAGMENTA",
        "object_urn": "urn:cts:greekLit:tlg0011.fragmenta",
        "fragments": fragments, "cards": cards, "versions": versions,
        "status": "Fragmentary text", "fragment_corpus": True,
    }


def update_registry(registry_path: Path, dindorf_path: Path) -> None:
    registry_path, dindorf_path = Path(registry_path), Path(dindorf_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source = build_dindorf(dindorf_path)
    edition = {
        "path": str(dindorf_path),
        "urn": f"urn:cts:greekLit:tlg0011.fragmenta.{DINDORF}",
        "label": "Greek (Dindorf; OCR draft)",
        "class": "greek-text", "format": "tei_fragment_collection",
        "corresp_axis": "work",
    }
    aggregate = registry["tlg0011.fragmenta"]
    aggregate.setdefault("fragment_editions", {})[DINDORF] = edition
    aggregate["source_edition"] = "multiple-fragment-editions"
    aggregate["fragment_corpus"] = True
    for work in source["works"].values():
        slug = work["work"]
        key = f"tlg0011.{slug}"
        record = registry.setdefault(key, {
            "textgroup": "tlg0011", "work": slug,
            "title": work["source_title"], "fragmentary": True,
            "record_type": work["record_type"],
            "editions": {}, "appcrits": {}, "translations": {},
            "commentaries": {}, "treebanks": {}, "fragment_editions": {},
            "object_urn": work["object_urn"],
        })
        record.setdefault("fragment_editions", {})[DINDORF] = edition
        record.setdefault("source_title", work["source_title"])
        if work["record_type"] == "fragment_collection":
            record["fragment_collection"] = True
        record["source_edition"] = "multiple-fragment-editions"
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def persist_alignments(dindorf_path: Path, concordance: list[dict]) -> int:
    """Record accepted Dindorf links in the canonical TEI as @sameAs."""
    links = {}
    for match in concordance:
        dindorf = match.get("dindorf")
        if not dindorf:
            continue
        targets = [match[field] for field in ("nauck", "pearson") if match.get(field)]
        links.setdefault(dindorf, set()).update(targets)
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
            targets = sorted(links.get(source_urn, ()))
            if targets:
                fragment.set("sameAs", " ".join(targets))
                recorded += 1
            else:
                fragment.attrib.pop("sameAs", None)
    revision = tree.xpath("//tei:revisionDesc", namespaces=NS)[0]
    change = etree.SubElement(
        revision, f"{{{NS['tei']}}}change", when="2026-10-08")
    change.text = (
        f"Recorded {recorded} conservative Dindorf correspondences to Nauck or "
        "Pearson from normalized quoted-Greek similarity; unmatched fragments remain unlinked."
    )
    tree.write(str(dindorf_path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    return recorded
