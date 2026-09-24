"""Build the exploratory Greek word dashboard shipped with PMV.

The dashboard is deliberately a *sample* and deliberately keeps annotation
layers separate.  GLAUx, OGA, and Daphne overlap substantially; adding their
token counts would turn alternate analyses of the same text into fake corpus
frequency.  The browser therefore selects one layer at a time (GLAUx is the
default textual-frequency layer) and offers the others for comparison.

Run with ``python -m pipeline.word_dashboard``.  The generated public JSON is
written under ``web/``; index_builder copies it and the dashboard assets to the
published PMV root on the next ``make index``.
"""

from __future__ import annotations

import argparse
import collections as C
import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from pipeline.config import SRC_DIR


CORPUS_ROOT = Path("/Users/gcrane/github")
WEB_DIR = SRC_DIR / "web"
PILOT_LEMMAS = ("λόγος", "ἔργον", "λέγω", "φέρω", "δίκη", "θυμός", "ἐν")
GLAUX_WORKS = (
    "0012-001", "0011-002", "0019-001", "0059-003", "0003-001",
    "0086-034", "0057-001", "0527-001", "0031-001",
)
DAPHNE_WORKS = ("0012-001", "0011-002", "0020-001", "0006-003", "0085-005")
POETRY_GENRES = {"Epic poetry", "Tragedy", "Comedy"}
SOURCE_INFO = {
    "glaux": {
        "label": "GLAUx",
        "scheme": "AGDT XML",
        "role": "Curated/automatic control layer",
        "note": "A mixed curated/automatic layer with sentence-level provenance.",
    },
    "oga": {
        "label": "OGA",
        "scheme": "AGDT-style CoNLL-U",
        "role": "Primary production corpus",
        "note": "Automatically generated analyses; intended to scale to the complete OGA corpus.",
    },
    "daphne": {
        "label": "Daphne",
        "scheme": "Universal Dependencies",
        "role": "Curated UD comparison layer",
        "note": "Curated UD analyses; labels are not silently equated with AGDT labels.",
    },
}


def nfc(value: str | None) -> str:
    return unicodedata.normalize("NFC", value or "")


def top(counter: C.Counter, limit: int = 12) -> list[dict]:
    return [{"label": key, "count": value} for key, value in counter.most_common(limit)]


def parse_misc(value: str) -> dict[str, str]:
    result = {}
    for item in value.split("|"):
        if "=" in item:
            key, val = item.split("=", 1)
            result[key.lower()] = val
    return result


def conllu_sentences(path: Path):
    comments: dict[str, str] = {}
    tokens: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if not line.strip():
            if tokens:
                yield comments, tokens
            comments, tokens = {}, []
            continue
        if line.startswith("#"):
            if "=" in line:
                key, value = line[1:].split("=", 1)
                comments[key.strip().lower()] = value.strip()
            continue
        cols = line.split("\t")
        if len(cols) != 10 or not cols[0].isdigit():
            continue
        misc = parse_misc(cols[9])
        artificial = bool(re.match(r"e_\d+\|", cols[9])) or cols[1] in {
            "E", "[0]", "[1]", "[2]", "[3]", "[4]"
        }
        tokens.append({
            "id": cols[0], "form": nfc(cols[1]), "lemma": nfc(cols[2]),
            "pos": cols[3], "xpos": cols[4], "feats": cols[5],
            "head": cols[6], "rel": cols[7], "misc": misc,
            "punct": cols[3] in {"u", "PUNCT"}, "artificial": artificial,
        })


def glaux_sentences(path: Path):
    for _event, element in ET.iterparse(path, events=("end",)):
        if element.tag != "sentence":
            continue
        tokens = []
        for word in element.findall("word"):
            attrs = word.attrib
            tokens.append({
                "id": attrs.get("id", ""), "form": nfc(attrs.get("form")),
                "lemma": nfc(attrs.get("lemma")), "pos": attrs.get("postag", "")[:1],
                "xpos": attrs.get("postag", ""), "feats": "",
                "head": attrs.get("head", ""), "rel": attrs.get("relation", ""),
                "misc": {key.lower(): value for key, value in attrs.items()},
                "punct": attrs.get("postag", "").startswith("u"),
                "artificial": bool(attrs.get("artificial")),
            })
        yield {key.lower(): value for key, value in element.attrib.items()}, tokens
        element.clear()


def evenly_spaced(sentences, cap: int = 500):
    sentences = list(sentences)
    if len(sentences) <= cap:
        return sentences
    return [sentences[(index * len(sentences)) // cap] for index in range(cap)]


def metadata_by_work() -> dict[str, dict]:
    path = CORPUS_ROOT / "glaux" / "metadata.txt"
    with path.open(encoding="utf-8") as handle:
        return {row["TLG"]: row for row in csv.DictReader(handle, delimiter="\t")}


def work_urn(work: str) -> str:
    textgroup, text = work.split("-")
    return f"tlg{textgroup}.tlg{text}"


def work_info(work: str, metadata: dict[str, dict]) -> dict:
    row = metadata.get(work, {})
    genre = row.get("GENRE_STANDARD", "Unknown") or "Unknown"
    return {
        "id": work,
        "urn": work_urn(work),
        "author": row.get("AUTHOR_STANDARD", work),
        "title": row.get("TITLE_STANDARD", work),
        "genre": genre,
        "register": "Poetry" if genre in POETRY_GENRES else "Prose",
        "dialect": row.get("DIALECT", "Unknown") or "Unknown",
        "start": row.get("STARTDATA", ""),
        "end": row.get("ENDDATE", ""),
    }


def reference_for(tokens: list[dict], comments: dict) -> str:
    for token in tokens:
        misc = token["misc"]
        for key in ("line", "div_stephanus_section", "div_perseus_section", "ref"):
            if misc.get(key):
                value = misc[key]
                if key == "ref" and "_" in value:
                    value = value.rsplit("_", 1)[-1]
                return value
    source = comments.get("source", "")
    if "_" in source:
        return source.rsplit("_", 1)[-1]
    return comments.get("sent_id", comments.get("id", ""))


def source_path(source_id: str, work: str) -> Path | None:
    textgroup, text = work.split("-")
    if source_id == "glaux":
        return CORPUS_ROOT / "glaux" / "xml" / f"{work}.xml"
    if source_id == "oga":
        candidates = sorted((CORPUS_ROOT / "oga_src" / "data").glob(
            f"tlg{textgroup}.tlg{text}.*_oga020_src.conllu"
        ))
        candidates = [path for path in candidates if ".glossed." not in path.name]
        return candidates[0] if candidates else None
    candidates = sorted((CORPUS_ROOT / "Daphne" / "data" / "annotation" / "latest").glob(
        f"**/tlg{textgroup}.tlg{text}.daphne_tb-grc1*.conllu"
    ))
    candidates = [path for path in candidates if "gloss" not in path.name and "bak" not in path.name]
    return candidates[0] if candidates else None


def empty_lemma() -> dict:
    return {
        "occurrences": 0,
        "forms": C.Counter(), "pos": C.Counter(), "features": C.Counter(),
        "relations": C.Counter(), "heads": C.Counter(), "dependents": C.Counter(),
        "genres": C.Counter(), "registers": C.Counter(), "works": C.Counter(),
        "dialects": C.Counter(), "provenance": C.Counter(), "examples": [],
        "example_work_counts": C.Counter(),
    }


def collect_layer(source_id: str, works: tuple[str, ...], metadata: dict[str, dict]) -> dict:
    totals = C.Counter()
    register_totals = C.Counter()
    genre_totals = C.Counter()
    file_count = sentence_count = 0
    lemmas = {lemma: empty_lemma() for lemma in PILOT_LEMMAS}
    work_rows = []

    for work in works:
        path = source_path(source_id, work)
        if path is None or not path.exists():
            continue
        info = work_info(work, metadata)
        parser = glaux_sentences if source_id == "glaux" else conllu_sentences
        sample = evenly_spaced(parser(path))
        file_count += 1
        sentence_count += len(sample)
        work_words = 0
        work_hits = C.Counter()
        for comments, tokens in sample:
            by_id = {token["id"]: token for token in tokens}
            analysis = comments.get("analysis", "curated" if source_id == "daphne" else "automatic")
            for index, token in enumerate(tokens):
                if token["punct"] or token["artificial"]:
                    continue
                work_words += 1
                totals["words"] += 1
                register_totals[info["register"]] += 1
                genre_totals[info["genre"]] += 1
                lemma = token["lemma"]
                if lemma not in lemmas:
                    continue
                item = lemmas[lemma]
                item["occurrences"] += 1
                work_hits[lemma] += 1
                item["forms"][token["form"]] += 1
                item["pos"][token["pos"] or "unknown"] += 1
                item["relations"][token["rel"] or "unknown"] += 1
                item["genres"][info["genre"]] += 1
                item["registers"][info["register"]] += 1
                item["works"][work] += 1
                item["dialects"][info["dialect"]] += 1
                item["provenance"][analysis] += 1
                if token["feats"] and token["feats"] != "_":
                    for feature in token["feats"].split("|"):
                        item["features"][feature] += 1
                elif token["xpos"]:
                    item["features"][f"tag:{token['xpos']}"] += 1
                head = by_id.get(token["head"])
                if head and not head["punct"] and not head["artificial"]:
                    item["heads"][head["lemma"] or head["form"]] += 1
                for child in tokens:
                    if child["head"] == token["id"] and not child["punct"] and not child["artificial"]:
                        item["dependents"][f"{child['rel']} · {child['lemma'] or child['form']}"] += 1
                if item["example_work_counts"][work] < 2 and len(item["examples"]) < 24:
                    ref = reference_for(tokens, comments)
                    item["examples"].append({
                        "work": work, "urn": info["urn"], "author": info["author"],
                        "title": info["title"], "genre": info["genre"], "register": info["register"],
                        "reference": ref, "sentence": " ".join(part["form"] for part in tokens),
                        "token_index": index, "form": token["form"], "relation": token["rel"],
                        "analysis": analysis,
                    })
                    item["example_work_counts"][work] += 1
        work_rows.append({**info, "tokens": work_words, "hits": dict(work_hits)})

    for lemma, item in lemmas.items():
        item["distinct_forms"] = len(item["forms"])
        item["rate"] = round(10000 * item["occurrences"] / totals["words"], 2) if totals["words"] else 0
        item["register_detail"] = []
        for register in ("Poetry", "Prose"):
            count = item["registers"][register]
            denominator = register_totals[register]
            item["register_detail"].append({
                "label": register, "count": count, "tokens": denominator,
                "rate": round(10000 * count / denominator, 2) if denominator else 0,
            })
        for field in ("forms", "pos", "features", "relations", "heads", "dependents",
                      "genres", "registers", "works", "dialects", "provenance"):
            item[field] = top(item[field])
        item.pop("example_work_counts", None)

    return {
        **SOURCE_INFO[source_id],
        "id": source_id, "files": file_count, "sentences": sentence_count,
        "tokens": totals["words"], "register_tokens": dict(register_totals),
        "genre_tokens": dict(genre_totals), "works": work_rows, "lemmas": lemmas,
    }


def collect_gloss_evidence() -> dict[str, dict]:
    paths = [
        ("OGA · Plato, Crito", CORPUS_ROOT / "oga_src" / "data" /
         "tlg0059.tlg003.perseus-grc2_oga020_src.glossed.conllu"),
        ("Daphne · Sophocles, Antigone", CORPUS_ROOT / "Daphne" / "data" /
         "annotation" / "latest" / "tlg0011" / "tlg002" /
         "tlg0011.tlg002.daphne_tb-grc1.glossed.conllu"),
    ]
    evidence = {lemma: {"glosses": C.Counter(), "sources": C.Counter()} for lemma in PILOT_LEMMAS}
    for label, path in paths:
        if not path.exists():
            continue
        for _comments, tokens in conllu_sentences(path):
            for token in tokens:
                if token["lemma"] in evidence and token["misc"].get("gloss"):
                    gloss = token["misc"]["gloss"].replace("-", " ")
                    evidence[token["lemma"]]["glosses"][gloss] += 1
                    evidence[token["lemma"]]["sources"][label] += 1
    return {
        lemma: {
            "status": "Gloss evidence only — no reviewed token-level sense IDs were found",
            "glosses": top(item["glosses"], 15),
            "sources": top(item["sources"], 5),
        }
        for lemma, item in evidence.items()
    }


def reliability_summary(primary: dict, control: dict) -> dict:
    """Compare rates on shared sampled works without pretending this is token agreement.

    A real token-level error estimate requires an explicit occurrence crosswalk.
    These rate deltas are useful smoke tests and are labelled as such in the UI.
    """
    primary_works = {row["id"]: row for row in primary["works"]}
    control_works = {row["id"]: row for row in control["works"]}
    shared = sorted(primary_works.keys() & control_works.keys())
    rows = []
    for lemma in PILOT_LEMMAS:
        primary_count = sum(primary_works[work]["hits"].get(lemma, 0) for work in shared)
        control_count = sum(control_works[work]["hits"].get(lemma, 0) for work in shared)
        primary_tokens = sum(primary_works[work]["tokens"] for work in shared)
        control_tokens = sum(control_works[work]["tokens"] for work in shared)
        primary_rate = 10000 * primary_count / primary_tokens if primary_tokens else 0
        control_rate = 10000 * control_count / control_tokens if control_tokens else 0
        delta = primary_rate - control_rate
        rows.append({
            "lemma": lemma,
            "primary_count": primary_count,
            "control_count": control_count,
            "primary_rate": round(primary_rate, 2),
            "control_rate": round(control_rate, 2),
            "rate_delta": round(delta, 2),
            "relative_delta_percent": round(100 * delta / control_rate, 1) if control_rate else None,
        })
    return {
        "control": control["id"],
        "shared_works": shared,
        "rows": rows,
        "interpretation": (
            "Rate differences over shared sampled works are triage signals, not an accuracy score. "
            "Token-level lemma, morphology, and dependency agreement requires a reviewed occurrence crosswalk."
        ),
    }


def build() -> dict:
    metadata = metadata_by_work()
    oga_works = tuple(dict.fromkeys((*GLAUX_WORKS, *DAPHNE_WORKS)))
    layers = {
        "glaux": collect_layer("glaux", GLAUX_WORKS, metadata),
        "oga": collect_layer("oga", oga_works, metadata),
        "daphne": collect_layer("daphne", DAPHNE_WORKS, metadata),
    }
    inventory = {
        "glaux_files": len(list((CORPUS_ROOT / "glaux" / "xml").glob("*.xml"))),
        "oga_files": len(list((CORPUS_ROOT / "oga_src" / "data").glob("*.conllu"))),
        "daphne_latest_files": len(list((CORPUS_ROOT / "Daphne" / "data" / "annotation" / "latest").glob("**/*.conllu"))),
    }
    return {
        "generated": date.today().isoformat(),
        "title": "Greek word explorer",
        "subtitle": "A provenance-aware pilot over GLAUx, OGA, and Daphne",
        "method": (
            "Up to 500 evenly spaced sentences per selected file. Counts exclude punctuation "
            "and recognized artificial nodes. Rates are occurrences per 10,000 sampled words."
        ),
        "warning": (
            "This is an exploratory sample, not a corpus-wide estimate. Choose one annotation "
            "layer at a time: overlapping layers are not added together."
        ),
        "production_goal": (
            "Compute the dashboard over the complete OGA corpus, using GLAUx and Daphne as "
            "controls to estimate where automatic lemmas, morphology, and dependencies deviate."
        ),
        "pilot_lemmas": list(PILOT_LEMMAS),
        "inventory": inventory,
        "layers": layers,
        "reliability": [
            reliability_summary(layers["oga"], layers["glaux"]),
            reliability_summary(layers["oga"], layers["daphne"]),
        ],
        "sense_evidence": collect_gloss_evidence(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WEB_DIR / "word-dashboard-data.json")
    args = parser.parse_args(argv)
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output} ({args.output.stat().st_size:,} bytes): "
        + ", ".join(f"{key}={layer['tokens']:,} tokens" for key, layer in payload["layers"].items())
    )


if __name__ == "__main__":
    main()
