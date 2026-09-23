#!/usr/bin/env python3
"""Tag recurring bibliographic citations in the Blass Eumenides commentary.

The recognizer deliberately uses citation-family regular expressions rather
than a list of literal strings. It catches changes in passage numbers and
spacing while leaving already tagged <bibl> elements alone. Run without
--write to audit matches; --write updates the TEI in place.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence, Union

from lxml import etree


TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
NS = {"tei": TEI_NS}
ROMAN_OR_ARABIC = r"(?:[IVXLCDM]+|\d+)"
FF = r"(?:\s*f{1,2}\.)?"


@dataclass(frozen=True)
class BiblSpec:
    text: str
    n: str


Chunk = Union[str, BiblSpec]
Emitter = Callable[[re.Match], Sequence[Chunk]]


@dataclass(frozen=True)
class CitationRule:
    name: str
    pattern: re.Pattern
    emit: Emitter


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _single(prefix: str | None = None, range_pair: bool = False) -> Emitter:
    def emit(match: re.Match) -> Sequence[Chunk]:
        shown = match.group(0)
        normalized = _space(shown)
        if prefix:
            normalized = _space(prefix + match.group("passage"))
        if range_pair:
            normalized = re.sub(
                r"(?P<start>\d+)\.\s*(?P<end>\d+)(?!.*\d)",
                r"\g<start>-\g<end>",
                normalized,
            )
        return [BiblSpec(shown, normalized)]

    return emit


def _pausanias_chain(match: re.Match) -> Sequence[Chunk]:
    book = match.group("book")
    first = match.group("first")
    second = match.group("second")
    return [
        BiblSpec(first, _space(first).replace("Pausanias", "Paus.")),
        match.group("sep"),
        BiblSpec(second, f"Paus. {book}, {_space(second)}"),
    ]


def _fragment_pair(match: re.Match) -> Sequence[Chunk]:
    return [
        BiblSpec(match.group("dindorf"), "Aesch. Frg. " + match.group("dnum") + " Dindorf"),
        match.group("sep"),
        BiblSpec(match.group("nauck"), "Aesch. Frg. " + match.group("nnum") + " Nauck"),
    ]


def _two_passages(match: re.Match) -> Sequence[Chunk]:
    prefix = match.group("prefix")
    first = match.group("first")
    second = match.group("second")
    return [
        BiblSpec(prefix + first, _space(prefix + first)),
        match.group("sep"),
        BiblSpec(second, _space(prefix + second)),
    ]


RULES: Sequence[CitationRule] = (
    CitationRule(
        "pausanias-inherited-book",
        re.compile(
            rf"(?P<first>Pausan(?:ias|\.)\s+(?P<book>{ROMAN_OR_ARABIC}),\s*\d+,\s*\d+)"
            rf"(?P<sep>\.\s*)(?P<second>\d+,\s*\d+{FF})"
        ),
        _pausanias_chain,
    ),
    CitationRule(
        "pausanias",
        re.compile(rf"\bPausan(?:ias|\.)\s+(?P<passage>{ROMAN_OR_ARABIC},\s*\d+,\s*\d+{FF})"),
        _single("Paus. "),
    ),
    CitationRule(
        "herodotus",
        re.compile(rf"\b(?:Herodot|Hdt\.)\s+(?P<passage>{ROMAN_OR_ARABIC},\s*\d+(?:,\s*\d+)?{FF})"),
        _single("Hdt. "),
    ),
    CitationRule(
        "euripides-iphigenia-taurica",
        re.compile(rf"\bEuripides\s+I\.\s*T\.\s+(?P<passage>\d+{FF})"),
        _single("Eur. Iph. T. "),
    ),
    CitationRule(
        "aristophanes-acharnians",
        re.compile(
            r"\b(?P<prefix>Ar\.\s+Ach\.\s+)(?P<first>\d+)"
            r"(?P<sep>\.\s+)(?P<second>\d+)"
        ),
        _two_passages,
    ),
    CitationRule(
        "aristotle-physics-diels",
        re.compile(r"\bAr\.\s+Phys\.\s+p\.\s*(?P<passage>\d+,\s*\d+\s+Diels)"),
        _single("Arist. Phys. p. "),
    ),
    CitationRule(
        "plato-laws",
        re.compile(rf"\bPlaton\s+Ges\.\s+(?P<passage>{ROMAN_OR_ARABIC},\s*\d+\s*[A-EΒ]?)"),
        _single("Plat. Leg. "),
    ),
    CitationRule(
        "phrynichus-bekker-anecdota",
        re.compile(r"\bPhrynich\.\s+Bk\.\s+An\.\s+(?P<passage>\d+)"),
        _single("Phrynich. Bk. An. "),
    ),
    CitationRule(
        "apollonius-rhodius",
        re.compile(
            rf"\b(?:Apollon(?:ios|\.)\s+Rhod\.|Apoll\.\s+Rh\.)\s+"
            rf"(?:Argon\.\s+)?(?P<passage>{ROMAN_OR_ARABIC},\s*\d+{FF})"
        ),
        _single("Apoll. Rhod. Argon. "),
    ),
    CitationRule(
        "apollonius-paired-lines",
        re.compile(r"\bApollon\.\s+(?P<passage>\d+,\s*\d+\.\s*\d+)"),
        _single("Apoll. Rhod. Argon. ", range_pair=True),
    ),
    CitationRule(
        "nicander-alexipharmaca",
        re.compile(r"\bNikandros\s+Al\.\s+(?P<passage>\d+)"),
        _single("Nicand. Alex. "),
    ),
    CitationRule(
        "aristophanes-frogs-paired-lines",
        re.compile(r"\bAr\.\s+Βάτρ\.\s+(?P<passage>\d+\.\s*\d+)"),
        _single("Ar. Ran. ", range_pair=True),
    ),
    CitationRule(
        "euripides-orestes-abbrev",
        re.compile(r"\b[ΟO]r\.\s*(?P<passage>\d+)"),
        _single("Eur. Or. "),
    ),
    CitationRule(
        "euripides-heraclidae",
        re.compile(r"\bEur\.\s+῾?Ηρακλ\.\s*μ\.\s*(?P<passage>\d+)"),
        _single("Eur. Heracl. "),
    ),
    CitationRule(
        "empedocles-diels",
        re.compile(r"\bEmpedokles\s+(?P<passage>\d+,\s*\d+\s+Diels)"),
        _single("Empedocles "),
    ),
    CitationRule(
        "aeschylus-fragment-editions",
        re.compile(
            r"(?P<dindorf>Frg\.\s*(?P<dnum>\d+)\s+Ddf\.)(?P<sep>\s*)"
            r"(?P<nauck>(?P<nnum>\d+)\s+N\.)"
        ),
        _fragment_pair,
    ),
    CitationRule(
        "aristotle-athenian-constitution",
        re.compile(
            r"\bArist(?:oteles|ot\.|\.)\s+Πολ\.\s*Αθ\.\s*"
            r"(?P<passage>(?:Col\.\s*\d+|\d+,\s*\d+))"
        ),
        _single("Arist. Ath. Pol. "),
    ),
    CitationRule(
        "aristotle-categories",
        re.compile(r"\bAristot\.\s+Kateg\.\s+(?P<passage>\d+)"),
        _single("Arist. Cat. "),
    ),
    CitationRule(
        "pindar-nemean",
        re.compile(r"\bPindar\s+N\.\s+(?P<passage>\d+,\s*\d+)"),
        _single("Pind. Nem. "),
    ),
)


def _replace_slot(text_node, chunks: Sequence[Chunk]) -> None:
    owner = text_node.getparent()
    if text_node.is_text:
        parent = owner
        insert_at = 0
        parent.text = ""
        last = None
    elif text_node.is_tail:
        parent = owner.getparent()
        insert_at = parent.index(owner) + 1
        owner.tail = ""
        last = owner
    else:
        raise ValueError("Unsupported XML text slot")

    for chunk in chunks:
        if isinstance(chunk, str):
            if last is None:
                parent.text = (parent.text or "") + chunk
            else:
                last.tail = (last.tail or "") + chunk
            continue
        node = etree.Element(f"{{{TEI_NS}}}bibl")
        node.set("n", chunk.n)
        node.text = chunk.text
        parent.insert(insert_at, node)
        insert_at += 1
        last = node


def apply_rule(tree: etree._ElementTree, rule: CitationRule) -> List[tuple]:
    changes = []
    slots = tree.xpath(
        '//tei:seg[@type="comment"]//text()[not(ancestor::tei:bibl)]',
        namespaces=NS,
    )
    for slot in slots:
        source = str(slot)
        matches = list(rule.pattern.finditer(source))
        if not matches:
            continue
        chunks: List[Chunk] = []
        cursor = 0
        for match in matches:
            chunks.append(source[cursor:match.start()])
            emitted = list(rule.emit(match))
            chunks.extend(emitted)
            seg = slot.getparent()
            while seg is not None and seg.tag != f"{{{TEI_NS}}}seg":
                seg = seg.getparent()
            changes.append((
                rule.name,
                seg.get(XML_ID) if seg is not None else None,
                match.group(0),
                [c.n for c in emitted if isinstance(c, BiblSpec)],
            ))
            cursor = match.end()
        chunks.append(source[cursor:])
        _replace_slot(slot, chunks)
    return changes


def tag_bibls(path: Path) -> tuple[etree._ElementTree, List[tuple]]:
    tree = etree.parse(str(path), etree.XMLParser(remove_blank_text=False))
    changes: List[tuple] = []
    for rule in RULES:
        changes.extend(apply_rule(tree, rule))
    return tree, changes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    tree, changes = tag_bibls(args.path)
    for rule, seg_id, shown, normalized in changes:
        print(f"{rule}\t{seg_id or '-'}\t{shown}\t=>\t{' | '.join(normalized)}")
    print(f"{len(changes)} citation match(es)")
    if args.write:
        tree.write(str(args.path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


if __name__ == "__main__":
    main()
