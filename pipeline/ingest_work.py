"""Per-work (or full-registry) ingestion into the persistent monolith.

Relocated from Cell 4's driver tail (everything after its function
definitions), which originally ran as four unconditional top-level loops
over the ENTIRE WORK_REGISTRY every time the cell ran. The loop BODIES
below are unchanged from the notebook; the only mechanical edit is the
loop header itself: `for work_key, work_meta in WORK_REGISTRY.items():`
became `for work_key in target_keys: work_meta = WORK_REGISTRY[work_key]`,
so the same code can run over one work or the whole registry.

_pending_metrical / WORK_HAS_BOOKS were kernel-global state in the
notebook (written by phase 1, read by phase 2, for the SAME work_key each
time -- never across works). Here they're threaded explicitly as a return
value / parameter instead, so this module has no hidden global state.

ingest_works() is NEW: it adds the delete-before-insert step that makes a
single-work rebuild safe against a PERSISTENT monolith (see manifest.py /
build_all.py) instead of the notebook's one-shot "delete the whole DB file,
recreate from scratch" behavior in init_storage_engine.
"""
import os
import re
import json
import sqlite3
from pathlib import Path
from collections import OrderedDict

from pipeline.config import DB_PATH
from pipeline.registry import WORK_REGISTRY
from pipeline.core.xml_utils import NS, _ns, safe_parse, find_text_root, extract_text_recursive
from pipeline.core.storage import TEXTGROUP_NAMESPACE, generate_canonical_id
from pipeline.core.canonical_intervals import (
    build_poetry_canonical_intervals, build_line_remap, build_milestone_remap,
)
from pipeline.core.alignment import ingest_edition_alignment
from pipeline.parsers import DOC_TYPE_PARSERS
from pipeline.parsers.poetry_cards import parse_poetry_cards_tei
from pipeline.parsers.card_prose import parse_card_prose_tei
from pipeline.parsers.milestones import parse_milestone_tei
from pipeline.parsers.reading_lines import parse_reading_lines_tei
from pipeline.parsers.hierarchical import parse_hierarchical_tei
from pipeline.parsers.speech_collection import parse_speech_collection_tei
from pipeline.parsers.book_chapter_section import parse_book_chapter_section_tei
from pipeline.parsers.line_commentary import parse_line_commentary_tei
from pipeline.parsers.speakers import parse_speakers_csv
from pipeline.parsers.metrical import parse_metrical_tsv
from pipeline.treebank.conllu import parse_conllu_treebank
from pipeline.treebank.agdt import parse_agdt_treebank
from pipeline.treebank.flatten import flatten_treebank_tokens


# ── NEW: delete-before-insert, scoped to the works being rebuilt ───────────
# text_segments has no textgroup/work columns of its own (only passage_urn +
# version_short_id) -- it must be cleared via a subquery against
# alignment_grid BEFORE alignment_grid's own rows for that work are deleted.
_DIRECTLY_KEYED_TABLES = [
    "text_units", "alignment_grid", "edition_chapter_order", "work_book_metadata",
    "treebank_sentences", "treebank_doc_credits", "treebank_speakers",
    "metrical_lines", "token_alignments",
]

def _delete_existing_rows(conn, target_keys):
    cur = conn.cursor()
    for work_key in target_keys:
        meta = WORK_REGISTRY[work_key]
        tg, wk = meta["textgroup"], meta["work"]
        cur.execute(
            "DELETE FROM text_segments WHERE passage_urn IN "
            "(SELECT passage_urn FROM alignment_grid WHERE textgroup=? AND work=?)",
            (tg, wk),
        )
        for table in _DIRECTLY_KEYED_TABLES:
            cur.execute(f"DELETE FROM {table} WHERE textgroup=? AND work=?", (tg, wk))
    conn.commit()


# ── Phase 1: editions, alignment_grid, text_segments ───────────────────────
def ingest_editions_and_structure(conn, target_keys):
    cursor = conn.cursor()
    # NEW vs. the notebook: _pending_metrical and WORK_HAS_BOOKS were also
    # kernel-global, initialized once before Cell 4's driver loop (see
    # global_sort_index note above -- same fix, same reasoning).
    # WORK_HAS_BOOKS: whether each work has book-level divisions at all,
    # keyed by work_key. Populated below (same has_multiple_books the
    # edition loop uses to build alignment_grid) and returned for the
    # caller to pass into ingest_treebank_and_metrical (conllu
    # chapter/section addressing needs to agree with however this work's
    # alignment_grid was actually keyed) and, optionally, into
    # chunking_guard.run_chunking_guard / topostext.ingest_place_references.
    _pending_metrical = {}
    WORK_HAS_BOOKS = {}
    global_sort_index = 0
    for work_key in target_keys:
        work_meta = WORK_REGISTRY[work_key]
        tg = work_meta["textgroup"]
        wk = work_meta["work"]
    
        editions_combined = {}
        doc_types_map = {}

        # Accumulates per-book titles/summaries auto-derived from the TEI itself
        # (currently only populated by the speech_collection_sentences branch
        # below, via parse_speech_collection_tei) across every edition of this
        # work. setdefault below means the FIRST edition (in editions_combined's
        # own order) to report a non-empty value for a given book wins; later
        # editions with the same book number don't overwrite it. Written to the
        # work_book_metadata table once the edition loop finishes.
        _work_book_titles = {}
        _work_book_summaries = {}

        for category in ["editions", "appcrits", "translations", "commentaries", "scholia"]:
            category_dict = work_meta.get(category, {})
            editions_combined.update(category_dict)
            for v_id in category_dict:
                doc_types_map[v_id] = {
                    "editions": "edition",
                    "appcrits": "appcrit",
                    "translations": "translation",
                    "commentaries": "commentary",
                    "scholia": "scholia",
                }[category]

        for v_id, cfg in work_meta.get("treebanks", {}).items():
            canonical_id = f"{tg}_{wk}_{v_id}_treebank"
            cursor.execute("""
                INSERT OR REPLACE INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (canonical_id, f"urn:cts:{_ns(work_key)}:{work_key}.{v_id}",
                  cfg["label"], cfg["class"], tg, wk, v_id, "treebank"))

        # ── Ingest metrical annotation files ──────────────────────────────
        for v_id, cfg in work_meta.get("metrics", {}).items():
            canonical_id = f"{tg}_{wk}_{v_id}_metrical"
            cursor.execute("""
                INSERT OR REPLACE INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (canonical_id, f"urn:cts:{_ns(work_key)}:{work_key}.{v_id}",
                  cfg["label"], cfg["class"], tg, wk, v_id, "metrical"))
            lines_data = parse_metrical_tsv(cfg["path"])
            if not lines_data:
                print(f"  ⚠ No metrical data loaded for {v_id}")
                continue
            # Map line_ref -> chapter using card intervals (built later);
            # store temporarily and re-ingest after master_intervals are built.
            # For now store lines keyed by line_ref; chapter assigned below.
            _pending_metrical[work_key] = _pending_metrical.get(work_key, {})
            _pending_metrical[work_key][v_id] = {"cfg": cfg, "lines_data": lines_data,
                                                  "canonical_id": canonical_id}
            print(f"  ✓ Loaded {len(lines_data)} metrical lines for {v_id}")

        print(f"Ingesting structural alignment mappings for work: {work_key}...")
    
        _used_canonical_ids = set()
        for v_id, cfg in editions_combined.items():
            doc_type = doc_types_map[v_id]
            canonical_id = generate_canonical_id(work_key, cfg["label"], doc_type)
            if canonical_id in _used_canonical_ids:
                # generate_canonical_id only reads the editor name + year out of
                # the label's first parenthetical, so two editions whose labels
                # only differ AFTER that point collide -- e.g. Wendel's original
                # German notes and their English machine translation both start
                # "(Carolus Wendel, 1935...)". Since canonical_id is the PRIMARY
                # KEY in text_units and this is an INSERT OR REPLACE, the second
                # one silently overwrote the first one's row -- one commentary
                # just vanished from the dropdown with no error anywhere.
                # Disambiguate with the edition's own registry key (v_id), which
                # is already guaranteed unique by construction.
                canonical_id = f"{canonical_id}_" + re.sub(r"[^0-9a-zA-Z]+", "_", v_id).strip("_").lower()
            _used_canonical_ids.add(canonical_id)
            cursor.execute("""
                INSERT OR REPLACE INTO text_units (canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (canonical_id, f"urn:cts:{_ns(work_key)}:{work_key}.{v_id}", cfg["label"], cfg["class"], tg, wk, v_id, doc_type))


        master_intervals = None
        is_poetry = any(cfg.get("parse_mode") in ("poetry_cards", "card_prose") for cfg in editions_combined.values())
        if is_poetry:
            master_intervals = build_poetry_canonical_intervals(editions_combined)

        # Card structure is built from the baseline edition (perseus-grc2 = Storr).
        # For every edition-alignment crosswalk whose base axis IS that baseline,
        # build a {target_line: baseline_line} remap so the target edition is binned
        # by its true Storr counterpart line (split/merge -> first Storr line of the
        # group; target_only -> preceding Storr line). Display keeps the native @n.
        baseline_vid = ("perseus-grc2" if "perseus-grc2" in editions_combined
                        else (next(iter(editions_combined)) if editions_combined else None))
        edition_remaps = {}
        for _tsv in work_meta.get("edition_alignments", []):
            if not os.path.exists(_tsv):
                continue
            _bv, _tv, _map = build_line_remap(_tsv)
            if _tv:
                edition_remaps[_tv] = {"base": _bv, "map": _map}
                print(f"  \u21b3 line remap {_tv}\u2192{_bv}: {len(_map)} lines (baseline={baseline_vid})")

        work_corpus = OrderedDict()
        edition_own_order = {}
        for v_id, cfg in editions_combined.items():
            p_mode = cfg.get("parse_mode")
            if p_mode == "poetry_cards":
                if cfg.get("card_anchor") == "milestones":
                    # Carries embedded Storr card milestones: bin by those, ignoring
                    # its own independent line numbers (which remain display-only).
                    _rm = build_milestone_remap(cfg["path"])
                    _intervals_for_this_edition = master_intervals
                elif cfg.get("card_anchor") == "poem":
                    # Div-carded (elegy/letter-collection) works whose editors
                    # disagree about where poems split -- e.g. Propertius: Butler
                    # divides book 2 into 43 poems, the Perseus edition into 46,
                    # with different lettered sub-splits (18a/18b vs 18a/18b/18c)
                    # at different points. A single shared master_intervals (built
                    # from whichever edition happens to be first/baseline) means
                    # every OTHER edition's own div boundaries silently fail to
                    # match card_n_to_label and get merged into the wrong card --
                    # this is what broke the second Propertius edition. Until a
                    # real cross-edition remap exists for div-carded works (the
                    # existing edition_remaps/line_remap machinery only hooks into
                    # the milestone-anchored branch above), each such edition
                    # computes and displays its OWN independent card structure.
                    _rm = None
                    _intervals_for_this_edition = build_poetry_canonical_intervals({v_id: cfg})
                else:
                    _info = edition_remaps.get(v_id)
                    _rm = _info["map"] if (_info and _info["base"] == baseline_vid) else None
                    _intervals_for_this_edition = master_intervals
                parsed = parse_poetry_cards_tei(cfg["path"], _intervals_for_this_edition,
                                                lineno_sigil=cfg.get("lineno_sigil"),
                                                line_remap=_rm)
            elif p_mode == "card_prose":
                # Prose (no <l>) segmented only by embedded Storr card milestones.
                parsed = parse_card_prose_tei(cfg["path"], master_intervals,
                                              lineno_sigil=cfg.get("lineno_sigil"))
            elif p_mode == "line_commentary":
                # Line-keyed verse commentary (e.g. Jebb): bins each note into the
                # SAME canonical card as the verse baseline via its commline @n /
                # section @corresp. Requires a poetry verse edition in this work so
                # master_intervals exists; returns None (skipped) if it does not.
                parsed = parse_line_commentary_tei(cfg["path"], master_intervals,
                                                   lineno_sigil=cfg.get("lineno_sigil"),
                                                   anchor_axis=cfg.get("anchor_axis", "native"),
                                                   reference_sigil=cfg.get("reference_sigil"),
                                                   show_reference_line=cfg.get("show_reference_line", False))
            elif p_mode == "milestones":
                # Translation whose own div hierarchy (e.g. Twining's Part/Section) does
                # NOT match the canonical chapter:section scheme, but which carries inline
                # <milestone unit='bekker' n='CHAPTER.SECTION'/> anchors. Bin running prose
                # by those so it aligns to the baseline chapter:section grid.
                parsed = parse_milestone_tei(cfg["path"],
                                             milestone_unit=cfg.get("milestone_unit", "bekker"),
                                             lineno_sigil=cfg.get("lineno_sigil"),
                                             milestone_scheme=cfg.get("milestone_scheme", "chapter_section"))
            elif p_mode == "reading_lines":
                parsed = parse_reading_lines_tei(cfg["path"])
            elif p_mode == "book_chapter_section":
                # Strict book>chapter>section div hierarchy where a section may
                # bundle several <s> sentences under one <p> (e.g. Heike Monogatari).
                # See parse_book_chapter_section_tei's docstring for why this can't
                # just reuse parse_hierarchical_tei.
                parsed = parse_book_chapter_section_tei(cfg["path"])
            elif p_mode == "speech_collection_sentences":
                # Sentence-granular collection of speeches (e.g. Boeckh's
                # Orationes): book=speech, chapter=paragraph, section=sentence,
                # read directly off the file's own div>p>s structure rather than
                # requiring a wrapping div per chapter/section level. See
                # parse_speech_collection_tei's docstring.
                parsed, _book_titles_this_edition, _book_summaries_this_edition = parse_speech_collection_tei(
                    cfg["path"], book_div_types=(cfg.get("book_div_type", "edition"),))
                # Book titles/summaries are static work-level metadata (used by
                # catalog.json, not per-shard). Merged into work_book_metadata
                # (written after the edition loop below) so they flow straight
                # from the TEI's own <head> elements on every rebuild -- no
                # manual work_registry.json copy to keep in sync. setdefault:
                # first edition to report a non-empty value for a book wins.
                for _bk, _t in _book_titles_this_edition.items():
                    _work_book_titles.setdefault(_bk, _t)
                for _bk, _s in _book_summaries_this_edition.items():
                    _work_book_summaries.setdefault(_bk, _s)
            else:
                parsed = parse_hierarchical_tei(cfg["path"], include_nonparagraph_blocks=work_meta.get("strict_section_alignment", False))
            
            if parsed is not None and sum(len(secs) for chs in parsed.values() for secs in chs.values()) > 0:
                work_corpus[v_id] = parsed
                # Capture this edition's OWN document-order sequence of chapters,
                # per book, while it's still available as the parsed dict's key
                # order (an OrderedDict, insertion-ordered by construction in
                # parse_poetry_cards_tei / parse_card_prose_tei etc.). This is
                # what lets the client show "reading order" cards in the order
                # THIS edition actually prints them (e.g. Sidgwick's Eumenides
                # binding song genuinely swaps two stanzas relative to Smyth),
                # independent of the single global sort_order every edition
                # otherwise shares. See _merge_local_order below.
                edition_own_order[v_id] = {bk: list(chs.keys()) for bk, chs in parsed.items()}
                print(f"  ✓ {v_id}: {sum(len(secs) for chs in parsed.values() for secs in chs.values())} segments parsed")
            else:
                print(f"  ✗ {v_id}: Failed to parse completely.")

        if not work_corpus: continue

        first_version = list(work_corpus.keys())[0]
        baseline_corpus = work_corpus[first_version]

        # chapter_sequence used to come ONLY from `first_version` -- whichever
        # edition happened to be first in dict/registry order. That's fine when
        # every edition shares one citation scheme (Homer, Vergil...), but for
        # div-carded works where editors genuinely disagree about where poems
        # split (Propertius: Butler splits 2.8 into 8/8a where Muller keeps it
        # whole; Perseus's edition splits 2.18 into three where Butler splits it
        # into two), any card that ONLY exists in a non-first edition had no
        # chapter_sequence slot at all -- not hidden, structurally unreachable,
        # since alignment_grid/text_segments/the client TOC are all built by
        # walking this sequence. Fix: union every edition's own (book, chapter)
        # pairs, in natural order (8, 8a, 8b, 9 -- not string order). The
        # per-edition INSERT loop below already tolerates an edition not having
        # a given chapter (falls back to "[Text range missing...]"), so nothing
        # else needs to change -- editions that never split a poem simply show
        # that fallback at the cards only some OTHER edition introduced.
        def _natural_card_key(s):
            m = re.match(r'^(\d+)(.*)$', str(s))
            return (int(m.group(1)), m.group(2)) if m else (10**9, str(s))

        union_books = OrderedDict()
        for v_corpus in work_corpus.values():
            for b_k, ch_v in v_corpus.items():
                union_books.setdefault(b_k, set()).update(ch_v.keys())

        has_multiple_books = len(union_books) > 1
        WORK_HAS_BOOKS[work_key] = has_multiple_books

        # Persist any auto-derived book titles/summaries gathered above (see
        # _work_book_titles / _work_book_summaries). Cleared for this work first
        # so a book whose <head> was removed from the XML doesn't leave a stale
        # row behind from a previous run.
        cursor.execute("DELETE FROM work_book_metadata WHERE textgroup=? AND work=?;", (tg, wk))
        for _bk in set(_work_book_titles) | set(_work_book_summaries):
            cursor.execute("""
                INSERT OR REPLACE INTO work_book_metadata (textgroup, work, book, title, summary)
                VALUES (?, ?, ?, ?, ?);
            """, (tg, wk, _bk, _work_book_titles.get(_bk), _work_book_summaries.get(_bk)))

        def _book_sort_key(b):
            try:
                return (0, int(b))
            except (TypeError, ValueError):
                return (1, str(b))

        chapter_sequence = []
        for b_k in sorted(union_books, key=_book_sort_key):
            for c_k in sorted(union_books[b_k], key=_natural_card_key):
                chapter_sequence.append({'book': b_k if has_multiple_books else None, 'chapter': c_k})

        # ── Per-edition reading order (Focus-aware) ────────────────────────────
        # chapter_sequence above is the single CANONICAL order every edition
        # shares (union of all cards, sorted naturally) -- fine for the default
        # view, but wrong whenever an edition's own printed order of cards
        # genuinely differs from canonical (e.g. Sidgwick's Eumenides swaps two
        # stanzas of the binding song relative to Smyth's numbering). For each
        # edition, merge its OWN observed card order (edition_own_order, from
        # the parse step above) against the canonical order: cards the edition
        # actually contains keep ITS relative order; any canonical card the
        # edition lacks is slotted in right after the nearest canonical
        # predecessor the edition DOES have (falling back to canonical position
        # for runs of missing cards, and to the front/back for cards outside
        # every edition-own card's span). Editions with no own-order data at all
        # (translations riding line-fallback, etc.) just get the canonical order
        # back unchanged -- this is a strict generalization, not a special case.
        def _merge_local_order(canonical_labels, own_labels):
            own_set = set(own_labels)
            canon_pos = {lab: i for i, lab in enumerate(canonical_labels)}
            result = []
            max_seen = -1  # highest canonical index already flushed -- monotonic,
                            # so an edition that reorders relative to canonical
                            # more than once never re-flushes or duplicates a gap.
            for lab in own_labels:
                ci = canon_pos.get(lab)
                if ci is not None and ci > max_seen:
                    for mid in canonical_labels[max_seen + 1:ci]:
                        if mid not in own_set:
                            result.append(mid)
                    max_seen = ci
                result.append(lab)
            for mid in canonical_labels[max_seen + 1:]:
                if mid not in own_set:
                    result.append(mid)
            return result

        canonical_by_book = {b_k: sorted(union_books[b_k], key=_natural_card_key) for b_k in union_books}
        # Same orphaned-row risk as alignment_grid above: INSERT OR REPLACE
        # here only touches (textgroup, work, version_short_id, book, chapter)
        # combinations the CURRENT build still produces, so a chapter/card that
        # dropped out of an edition's own order between builds would otherwise
        # leave a stale local_sort_index row behind.
        cursor.execute("DELETE FROM edition_chapter_order WHERE textgroup=? AND work=?;", (tg, wk))
        for v_id in editions_combined:
            own_by_book = edition_own_order.get(v_id, {})
            for b_k, canonical_labels in canonical_by_book.items():
                merged = _merge_local_order(canonical_labels, own_by_book.get(b_k, []))
                grid_book_val = b_k if has_multiple_books else None
                for local_idx, ch_id in enumerate(merged):
                    cursor.execute("""
                        INSERT OR REPLACE INTO edition_chapter_order
                        (textgroup, work, version_short_id, book, chapter, local_sort_index)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """, (tg, wk, v_id, grid_book_val, ch_id, local_idx))

        # Clear this work's existing alignment_grid/text_segments rows before
        # re-inserting. INSERT OR REPLACE only overwrites a row when the new
        # passage_urn collides with an existing one -- it never removes a row
        # whose passage_urn simply isn't produced anymore. Without this delete,
        # a card that existed in an earlier build (e.g. from a stray milestone
        # since fixed in the source XML, or an earlier version of
        # build_poetry_canonical_intervals) survives as an orphaned row forever,
        # even after the XML/code that produced it is corrected. Mirrors the
        # work_book_metadata delete above.
        cursor.execute("DELETE FROM text_segments WHERE passage_urn IN "
                       "(SELECT passage_urn FROM alignment_grid WHERE textgroup=? AND work=?);", (tg, wk))
        cursor.execute("DELETE FROM alignment_grid WHERE textgroup=? AND work=?;", (tg, wk))

        for c_idx, coord in enumerate(chapter_sequence):
            bk_id = coord['book']
            ch_id = coord['chapter']
            lookup_bk = bk_id if bk_id else list(baseline_corpus.keys())[0]
            # chapter_sequence is now the UNION of every edition's own (book,
            # chapter) pairs (see above) -- a chapter can legitimately exist in
            # chapter_sequence because SOME edition has it, while `baseline_corpus`
            # specifically (still just work_corpus[first_version], used elsewhere
            # as a general fallback) has no entry for it at all. Raw-indexing
            # baseline_corpus[lookup_bk][ch_id] here throws exactly that KeyError
            # the moment a union-only chapter is reached. Union the section keys
            # across every edition that actually has this (book, chapter) instead
            # -- same tolerant .get() pattern the per-edition INSERT loop below
            # already uses, just applied one step earlier.
            sec_union = set()
            for v_corpus in work_corpus.values():
                sec_union.update(v_corpus.get(lookup_bk, {}).get(ch_id, {}).keys())
            baseline_secs = sorted(sec_union, key=_natural_card_key) if sec_union else ["1"]
        
            for sec in baseline_secs:
                global_sort_index += 1
                if bk_id:
                    passage_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{bk_id}.{ch_id}.{sec}"
                    prev_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{chapter_sequence[c_idx-1]['book']}.{chapter_sequence[c_idx-1]['chapter']}.{sec}" if c_idx > 0 else None
                    next_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{chapter_sequence[c_idx+1]['book']}.{chapter_sequence[c_idx+1]['chapter']}.{sec}" if c_idx < len(chapter_sequence) - 1 else None
                else:
                    passage_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{ch_id}.{sec}"
                    prev_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{chapter_sequence[c_idx-1]['chapter']}.{sec}" if c_idx > 0 else None
                    next_urn = f"urn:cts:{_ns(work_key)}:{work_key}:{chapter_sequence[c_idx+1]['chapter']}.{sec}" if c_idx < len(chapter_sequence) - 1 else None
            
                cursor.execute("""
                    INSERT OR REPLACE INTO alignment_grid 
                    (passage_urn, textgroup, work, book, chapter, section, prev_urn, next_urn, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (passage_urn, tg, wk, bk_id, ch_id, sec, prev_urn, next_urn, global_sort_index))
            
                for v_id in editions_combined:
                    ch_data = work_corpus.get(v_id, {}).get(lookup_bk, {}).get(ch_id, {})
                    raw_html = ch_data.get(sec)
                    # Strictly aligned prose must never copy section 1 into
                    # a citation present only in another edition's structure.
                    if raw_html is None and not work_meta.get("strict_section_alignment", False):
                        raw_html = ch_data.get("1")
                    if raw_html is None:
                        # This edition genuinely has no content at this card --
                        # e.g. Muller never splits 2.8 into 8/8a, so his "8a" row
                        # would be empty. Skip the INSERT rather than storing a
                        # placeholder string: this makes "a text_segments row
                        # exists for (passage_urn, version_short_id)" a clean,
                        # queryable presence signal (used client-side to grey out
                        # TOC buttons the current Focus edition doesn't have real
                        # content for), instead of requiring the client to
                        # string-match a hardcoded "missing" message. The client
                        # decides what, if anything, to display for the gap.
                        continue
                    cursor.execute("""
                        INSERT OR REPLACE INTO text_segments (passage_urn, version_short_id, content_html)
                        VALUES (?, ?, ?);
                    """, (passage_urn, v_id, raw_html))

    conn.commit()
    return _pending_metrical, WORK_HAS_BOOKS


# ── Phase 2: treebank sentences + metrical lines ────────────────────────────
def ingest_treebank_and_metrical(conn, target_keys, pending_metrical, work_has_books):
    cursor = conn.cursor()
    _pending_metrical = pending_metrical
    WORK_HAS_BOOKS = work_has_books
    print("\nIngesting treebank and metrical data...")
    for work_key in target_keys:
        work_meta = WORK_REGISTRY[work_key]
        tg = work_meta["textgroup"]
        wk = work_meta["work"]

        # Build card intervals once per work (needed by both treebank and metrical)
        tb_card_intervals = None
        if any(c.get("parse_mode") == "poetry_cards"
               for c in work_meta.get("editions", {}).values()):
            try:
                # Include translations (not just editions) so a base edition with
                # no milestones/poem-divs can still fall back to a companion
                # card_prose translation's @corresp anchors (see the corresp
                # tier in build_poetry_canonical_intervals) -- matches what the
                # main poetry-rendering loop below passes via editions_combined.
                _tb_editions_combined = {}
                for _cat in ("editions", "appcrits", "translations", "commentaries", "scholia"):
                    _tb_editions_combined.update(work_meta.get(_cat, {}))
                tb_card_intervals = build_poetry_canonical_intervals(_tb_editions_combined)
                tb_card_intervals = [iv for bk in tb_card_intervals.values() for iv in bk]
                print(f"  ↳ {work_key}: {len(tb_card_intervals)} card intervals")
            except Exception as e:
                print(f"  ⚠ Could not build card intervals for {work_key}: {e}")

        # ── Treebank sentences ────────────────────────────────────────────
        for v_id, cfg in work_meta.get("treebanks", {}).items():
            p_mode = cfg.get("parse_mode")
            if p_mode == "conllu":
                sentences, doc_credits = parse_conllu_treebank(cfg["path"], v_id, tg, wk,
                                                  card_intervals=tb_card_intervals,
                                                  has_books=WORK_HAS_BOOKS.get(work_key, True))
            elif p_mode == "agdt_xml":
                sentences, doc_credits = parse_agdt_treebank(cfg["path"], v_id, tg, wk,
                                                  card_intervals=tb_card_intervals)
            else:
                print(f"  ✗ {v_id}: unsupported treebank parse_mode {p_mode!r}")
                continue
            speakers  = parse_speakers_csv(cfg.get("speakers_csv", ""))
            cursor.execute("""
                INSERT OR REPLACE INTO treebank_doc_credits
                (textgroup, work, version_short_id, source_repo, credits_json)
                VALUES (?, ?, ?, ?, ?)
            """, (tg, wk, v_id, cfg.get("source_repo"),
                  json.dumps(doc_credits.get('annotators', []), ensure_ascii=False)))
            for sent in sentences:
                if not sent.get('subdoc'): continue
                cursor.execute("""
                    INSERT INTO treebank_sentences
                    (textgroup, work, version_short_id, subdoc, chapter, section, book,
                     sentence_json, prose_translation, literal_translation, transliteration,
                     credits_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tg, wk, v_id, sent['subdoc'], sent['chapter'], sent.get('section') or '1', sent.get('book'),
                      json.dumps(sent['tokens'], ensure_ascii=False),
                      sent.get('prose'), sent.get('literal'), sent.get('translit'),
                      json.dumps(sent['credits'], ensure_ascii=False) if sent.get('credits') else None))
                if sent['subdoc'] in speakers:
                    cursor.execute("""
                        INSERT INTO treebank_speakers (textgroup, work, subdoc, speaker)
                        VALUES (?, ?, ?, ?)
                    """, (tg, wk, sent['subdoc'], speakers[sent['subdoc']]))
            print(f"  ✓ {v_id}: {len(sentences)} sentences ingested"
                  + (f" ({len(doc_credits.get('annotators', []))} doc-level annotator(s))"
                     if doc_credits.get('annotators') else ""))

        # ── Metrical lines ────────────────────────────────────────────────
        if work_key in _pending_metrical:
            if not tb_card_intervals:
                print(f"  ⚠ No card intervals for {work_key} — metrical chapters will use book number")
            _m_line_to_card = {}
            if tb_card_intervals:
                for _iv in tb_card_intervals:
                    try:
                        _bk = str(_iv['book'])
                        _s  = int(_iv['label'].split('-')[0])
                        _e  = int(_iv['label'].split('-')[1])
                        for _ln in range(_s, _e + 1):
                            _m_line_to_card[f"{_bk}.{_ln}"] = _iv['label']
                    except (ValueError, KeyError):
                        continue
            for v_id, entry in _pending_metrical[work_key].items():
                rows_inserted = 0
                for line_ref, words in entry["lines_data"].items():
                    # book is the citation's own leading BOOK.LINE component --
                    # already normalized (parse_metrical_tsv strips zero-padding)
                    # and guaranteed present, so no separate lookup needed. This
                    # is what metricalForChapter's SQL query now filters on
                    # alongside chapter: chapter labels ("1-15" etc.) are built
                    # independently per book and collide constantly across a
                    # 48-book work, so chapter alone can't disambiguate which
                    # book's rows a query should return -- see the shard_loader
                    # patch in Cell 2c/app.js for the other half of this fix.
                    book = line_ref.split('.')[0]
                    chapter = _m_line_to_card.get(line_ref, book)
                    cursor.execute(
                        "INSERT INTO metrical_lines "
                        "(textgroup, work, version_short_id, line_ref, book, chapter, line_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (tg, wk, v_id, line_ref, book, chapter, json.dumps(words, ensure_ascii=False))
                    )
                    rows_inserted += 1
                print(f"  ✓ {v_id}: {rows_inserted} metrical lines inserted")
    conn.commit()

# ── Phase 3: cross-version token alignments ─────────────────────────────────
def ingest_token_alignments(conn, target_keys):
    cursor = conn.cursor()
    # The monolith is persistent across incremental builds. Upgrade older
    # copies in place before authored bridge metadata is inserted; relying on
    # init_storage_engine alone only migrates brand-new databases.
    _columns = {row[1] for row in cursor.execute("PRAGMA table_info(token_alignments)")}
    if "meta_json" not in _columns:
        cursor.execute("ALTER TABLE token_alignments ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'")
    print("\nIngesting token alignment files...")
    for work_key in target_keys:
        work_meta = WORK_REGISTRY[work_key]
        tg = work_meta["textgroup"]
        wk = work_meta["work"]
        for pair_id, aln_cfg in work_meta.get("alignments", {}).items():
            aln_path = aln_cfg["path"]
            if not os.path.exists(aln_path):
                print(f"  ✗ {pair_id}: file not found at {aln_path}")
                continue
            with open(aln_path, encoding="utf-8") as f:
                aln_data = json.load(f)
            meta     = aln_data.get("alignment_meta", {})
            segments = aln_data.get("segments", {})
            src_ver  = aln_cfg["src_version"]
            tgt_ver  = aln_cfg["tgt_version"]
            rows = 0
            for seg_id, seg in segments.items():
                for grp in seg.get("alignments", []):
                    cursor.execute("""
                        INSERT INTO token_alignments
                        (textgroup, work, pair_id, src_version, tgt_version,
                         segment, src_indices, tgt_indices, src_tokens, tgt_tokens, score, meta_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        tg, wk, pair_id, src_ver, tgt_ver, seg_id,
                        json.dumps(grp["src_indices"]),
                        json.dumps(grp["tgt_indices"]),
                        json.dumps(grp.get("src_tokens", [])),
                        json.dumps(grp.get("tgt_tokens", [])),
                        grp["score"],
                        json.dumps(grp.get("meta", {}), ensure_ascii=False)
                    ))
                    rows += 1
            conn.commit()
            print(f"  ✓ {pair_id}: {len(segments)} segments, {rows} alignment groups ingested")

# ── Phase 4: edition line-alignment crosswalks ──────────────────────────────
def ingest_edition_alignments(conn, target_keys):
    cursor = conn.cursor()
    print("\nIngesting edition line-alignment files...")
    for work_key in target_keys:
        work_meta = WORK_REGISTRY[work_key]
        for tsv in work_meta.get("edition_alignments", []):
            if not os.path.exists(tsv):
                print(f"  ✗ edition alignment: file not found at {tsv}")
                continue
            ingest_edition_alignment(conn, tsv)
    conn.commit()


# ── Top-level orchestrator ──────────────────────────────────────────────────
def ingest_works(conn, work_keys=None, delete_existing=True):
    """Ingest one work, a subset, or (work_keys=None) everything in
    WORK_REGISTRY, into an already-open monolith connection. Safe to call
    repeatedly against the SAME persistent connection/file -- each call
    only touches the rows belonging to target_keys.
    """
    target_keys = work_keys or list(WORK_REGISTRY.keys())

    if delete_existing:
        _delete_existing_rows(conn, target_keys)

    pending_metrical, work_has_books = ingest_editions_and_structure(conn, target_keys)
    ingest_treebank_and_metrical(conn, target_keys, pending_metrical, work_has_books)
    ingest_token_alignments(conn, target_keys)
    ingest_edition_alignments(conn, target_keys)
    flatten_treebank_tokens(conn, target_keys)
    conn.commit()
    return work_has_books
