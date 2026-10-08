"""Combine Pearson's and Nauck's Sophoclean fragments without conflating numbers.

The two editions number fragments independently.  A shared PMV card is therefore
created only when the quoted Greek supplies positive evidence for equivalence.
Exact normalized matches are accepted; a conservative mutual-best comparison is
used for small editorial/OCR differences.  Unmatched fragments remain visible as
edition-specific cards.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
import re
import unicodedata


PEARSON = "pearson1917-grc1"
NAUCK = "nauck1889grc1"

# Only unambiguous title variants are collapsed here.  Composite headings such
# as Nauck's ACHAION SYLLOGOS E SYNDEIPNOI remain separate until an editor says
# how the individual play attributions should be distributed.
NAUCK_WORK_ALIASES = {
    "athamas_a_et_b": "athamas_a_kai_b",
    "dionysiakos_satyrikos": "dionysiskos_satyrikos",
    "erakles_epi_tainaroi_satyrikos": "erakles_epi_tainaroi_satyroi_erakleiskos",
    "inachos_satyrikos": "inachos",
    "iokles": "oikles",
    "kedalion_satyrikos": "kedalion",
    "kophoi_satyroi": "kophoi",
    "krisis_satyrike": "krisis",
    "manteis_e_polyidos": "manteis",
    "momos_matyrikos": "momos",
    "naysikaa_e_plyntriai": "naysikaa",
    "odysseys_akanthoplex_e_niptra": "odysseys_akanthoplex",
    "oinomaos_e_ippodameia": "oinomaos",
    "pandora_e_sphyrokopoi": "pandora",
    "philoktetes_o_en_troiai": "philoktetes",
    "phineys_a_et_b": "phineys",
    "pizotomoi": "rizotomoi",
    "salmoneys_satyrikos": "salmoneys",
    "skyphai": "skythai",
    "telephos_satyrikos": "telephos",
    "thyestes_en_sikyoni_et_thyestes_deyteros": "thyestes_en_sikyoni",
    "tyro_a_et_b": "tyro",
    "ybris_satyrike": "ybris",
}


MIXED_OCR = str.maketrans({
    "a": "α", "b": "β", "e": "ε", "i": "ι", "k": "κ", "m": "μ",
    "n": "ν", "o": "ο", "p": "ρ", "s": "σ", "t": "τ", "x": "χ",
})


def normalized_tokens(text):
    text = unicodedata.normalize("NFD", text).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    tokens = []
    for token in re.findall(r"[^\W\d_]+", text, re.UNICODE):
        if re.search(r"[\u0370-\u03ff]", token):
            token = token.translate(MIXED_OCR)
        tokens.append(token)
    return tokens


def normalized_text(text):
    return "".join(normalized_tokens(text))


def normalized_greek(fragment):
    return normalized_text(" ".join(
        line.get("text", "") for line in fragment.get("lines", [])))


def normalized_context(fragment):
    return normalized_text(fragment.get("context", ""))


def fragment_similarity(left, right):
    """Compare quoted lines, falling back to quotation-in-context evidence."""
    left_text, right_text = normalized_greek(left), normalized_greek(right)
    score, method = 0.0, None
    if len(left_text) >= 5 and len(right_text) >= 5:
        score = SequenceMatcher(None, left_text, right_text).ratio()
        method = "mutual-best-normalized-greek"
    left_context, right_context = normalized_context(left), normalized_context(right)
    if len(left_text) >= 5 and left_text in right_context and score < 0.995:
        score, method = 0.995, "quoted-text-in-source-context"
    if len(right_text) >= 5 and right_text in left_context and score < 0.995:
        score, method = 0.995, "quoted-text-in-source-context"
    # Lexicographical fragments may differ by one OCR/editorial character
    # (e.g. ἐμπλεύρου / ἐμπεύρου). Compare a short quoted lemma with each
    # token in the other edition's source discussion, still subject to the
    # mutual-best and margin checks in align_fragments.
    for quote, context_fragment in ((left_text, right), (right_text, left)):
        if not 5 <= len(quote) <= 30:
            continue
        for token in normalized_tokens(context_fragment.get("context", "")):
            if not 0.6 * len(quote) <= len(token) <= 1.4 * len(quote):
                continue
            candidate = SequenceMatcher(None, quote, token).ratio()
            if candidate > score:
                score, method = candidate, "fuzzy-quoted-text-in-source-context"
    return score, method


def _unique_exact(pearson, nauck):
    left, right = defaultdict(list), defaultdict(list)
    for fragment in pearson:
        left[normalized_greek(fragment)].append(fragment)
    for fragment in nauck:
        right[normalized_greek(fragment)].append(fragment)
    pairs = []
    for text, candidates in left.items():
        if len(text) >= 8 and len(candidates) == 1 and len(right.get(text, [])) == 1:
            pairs.append((candidates[0], right[text][0], 1.0, "exact-normalized-greek"))
    return pairs


def align_fragments(pearson, nauck, fuzzy=True):
    """Return defensible one-to-one fragment pairs for a single play view."""
    pairs = _unique_exact(pearson, nauck)
    used_p = {id(pair[0]) for pair in pairs}
    used_n = {id(pair[1]) for pair in pairs}
    if not fuzzy:
        return pairs
    remaining_p = [f for f in pearson if id(f) not in used_p]
    remaining_n = [f for f in nauck if id(f) not in used_n]
    if not remaining_p or not remaining_n:
        return pairs

    def best(source, targets):
        answer = {}
        for fragment in source:
            scores = sorted(
                ((fragment_similarity(fragment, other)[0], other)
                 for other in targets), key=lambda item: item[0], reverse=True)
            answer[id(fragment)] = scores[:2]
        return answer

    p_best, n_best = best(remaining_p, remaining_n), best(remaining_n, remaining_p)
    for fragment in remaining_p:
        scores = p_best[id(fragment)]
        score, other = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else 0.0
        reverse = n_best[id(other)]
        reverse_runner_up = reverse[1][0] if len(reverse) > 1 else 0.0
        if (score >= 0.82 and score - runner_up >= 0.08
                and reverse[0][1] is fragment and score - reverse_runner_up >= 0.08):
            pairs.append((fragment, other, score, fragment_similarity(fragment, other)[1]))
    return pairs


def safe_card_id(label):
    return re.sub(r"[^0-9A-Za-z_-]+", "-", label).strip("-")


def merge_work_views(pearson, nauck):
    """Return merged play views plus a machine-readable fragment concordance."""
    pearson_works = {work["work"]: deepcopy(work) for work in pearson["works"].values()}
    nauck_works = {work["work"]: deepcopy(work) for work in nauck["works"].values()}
    canonical = {}
    for slug, work in pearson_works.items():
        canonical[slug] = {"pearson": work, "nauck": None}
    for slug, work in nauck_works.items():
        target = NAUCK_WORK_ALIASES.get(slug, slug)
        if target in canonical and canonical[target]["nauck"] is None:
            canonical[target]["nauck"] = work
        else:
            canonical[slug] = {"pearson": None, "nauck": work}

    versions = {v["short_id"]: deepcopy(v)
                for v in pearson.get("versions", []) + nauck.get("versions", [])}
    works, concordance = {}, []
    for slug, sources in canonical.items():
        pw, nw = sources["pearson"], sources["nauck"]
        template = deepcopy(pw or nw)
        pfrags = deepcopy((pw or {}).get("fragments", []))
        nfrags = deepcopy((nw or {}).get("fragments", []))
        pairs = align_fragments(pfrags, nfrags)
        p_to_pair = {id(p): (n, score, method) for p, n, score, method in pairs}
        # deepcopy above means object identity is stable inside this function.
        paired_n_numbers = {n["number"] for _, n, _, _ in pairs}
        cards = []
        for fragment in pfrags:
            pair = p_to_pair.get(id(fragment))
            if pair:
                other, score, method = pair
                label = f"P{fragment['number']}=N{other['number']}"
                cards.append({"label": label, "pearson": fragment, "nauck": other})
                fragment["same_as"] = [other["source_fragment_urn"]]
                other["same_as"] = [fragment["source_fragment_urn"]]
                concordance.append({
                    "work": slug, "card": label,
                    "pearson": fragment["source_fragment_urn"],
                    "nauck": other["source_fragment_urn"],
                    "confidence": round(score, 4), "method": method,
                })
            else:
                cards.append({"label": f"P{fragment['number']}", "pearson": fragment})
        for fragment in nfrags:
            if fragment["number"] not in paired_n_numbers:
                cards.append({"label": f"N{fragment['number']}", "nauck": fragment})
        template["work"] = slug
        template["id"] = f"sophocles-{slug.replace('_', '-')}"
        template["object_urn"] = f"urn:cite2:perseus:fragmentaryplays.v1:sophocles-{slug}"
        # The printed Greek heading is the reader-facing title; the stable
        # transliterated slug remains the route/work identifier.
        template["title"] = ((pw or {}).get("source_title")
                             or (nw or {}).get("source_title")
                             or template.get("title", slug))
        template["fragments"] = pfrags + nfrags
        present = ([PEARSON] if pfrags else []) + ([NAUCK] if nfrags else [])
        template["versions"] = [deepcopy(versions[v]) for v in present]
        template["cards"] = cards
        template["line_count"] = sum(len(f.get("lines", [])) for f in template["fragments"])
        template["evidence_only"] = not bool(cards)
        template["status"] = "Fragmentary text" if cards else "Evidence only"
        works[template["id"]] = template
    return works, concordance
