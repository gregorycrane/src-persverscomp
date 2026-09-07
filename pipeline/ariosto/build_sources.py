"""Driver: orlando-furioso-sanjaya annotation JSON  ->  augmented CoNLL-U
(the same shape parse_conllu_treebank already ingests for the Greek/Latin
glossed treebanks) + a 2-column lemma/gloss TSV for the Italian glossary
lexicon.

Run:  python3 -m pipeline.ariosto.build_sources

The Sanjaya annotations give ONE dependency parse per octave (ottava rima
stanza); tokens carry UD-style lemma / UPOS / XPOS / feats / head / deprel
plus an English `gloss`. Ariosto's citation is canto -> stanza -> line, so:

  * `# sent_id = <canto>.<stanza>.1`  -- one treebank sentence per stanza
    (poem-carded model, matched to its card by parse_conllu_treebank's
    book_card_lookup exactly like Propertius: sid_parts[0]=canto=book,
    sid_parts[1]=stanza=card label).
  * per-token `Ref=<line 1-8>` in MISC  -- drives the treebank column's
    per-line grid rows in web/app.js. Assigned by aligning the token
    stream to the stanza's 8 text lines (difflib, tolerant of the
    tokenizer splitting Italian preposition+article contractions like
    "dal" -> "da"+"il").

Outputs are written next to the TEI sources and are committed like any
other source file -- the pipeline never regenerates them.
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from pipeline.treebank.norm_key import norm_key

ANNOT_DIR = Path("/Users/gcrane/github/orlando-furioso-sanjaya/annotations")
OUT_DIR = Path("/Users/gcrane/github/grcnewxml/data/ariosto/orlandofurioso")
CONLLU_OUT = OUT_DIR / "ariosto.orlandofurioso.sanjaya-tb-ita1.conllu"
GLOSSARY_OUT = OUT_DIR / "ariosto.orlandofurioso.glossary-ita1.tsv"

DOC_ID = "ariosto.orlandofurioso.sanjaya-tb-ita1"
N_CANTOS = 46

_NO_SPACE_BEFORE = {",", ".", ";", ":", "!", "?", "»", ")", "”", "’", "'"}


def _match_norm(s: str) -> str:
    """Aggressive fold for token<->line alignment only: strip diacritics
    and every non-alphanumeric so elisions/apostrophes/punctuation don't
    perturb the match, and a split contraction ("da"+"il") differs from
    its surface ("dal") by just one inserted letter."""
    t = unicodedata.normalize("NFD", s)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t.lower())


def _stanza_lines(entry: dict):
    return [ln.strip() for ln in entry["text"].split("\n") if ln.strip()]


def _assign_line_refs(forms, lines):
    """Return a list of line numbers (1..len(lines)) parallel to `forms`,
    or None if the alignment looks unreliable."""
    if len(lines) != 8 or not forms:
        return None

    line_norm = [_match_norm(ln) for ln in lines]
    bounds, acc = [], 0
    for ln in line_norm:
        acc += len(ln)
        bounds.append(acc)               # cumulative end offset of each line
    full = "".join(line_norm)

    tok_norm = [_match_norm(f) for f in forms]
    tok_start, acc = [], 0
    for tn in tok_norm:
        tok_start.append(acc)
        acc += len(tn)
    concat = "".join(tok_norm)

    opcodes = SequenceMatcher(None, concat, full, autojunk=False).get_opcodes()

    def project(p):
        for tag, i1, i2, j1, j2 in opcodes:
            if i1 <= p < i2 or (p == i2 and tag != "insert"):
                if tag in ("equal", "replace"):
                    return min(j1 + (p - i1), max(j2 - 1, j1))
                return j1
        return len(full) - 1

    refs, last = [], 1
    for idx, tn in enumerate(tok_norm):
        if not tn:                       # punctuation-only token
            refs.append(last)
            continue
        q = project(tok_start[idx])
        ln = 1
        for li, b in enumerate(bounds):
            if q < b:
                ln = li + 1
                break
        else:
            ln = len(lines)
        ln = max(ln, last)               # monotonic: lines never go backwards
        refs.append(ln)
        last = ln

    # sanity: every line should be represented and the last token should
    # land on (or very near) the final line.
    if refs[-1] < len(lines) - 1 or len(set(refs)) < len(lines) - 1:
        return None
    return refs


def _gloss_slug(g: str) -> str:
    return re.sub(r"\s+", "-", g.strip()).replace("|", "/")


def _misc(ref, no_space, gloss):
    parts = []
    if ref is not None:
        parts.append(f"Ref={ref}")
    if no_space:
        parts.append("SpaceAfter=No")
    if gloss:
        parts.append(f"gloss={_gloss_slug(gloss)}")
    return "|".join(parts) if parts else "_"


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blocks = [f'# newdoc id = "{DOC_ID}"']
    glossary = {}                        # norm_key -> [display_lemma, {glosses}]
    n_sent = n_tok = 0
    unaligned = []
    untokenized = []

    for canto in range(1, N_CANTOS + 1):
        src = ANNOT_DIR / f"{canto}_nlp_gloss.json"
        entries = json.loads(src.read_text(encoding="utf-8"))
        for si, entry in enumerate(entries, start=1):
            toks = [t["annotation"] for t in entry["annotation"]]
            if not toks:
                # A handful of stanzas (the canto 32 proem) have text but no
                # linguistic annotation in the source -- skip; the reading
                # text + Rose translation still cover them.
                untokenized.append(f"{canto}.{si}")
                continue

            forms = [t["text"] for t in toks]
            lines = _stanza_lines(entry)
            # Align the whole stanza's token stream to its 8 lines once, then
            # slice per sentence -- keeps the mapping global and monotonic.
            refs = _assign_line_refs(forms, lines)
            if refs is None:
                unaligned.append(f"{canto}.{si}")
                refs = [None] * len(forms)

            # The NLP tool splits an octave into 1..N syntactic sentences;
            # token `id` restarts at 1 for each, and HEAD points within the
            # sentence -- so we MUST re-split here (a flat emit would corrupt
            # every head in sentences 2..N). Boundary = id == 1.
            starts = [i for i, tk in enumerate(toks) if tk["id"] == 1] + [len(toks)]
            def _no_space_after(i):
                nxt = forms[i + 1] if i + 1 < len(forms) else ""
                return nxt in _NO_SPACE_BEFORE or forms[i].endswith(("'", "’"))

            for k in range(len(starts) - 1):
                lo, hi = starts[k], starts[k + 1]
                sent_text = ""
                for i in range(lo, hi):
                    sent_text += forms[i] + ("" if _no_space_after(i) else " ")
                rows = [f"# sent_id = {canto}.{si}.{k + 1}",
                        f"# text = {sent_text.strip()}"]
                for i in range(lo, hi):
                    tk = toks[i]
                    no_space = _no_space_after(i)
                    lemma = tk.get("lemma") or "_"
                    gloss = tk.get("gloss") or ""
                    rows.append("\t".join([
                        str(tk["id"]),
                        tk.get("text") or "_",
                        lemma,
                        tk.get("part_of_speech") or "_",
                        tk.get("xpos") or "_",
                        tk.get("morphology") or "_",
                        str(tk.get("head", 0)),
                        tk.get("deprel") or "dep",
                        "_",
                        _misc(refs[i], no_space, gloss),
                    ]))
                    n_tok += 1
                    if gloss and lemma != "_":
                        gk = norm_key(lemma)
                        if gk:
                            glossary.setdefault(gk, [lemma, set()])[1].add(gloss.strip())
                blocks.append("\n".join(rows))
                n_sent += 1

    CONLLU_OUT.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    with GLOSSARY_OUT.open("w", encoding="utf-8") as fh:
        for k in sorted(glossary):
            lemma, glosses = glossary[k]
            fh.write(f"{lemma}\t{'; '.join(sorted(glosses))}\n")

    print(f"[ariosto] {n_sent} sentences, {n_tok} tokens -> {CONLLU_OUT}")
    print(f"[ariosto] {len(glossary)} glossary lemmas -> {GLOSSARY_OUT}")
    if untokenized:
        print(f"[ariosto] note: {len(untokenized)} stanza(s) have no source "
              f"annotation, skipped: {', '.join(untokenized)}")
    if unaligned:
        print(f"[ariosto] WARNING: token->line alignment fell back to "
              f"stanza-level for {len(unaligned)} stanza(s): "
              f"{', '.join(unaligned[:20])}{' ...' if len(unaligned) > 20 else ''}")


if __name__ == "__main__":
    build()
    sys.exit(0)
