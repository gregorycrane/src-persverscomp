"""Generate portable flashcards from an authored bridge-alignment JSON file.

The bridge TEI remains the source for Amelia Parrish's English wording; the
alignment metadata supplies Greek forms and treebank morphology.  No English
text is synthesized or normalized here.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS}


def _line_index(tree):
    out = {}
    for line in tree.xpath("//tei:l", namespaces=NS):
        for seg in line.xpath(".//tei:seg[@xml:id]", namespaces={**NS, "xml": XML_NS}):
            out[seg.get(f"{{{XML_NS}}}id")] = line
    return out


def _cloze_line(line, target_ids):
    clone = deepcopy(line)
    targets = set(target_ids)
    blank_written = False
    for seg in clone.xpath(".//tei:seg[@xml:id]", namespaces={**NS, "xml": XML_NS}):
        if seg.get(f"{{{XML_NS}}}id") not in targets:
            continue
        seg.text = "[…]" if not blank_written else ""
        for child in list(seg):
            seg.remove(child)
        blank_written = True
    return "".join(clone.itertext()).strip()


def build_cards(tei_path, alignment_path):
    tree = etree.parse(str(tei_path))
    lines = _line_index(tree)
    alignment = json.loads(Path(alignment_path).read_text(encoding="utf-8"))
    alignment_meta = alignment.get("alignment_meta", {})
    target_urn = alignment_meta.get(
        "target_urn", "urn:cts:greekLit:tlg0012.tlg001.parrish2021-eng1"
    )
    work_urn = ".".join(target_urn.split(".")[:-1])
    card_prefix = alignment_meta.get("flashcard_id_prefix", "parrish-iliad1")
    cards = []
    serial = 0
    for _segment, payload in alignment.get("segments", {}).items():
        for group in payload.get("alignments", []):
            meta = group.get("meta") or {}
            target_ids = meta.get("target_ids") or []
            tokens = meta.get("tokens") or []
            line = lines.get(target_ids[0]) if target_ids else None
            if line is None or not tokens:
                continue
            serial += 1
            cards.append({
                "id": f"{card_prefix}-{serial:05d}",
                "work": work_urn,
                "passage": (meta.get("source_lines") or [None])[0],
                "front": _cloze_line(line, target_ids),
                "english_answer": " / ".join(group.get("tgt_tokens") or []),
                "cue": ", ".join(meta.get("cues") or []),
                "greek_answer": " ".join(token.get("form") or "" for token in tokens).strip(),
                "lemmas": [token.get("lemma") for token in tokens],
                "morphology": [token.get("feats") for token in tokens],
                "upos": [token.get("upos") for token in tokens],
                "dependencies": [
                    {"head": token.get("head"), "relation": token.get("deprel")}
                    for token in tokens
                ],
                "treebank_token_ids": [token.get("stable_id") for token in tokens],
                "bridge_segment_ids": target_ids,
            })
    return {
        "title": alignment_meta.get(
            "flashcard_title",
            "Iliad Book 1: Parrish–Crane English-First Bridge Flashcards",
        ),
        "source_translation": target_urn,
        "source_alignment": alignment_meta,
        "cards": cards,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("tei", type=Path)
    parser.add_argument("alignment", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    result = build_cards(args.tei, args.alignment)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result['cards'])} flashcards to {args.output}")


if __name__ == "__main__":
    main()
