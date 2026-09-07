"""QA guard: compares the chapter/section set implied by each work's source
CoNLL-U files against what actually landed in the monolith and in the
deployed shards, to catch silent truncation. Relocated from Cell 14.

_chset_from_conllu depends on WORK_HAS_BOOKS, which the original notebook
populated as kernel-global state in Cell 1's edition-ingestion loop before
this cell ran. Here it's passed explicitly into run_chunking_guard() instead
of relying on execution order -- pass the same dict that
ingest_work.ingest_editions_and_structure() returns.
"""
import re
import sqlite3
from collections import Counter
from pipeline.core.canonical_intervals import build_poetry_canonical_intervals
from pipeline.treebank.conllu import parse_conllu_treebank
from pathlib import Path

def _natkey(c):
    m = re.match(r"(\d+)", str(c) or "")
    return (int(m.group(1)) if m else 10**9, str(c))

def _chset_from_conllu(cfg, tg, wk, work_meta, work_key):
    """Expected chapter set = what parse_conllu_treebank would emit from the
    source path(s), using the same card-interval logic the build uses.
    has_books is looked up from WORK_HAS_BOOKS (populated by Cell 1's
    edition-ingestion loop, which must have already run in this kernel
    session) so this independent re-derivation stays consistent with
    whatever alignment_grid was actually keyed by for this work -- getting
    this wrong is exactly what silently broke the bookless Poetics
    treebanks (Kassel, Bishr Matta) before this guard existed."""
    card_intervals = None
    if any(c.get("parse_mode") == "poetry_cards"
           for c in work_meta.get("editions", {}).values()):
        try:
            ci = build_poetry_canonical_intervals(work_meta["editions"])
            card_intervals = [iv for bk in ci.values() for iv in bk]
        except Exception as e:
            print(f"      ⚠ card-interval build failed ({e}); using None")
    has_books = WORK_HAS_BOOKS.get(work_key, True)
    sents, _doc_credits = parse_conllu_treebank(cfg["path"], "?", tg, wk,
                                                 card_intervals=card_intervals,
                                                 has_books=has_books)
    return Counter(str(s["chapter"]) for s in sents if s.get("subdoc"))

def _chset_from_db(db_path, tg, wk, vid):
    if not Path(db_path).exists():
        return None
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT chapter, COUNT(*) FROM treebank_sentences "
            "WHERE textgroup=? AND work=? AND version_short_id=? GROUP BY chapter",
            (tg, wk, vid)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        con.close()
    return Counter({str(c): n for c, n in rows})

def _chset_from_all_parts(site_root, tg, wk, vid):
    """A work may now be split into several book-range part files (see
    Cell 2's book-aware sharder); this unions the chapter counts across
    every part*.db so the guard still checks the WHOLE work, not just
    whichever part happens to sort first."""
    part_files = sorted((site_root / "data" / tg / wk).glob(f"{tg}.{wk}.part*.db"))
    if not part_files:
        return None, []
    total = Counter()
    found_any = False
    for pf in part_files:
        c = _chset_from_db(pf, tg, wk, vid)
        if c:
            found_any = True
            total.update(c)
    return (total if found_any else None), part_files


def run_chunking_guard(monolith_db, site_root, work_keys=None,
                        work_has_books=None, expected_tb_chapters=None):
    """Relocated from Cell 14's driver tail; parameterized with work_keys
    (defaults to every work in WORK_REGISTRY) and work_has_books (defaults
    to empty -- see module docstring) instead of always scanning the full
    registry against kernel-global state.
    """
    from pipeline.registry import WORK_REGISTRY
    global WORK_HAS_BOOKS
    WORK_HAS_BOOKS = work_has_books or {}
    EXPECTED_TB_CHAPTERS = expected_tb_chapters or {}
    MONOLITH_DB = monolith_db
    SITE_ROOT = site_root
    target_keys = work_keys or list(WORK_REGISTRY.keys())

    failures = []
    print("── Treebank chunking guard ───────────────────────────────────────────")
    for work_key in target_keys:
        work_meta = WORK_REGISTRY[work_key]
        tbs = {v: c for v, c in work_meta.get("treebanks", {}).items()
               if c.get("parse_mode") == "conllu"}
        if not tbs:
            continue
        tg, wk = work_meta["textgroup"], work_meta["work"]
        print(f"\n[{work_key}]")

        for vid, cfg in tbs.items():
            src_set  = set(_chset_from_conllu(cfg, tg, wk, work_meta, work_key))
            mono_set = set(_chset_from_db(MONOLITH_DB, tg, wk, vid) or Counter())
            shd_ct, part_files = _chset_from_all_parts(SITE_ROOT, tg, wk, vid)
            shd_set = set(shd_ct) if shd_ct is not None else None
            part_names = ", ".join(p.name for p in part_files) if part_files else "none found"

            n_shd = "n/a" if shd_set is None else len(shd_set)
            print(f"  {vid:<22} source={len(src_set):>3} chapters  "
                  f"monolith={len(mono_set):>3}  shard={n_shd}  (parts: {part_names})")

            if shd_set is None:
                failures.append(f"{work_key}/{vid}: no shard parts found, or no treebank_sentences rows across them")
                print("      \u2717 no shard parts have rows for this version")
                continue

            miss_mono = src_set - mono_set
            if miss_mono:
                failures.append(f"{work_key}/{vid}: monolith missing chapters {sorted(miss_mono, key=_natkey)}")
                print(f"      \u2717 in source but NOT in monolith: {sorted(miss_mono, key=_natkey)}  \u2192 re-run ingest_work for this work")

            miss_shd = mono_set - shd_set
            if miss_shd:
                failures.append(f"{work_key}/{vid}: shard missing chapters {sorted(miss_shd, key=_natkey)}")
                print(f"      \u2717 in monolith but NOT in shard: {sorted(miss_shd, key=_natkey)}  \u2192 re-run sharding.split_corpus_by_work + redeploy")

            extra_shd = shd_set - src_set
            if extra_shd:
                failures.append(f"{work_key}/{vid}: shard has unexpected chapters {sorted(extra_shd, key=_natkey)}")
                print(f"      \u2717 in shard but NOT in source (stale data?): {sorted(extra_shd, key=_natkey)}")

            if len(src_set) > 1 and shd_set == {"1"}:
                print("      \u2717 ALL shard sentences are chapter '1' \u2014 classic silent fallback / stale source")

            exp = EXPECTED_TB_CHAPTERS.get(vid)
            if exp is not None and len(shd_set) != exp:
                failures.append(f"{work_key}/{vid}: expected {exp} chapters in shard, got {len(shd_set)}")
                print(f"      \u2717 EXPECTED {exp} chapters, shard has {len(shd_set)}")

            if not (miss_mono or miss_shd or extra_shd) and (exp is None or len(shd_set) == exp):
                ordered = sorted(shd_set, key=_natkey)
                print(f"      \u2713 source \u2194 monolith \u2194 shard agree ({ordered[:3]}\u2026{ordered[-1:]})")

    print("\n──────────────────────────────────────────────────────────────────────")
    if failures:
        print(f"\u2717 {len(failures)} treebank chunking problem(s):")
        for f in failures:
            print("   \u2022", f)
        raise AssertionError(f"Treebank chunking guard failed ({len(failures)} issue(s)) \u2014 do not deploy.")
    print("\u2713 All treebank chapters consistent across source, monolith, and shards.")
    return failures
