#!/usr/bin/env python3
"""Restore missing Storr card boundaries in Potter's Sophocles XML.

The existing alignment is retained as a set of coarse anchors.  Around every
run of missing cards, Potter lines are repartitioned with a monotonic dynamic
program that combines canonical span lengths with character-ngram similarity
to the public-domain English reference text already present in the viewer DB.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
from pathlib import Path

from lxml import etree
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


TEI = "http://www.tei-c.org/ns/1.0"
NS = {"t": TEI}
Q = lambda name: f"{{{TEI}}}{name}"


def plain_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def line_text(line: etree._Element) -> str:
    parts = [line.text or ""]
    for child in line:
        if etree.QName(child).localname != "ref":
            parts.extend(child.itertext())
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def card_start(chapter: str) -> int:
    match = re.match(r"(\d+)", chapter)
    if not match:
        raise ValueError(f"Non-numeric card: {chapter}")
    return int(match.group(1))


def card_label(urn: str) -> str:
    return urn.rsplit(":", 1)[-1].rsplit(".", 1)[0]


def canonical_card_numbers(path: Path) -> dict[str, str]:
    """Map displayed card labels to the baseline's actual milestone values."""
    root = etree.parse(str(path)).getroot()
    text = root.xpath("//t:div[@type='edition']", namespaces=NS)
    entry = text[0] if text else root.xpath("//t:body", namespaces=NS)[0]
    landmarks: list[dict[str, object]] = []
    for element in entry.iter():
        tag = etree.QName(element).localname
        if tag == "milestone" and element.get("unit") == "card":
            value = (element.get("n") or "").strip()
            if value:
                landmarks.append({"card_n": value, "lines": []})
        elif tag == "l" and landmarks:
            value = (element.get("n") or "").strip()
            match = re.match(r"^(\d+)", value)
            if match:
                landmarks[-1]["lines"].append((int(match.group(1)), value))
    result = {}
    for landmark in landmarks:
        values = landmark["lines"]
        if not values:
            continue
        first = min(values, key=lambda item: item[0])[1]
        last = max(values, key=lambda item: item[0])[1]
        result[f"{first}-{last}"] = str(landmark["card_n"])
    return result


def find_milestone(body: etree._Element, start: int) -> etree._Element | None:
    matches = body.xpath(
        f'.//t:milestone[@unit="card"][@n="{start}"]', namespaces=NS
    )
    return matches[0] if matches else None


def elements_between(
    body: etree._Element, start: etree._Element, end: etree._Element
) -> list[etree._Element]:
    elements = list(body.iter())
    left, right = elements.index(start), elements.index(end)
    return elements[left:right]


def following_line_index(
    body: etree._Element, milestone: etree._Element, line_indexes: dict[int, int]
) -> int | None:
    elements = list(body.iter())
    for element in elements[elements.index(milestone) + 1:]:
        if etree.QName(element).localname == "l":
            return line_indexes[id(element)]
    return None


def compatible_anchor_chain(
    candidates: list[tuple[int, int]], card_count: int, line_count: int
) -> list[tuple[int, int]]:
    """Return the largest ordered subset of inherited card anchors.

    The legacy Potter alignment contains a few base milestones in the wrong
    place, as well as ``cont2`` continuation milestones.  A trustworthy set
    of coarse anchors must leave at least one Potter line for every intervening
    Storr card.  Virtual document boundaries make the repair cover the whole
    play, including a bad first or final inherited anchor.
    """
    points = [(0, 0)]
    points.extend(
        (card, line)
        for card, line in candidates
        if card not in {0, card_count} and line not in {0, line_count}
    )
    points.append((card_count, line_count))
    points = sorted(set(points))
    score = [-10**9] * len(points)
    previous = [-1] * len(points)
    score[0] = 0
    for index, (card, line) in enumerate(points[1:], 1):
        for prior, (old_card, old_line) in enumerate(points[:index]):
            if line - old_line < card - old_card:
                continue
            candidate_score = score[prior] + (0 if card == card_count else 1)
            if candidate_score > score[index]:
                score[index] = candidate_score
                previous[index] = prior
    cursor = len(points) - 1
    if score[cursor] < 0:
        raise RuntimeError("Could not construct an ordered Potter anchor chain")
    chain = []
    while cursor >= 0:
        chain.append(points[cursor])
        cursor = previous[cursor]
    return list(reversed(chain))


def partition_lines(
    texts: list[str], references: list[str], widths: list[int]
) -> tuple[list[int], list[float]]:
    """Return start offsets for cards after the first and per-card similarity."""
    line_count, card_count = len(texts), len(references)
    if line_count < card_count:
        raise RuntimeError(f"Only {line_count} Potter lines for {card_count} cards")

    corpus = references + texts
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), lowercase=True, min_df=1
    )
    matrix = vectorizer.fit_transform(corpus)
    ref_matrix = matrix[:card_count]
    line_matrix = matrix[card_count:]
    similarity = cosine_similarity(line_matrix, ref_matrix)
    prefixes = [[0.0] for _ in range(card_count)]
    for card in range(card_count):
        for value in similarity[:, card]:
            prefixes[card].append(prefixes[card][-1] + float(value))

    total_width = sum(widths)
    expected = [line_count * width / total_width for width in widths]
    # DP[card][end] = (score, previous_end). Every card receives >=1 line.
    dp = [{0: (0.0, None)}]
    for card in range(card_count):
        current = {}
        remaining_cards = card_count - card - 1
        for begin, (base_score, _) in dp[-1].items():
            min_end = begin + 1
            max_end = line_count - remaining_cards
            ideal = expected[card]
            # Length prior is deliberately stronger than lexical similarity;
            # it prevents an archaic wording mismatch from swallowing a card.
            for end in range(min_end, max_end + 1):
                length = end - begin
                lexical = prefixes[card][end] - prefixes[card][begin]
                penalty = 0.10 * ((length - ideal) ** 2) / max(ideal, 1.0)
                score = base_score + lexical - penalty
                if end not in current or score > current[end][0]:
                    current[end] = (score, begin)
        dp.append(current)

    end = line_count
    bounds = [line_count]
    for card in range(card_count, 0, -1):
        _, begin = dp[card][end]
        assert begin is not None
        bounds.append(begin)
        end = begin
    bounds.reverse()
    starts = bounds[1:-1]
    similarities = []
    for card, (begin, end) in enumerate(zip(bounds[:-1], bounds[1:])):
        similarities.append(
            round((prefixes[card][end] - prefixes[card][begin]) / max(end - begin, 1), 4)
        )
    return starts, similarities


def repair(
    xml_path: Path, baseline_path: Path, db_path: Path, output: Path, audit_path: Path
) -> None:
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    body = root.xpath("//t:body", namespaces=NS)[0]

    connection = sqlite3.connect(db_path)
    grid_rows = connection.execute(
        "SELECT passage_urn, chapter FROM alignment_grid ORDER BY sort_order"
    ).fetchall()
    canonical_numbers = canonical_card_numbers(baseline_path)
    cards = []
    for urn, chapter in grid_rows:
        if chapter not in canonical_numbers:
            raise RuntimeError(f"No baseline milestone found for card {chapter}")
        cards.append({
            "urn": urn,
            "chapter": chapter,
            "start": card_start(chapter),
            "card_n": canonical_numbers[chapter],
        })
    potter_urns = {
        row[0]
        for row in connection.execute(
            "SELECT passage_urn FROM text_segments WHERE version_short_id='potter1788-eng1'"
        )
    }
    reference_ids = [
        row[0]
        for row in connection.execute(
            """SELECT DISTINCT version_short_id FROM text_segments
               WHERE version_short_id != 'potter1788-eng1'
                 AND version_short_id NOT LIKE '%-com-%'
                 AND (version_short_id LIKE '%-eng1'
                      OR version_short_id LIKE '%-eng2'
                      OR version_short_id LIKE '%-eng3')"""
        )
    ]
    reference_html: dict[str, str] = {}
    if reference_ids:
        placeholders = ",".join("?" for _ in reference_ids)
        for urn, content in connection.execute(
            f"SELECT passage_urn, content_html FROM text_segments "
            f"WHERE version_short_id IN ({placeholders})",
            reference_ids,
        ):
            reference_html[urn] = reference_html.get(urn, "") + " " + (content or "")
    connection.close()

    present = [card["urn"] in potter_urns for card in cards]
    lines = body.xpath(".//t:l", namespaces=NS)
    line_indexes = {id(line): index for index, line in enumerate(lines)}
    inherited_candidates = []
    for index, card in enumerate(cards):
        milestone = find_milestone(body, card["card_n"])
        if milestone is None:
            continue
        line_index = following_line_index(body, milestone, line_indexes)
        if line_index is not None:
            inherited_candidates.append((index, line_index))
    anchor_chain = compatible_anchor_chain(
        inherited_candidates, len(cards), len(lines)
    )
    audit_zones = []

    boundaries = {0: 0}
    for (start_index, start_line), (end_index, end_line) in zip(
        anchor_chain[:-1], anchor_chain[1:]
    ):
        zone_cards = cards[start_index:end_index]
        zone_lines = lines[start_line:end_line]
        texts = [line_text(line) for line in zone_lines]
        references = [plain_html(reference_html.get(card["urn"], "")) for card in zone_cards]
        widths = []
        for card in zone_cards:
            numbers = [int(value) for value in re.findall(r"\d+", card["chapter"])]
            widths.append(max(1, numbers[-1] - numbers[0] + 1))
        starts, similarities = partition_lines(texts, references, widths)
        placed = []
        for card, offset in zip(zone_cards[1:], starts):
            absolute_offset = start_line + offset
            card_index = cards.index(card)
            boundaries[card_index] = absolute_offset
            placed.append({
                "card": card_label(card["urn"]),
                "before_line_n": lines[absolute_offset].get("n"),
                "before_text": line_text(lines[absolute_offset]),
                "offset": absolute_offset,
            })
        boundaries[end_index] = end_line
        audit_zones.append({
            "cards": [card_label(card["urn"]) for card in zone_cards],
            "line_count": len(zone_lines),
            "expected_line_counts": [round(len(zone_lines) * width / sum(widths), 2) for width in widths],
            "mean_similarity": similarities,
            "placed_boundaries": placed,
        })

    # Replace every numeric base milestone with one complete monotonic set.
    # Keep legacy continuation milestones (e.g. 251cont2) as documentary
    # evidence; the parser ignores them because they are not master cards.
    for milestone in list(body.xpath('.//t:milestone[@unit="card"]', namespaces=NS)):
        if (milestone.get("n") or "").isdigit():
            milestone.getparent().remove(milestone)
    for card_index in reversed(range(len(cards))):
        line_index = boundaries[card_index]
        milestone = etree.Element(
            Q("milestone"), unit="card", n=str(cards[card_index]["card_n"]), edRef="Storr"
        )
        lines[line_index].addprevious(milestone)

    revision = root.find(".//t:revisionDesc", namespaces=NS)
    if revision is not None:
        change = etree.SubElement(revision, Q("change"), when="2026-10-06", who="#gcrane")
        change.text = (
            "Restored missing Storr card boundaries in Potter's translation using "
            "the canonical grid, neighboring alignment anchors, and English-reference similarity."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    audit = {
        "source": str(xml_path),
        "baseline": str(baseline_path),
        "database": str(db_path),
        "reference_versions": reference_ids,
        "missing_before": [card_label(cards[i]["urn"]) for i, value in enumerate(present) if not value],
        "inherited_anchor_count": len(inherited_candidates),
        "retained_anchor_count": len(anchor_chain) - 2,
        "retained_anchor_cards": [card_label(cards[index]["urn"]) for index, _ in anchor_chain[1:-1]],
        "zones": audit_zones,
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("db", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("audit", type=Path)
    args = parser.parse_args()
    repair(args.xml, args.baseline, args.db, args.output, args.audit)


if __name__ == "__main__":
    main()
