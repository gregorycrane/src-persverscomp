"""Reconcile Beowulf CoNLL-U lemmas with Klaeber's glossary headwords.

The treebank is provisional; Klaeber is the authority.  This module changes
only lemma column 3 and deliberately leaves punctuation, fragments, multiword
analyses, and unresolved homographs for human review.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.lexicon.parsers import (
    TEI_NS,
    XML_ID,
    _klaeber_orth_variants,
    _klaeber_variant_keys,
    safe_parse_lexicon,
)
from pipeline.treebank.norm_key import norm_key


DEFAULT_GLOSSARY = Path(
    "/Users/gcrane/github/canonical-angLit/data/anon/klaeber_glossary/"
    "anon.klaeber_glossary.perseus-mul1.xml"
)
DEFAULT_TREEBANK = Path(
    "/Users/gcrane/github/canonical-angLit/data/anon/beowulf/"
    "anon.beowulf.brunetti-deepseek2026-tb-ang1.conllu"
)

# Cases in which one spelling indexes genuinely different Klaeber entries.
# These choices use the treebank POS only where it identifies the lexeme.
POS_OVERRIDES = {
    ("þæt", "DET"): "sē",
    ("þæt", "CCONJ"): "þæt",
    ("þa", "ADV"): "þā",
    ("þa", "CCONJ"): "þā",
    ("þe", "ADV"): "þē",
    ("þe", "CCONJ"): "þē",
    ("ofer", "ADP"): "ofer",
    ("ofer", "NOUN"): "ōfer",
    ("æt", "ADP"): "æt",
    ("æt", "NOUN"): "ǣt",
    ("min", "PRON"): "mīn",
    ("an", "ADJ"): "ān",
    ("god", "ADJ"): "gōd",
    ("god", "NOUN"): "gōd",
    ("God", "PROPN"): "God",
    ("mæg", "NOUN"): "mǣg",
    ("ge", "PRON"): "þū",
    ("ge", "CCONJ"): "gē",
    ("wit", "PRON"): "ic",
    ("wit", "NOUN"): "wit",
    ("git", "PRON"): "þū",
    ("hwæt", "PRON"): "hwā",
    ("hwæt", "INTJ"): "hwæt",
    ("hwæt", "ADJ"): "hwæt",
    ("no", "ADV"): "nō",
    ("nō", "ADV"): "nō",
    ("Heorot", "PROPN"): "Heorot",
    ("heorot", "NOUN"): "heorot",
    ("Scyld", "PROPN"): "Scyld",
    ("scyld", "NOUN"): "scyld",
}

LEMMA_OVERRIDES = {
    ("wesan", "VERB"): "eom",
    ("beon", "VERB"): "eom",
    ("heo", "PRON"): "hē",
    ("hit", "PRON"): "hē",
    ("we", "PRON"): "ic",
}


def _entry_text(entry):
    return " ".join("".join(entry.itertext()).split())


def build_klaeber_index(path=DEFAULT_GLOSSARY):
    """Return normalized lookup key -> authoritative Klaeber headwords."""
    root = safe_parse_lexicon(path).getroot()
    records = {}
    index = defaultdict(set)

    for entry in root.iter(f"{TEI_NS}entryFree"):
        entry_id = entry.get(XML_ID) or (entry.get("n") or "").strip()
        orths = [
            "".join(orth.itertext()).strip()
            for orth in entry.findall(f"{TEI_NS}orth")
            if "".join(orth.itertext()).strip()
        ]
        if not entry_id or not orths:
            continue
        variants = list(dict.fromkeys(
            variant for orth in orths for variant in _klaeber_orth_variants(orth)
        ))
        if not variants:
            continue
        refs = list(entry.iter(f"{TEI_NS}ref"))
        pointer = ""
        if len(refs) == 1 and len(_entry_text(entry)) < 100:
            pointer = "".join(refs[0].itertext()).strip()
        records[entry_id] = {"canonical": variants[0], "pointer": pointer}
        for variant in variants:
            for key in _klaeber_variant_keys(variant):
                if key:
                    index[key].add(entry_id)

    def resolve(entry_id, seen=None):
        seen = set() if seen is None else seen
        if entry_id in seen:
            return entry_id
        seen.add(entry_id)
        pointer = records[entry_id]["pointer"]
        if not pointer:
            return entry_id
        candidates = set()
        for key in _klaeber_variant_keys(pointer):
            candidates.update(index.get(key, ()))
        # Ignore the pointer entry itself; a unique remaining target is the
        # substantive article (e.g. sēo, see sē).
        candidates.discard(entry_id)
        if len(candidates) == 1:
            return resolve(next(iter(candidates)), seen)
        return entry_id

    result = defaultdict(set)
    for key, entry_ids in index.items():
        for entry_id in entry_ids:
            canonical = records[resolve(entry_id)]["canonical"]
            if canonical.isupper():
                canonical = canonical.lower()
            result[key].add(canonical)
    return result


def _misc_value(misc, key):
    prefix = key + "="
    for field in misc.split("|"):
        if field.startswith(prefix):
            return field[len(prefix):]
    return ""


def _orthographic_skeleton(value):
    value = unicodedata.normalize("NFD", value.casefold())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[-\s]", "", value)


def authoritative_lemma(lemma, upos, misc, index):
    """Return (replacement, reason), or (None, reason) when not automatic."""
    if upos in {"PUNCT", "X"} or not lemma or " " in lemma:
        return None, "excluded"

    # Klaeber distinguishes these two homographic verbs; the provisional
    # gloss supplies the semantic distinction without inference from form.
    gloss = (_misc_value(misc, "gloss") or
             _misc_value(misc, "BrunettiGloss")).lower()
    if norm_key(lemma) == "gewitan" and gloss in {"go", "went", "depart", "departed"}:
        return "ge-wītan", "gloss"
    if norm_key(lemma) == "witan" and gloss in {"know", "knew"}:
        return "witan", "gloss"

    override = POS_OVERRIDES.get((lemma, upos)) or LEMMA_OVERRIDES.get((lemma, upos))
    candidates = set(index.get(norm_key(lemma), ()))
    if override:
        if override in candidates or norm_key(override) == norm_key(lemma):
            return override, "pos"
        return None, "override-not-in-klaeber"
    if len(candidates) == 1:
        candidate = next(iter(candidates))
        # Exact spelling, macrons, case, and editorial compound hyphens are
        # safe to normalize automatically. A different lexical stem may be a
        # cross-reference or homograph and therefore stays in the review list.
        if _orthographic_skeleton(candidate) == _orthographic_skeleton(lemma):
            return candidate, "unique"
        return None, "lexical-review"
    return None, "unmatched" if not candidates else "ambiguous"


def reconcile_conllu(text, index):
    output = []
    stats = Counter()
    unresolved = Counter()
    changes = Counter()
    for line in text.splitlines(keepends=True):
        if not line.strip() or line.startswith("#"):
            output.append(line)
            continue
        ending = "\n" if line.endswith("\n") else ""
        columns = line.rstrip("\n").split("\t")
        if len(columns) < 10 or "-" in columns[0] or "." in columns[0]:
            output.append(line)
            continue
        old = columns[2]
        replacement, reason = authoritative_lemma(old, columns[3], columns[9], index)
        stats[reason] += 1
        if replacement is None:
            if reason in {"ambiguous", "unmatched", "lexical-review"}:
                unresolved[(old, columns[3], reason)] += 1
        elif replacement != old:
            columns[2] = replacement
            changes[(old, replacement)] += 1
            stats["changed"] += 1
        output.append("\t".join(columns) + ending)
    report = {
        "stats": dict(sorted(stats.items())),
        "changes": [
            {"from": old, "to": new, "tokens": count}
            for (old, new), count in changes.most_common()
        ],
        "unresolved": [
            {"lemma": lemma, "upos": upos, "reason": reason, "tokens": count}
            for (lemma, upos, reason), count in unresolved.most_common()
        ],
    }
    return "".join(output), report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--treebank", type=Path, default=DEFAULT_TREEBANK)
    parser.add_argument("--write", action="store_true",
                        help="replace the treebank after producing the report")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    index = build_klaeber_index(args.glossary)
    original = args.treebank.read_text(encoding="utf-8")
    reconciled, report = reconcile_conllu(original, index)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    if args.write and reconciled != original:
        args.treebank.write_text(reconciled, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
