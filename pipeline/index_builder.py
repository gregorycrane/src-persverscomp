"""Rebuilds index.html from the monolith. Relocated from Cell 10, wrapped
as rebuild(). Needs a COMPLETE monolith (all works, not just changed ones)
since it aggregates GLOBAL_REGISTRIES/GLOBAL_STRUCTURES across the whole
corpus -- that's exactly what reconstitute.py exists to guarantee is
present even when only one work was just re-ingested.

PATH FIX vs. the original notebook cell: WEB_SRC used to resolve as
Path("web") -- relative to the CWD the notebook happened to be launched
from -- with a fallback to WORKSPACE_DIR / "web" that doesn't actually
match this repo's real layout (web/ lives under SRC_DIR, not
WORKSPACE_DIR). Both were CWD-dependent or wrong; this version resolves
web/ from SRC_DIR directly, so it works regardless of where this module is
imported from or run.
"""
import json
import sqlite3
from pathlib import Path
from pipeline.config import WORKSPACE_DIR, BUILD_DIR, DB_PATH, SRC_DIR


def _merge_catalog_only_versions(structures, registries):
    """Add published overlay works and versions that live outside the monolith."""
    catalog_path = WORKSPACE_DIR / "site" / "catalog.json"
    if not catalog_path.exists():
        return
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for work_key, meta in catalog.get("works", {}).items():
        if meta.get("experimental_fragment"):
            structures[work_key] = [str(chapter) for part in meta.get("parts", [])
                                    for chapter in part.get("chapters", [])]
        for version in meta.get("versions", []):
            canonical_id = version.get("canonical_id")
            if not canonical_id or canonical_id in registries:
                continue
            registries[canonical_id] = {
                "urn": version["urn"], "label": version["label"],
                "class": version["text_class"], "textgroup": meta["textgroup"],
                "work": meta["work"], "short_id": version["short_id"],
                "doc_type": version["doc_type"],
                "source_version": version.get("source_version"),
                "source_certainty": version.get("source_certainty"),
                "source_note": version.get("source_note"),
                "translation_of": version.get("translation_of"),
            }

def rebuild(conn=None):
    """Rebuild index.html (+ README.md, .nojekyll) from the monolith at
    DB_PATH. Pass an open connection to reuse one from a build_all.py run;
    otherwise opens DB_PATH itself (must be a complete, all-works monolith
    -- see module docstring).
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Monolith not found at {DB_PATH}. Run Cell 1 (build) - it now writes to the temp build dir, not the repo.")

    conn = conn or sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 1. Dynamically reconstruct GLOBAL_REGISTRIES from text_units table
    cursor.execute("SELECT canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type, source_version, source_certainty, source_note, translation_of FROM text_units")
    extracted_registries = {}
    for row in cursor.fetchall():
        extracted_registries[row[0]] = {
            "urn": row[1],
            "label": row[2],
            "class": row[3],
            "textgroup": row[4],
            "work": row[5],
            "short_id": row[6],
            "doc_type": row[7],
            "source_version": row[8],
            "source_certainty": row[9],
            "source_note": row[10],
            "translation_of": row[11]
        }

    # 2. Dynamically reconstruct GLOBAL_STRUCTURES from alignment_grid table
    extracted_structures = {}
    cursor.execute("SELECT DISTINCT textgroup || '.' || work FROM alignment_grid")
    work_keys = [r[0] for r in cursor.fetchall() ]
    for w_key in work_keys:
        tg, wk = w_key.split('.')
    
        # Check if this work uses multi-book navigation or a flat structure
        cursor.execute("SELECT DISTINCT book FROM alignment_grid WHERE textgroup=? AND work=? AND book IS NOT NULL", (tg, wk))
        books = [r[0] for r in cursor.fetchall()]
    
        if books:
            # Multi-book configuration (e.g., Thucydides)
            book_map = {}
            # int(x) if x.isdigit() else x returns EITHER an int or a str
            # depending on the value, which crashes the instant `books` mixes
            # numeric and non-numeric labels (Python 3 won't compare across
            # types). Tuple key instead: numeric books sort first by real value,
            # non-numeric ones after by string -- the two groups only ever
            # compare their leading 0/1 flag against each other, never int
            # against str directly.
            for bk in sorted(books, key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x))):
                cursor.execute("SELECT DISTINCT chapter FROM alignment_grid WHERE textgroup=? AND work=? AND book=? ORDER BY sort_order", (tg, wk, bk))
                book_map[bk] = [r[0] for r in cursor.fetchall()]
            extracted_structures[w_key] = book_map
        else:
            # Flat configuration (e.g., Aristotle, Sophocles)
            cursor.execute("SELECT DISTINCT chapter FROM alignment_grid WHERE textgroup=? AND work=? ORDER BY sort_order", (tg, wk))
            extracted_structures[w_key] = [r[0] for r in cursor.fetchall()]

    # 3. Extract treebank sentences keyed by work+version+chapter
    extracted_treebanks = {}   # { "tg.wk/v_id": { chapter: [ {subdoc, tokens, prose, literal}, ...] } }
    extracted_speakers  = {}   # { "tg.wk/v_id": { subdoc: speaker } }

    # Guard: treebank tables only exist if Cell 1 was run with treebank support
    _tb_tables = {r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('treebank_sentences','treebank_speakers')"
    ).fetchall()}

    if 'treebank_sentences' in _tb_tables:
        cursor.execute("""
            SELECT textgroup, work, version_short_id, subdoc, chapter, section,
                   sentence_json, prose_translation, literal_translation
            FROM treebank_sentences
            ORDER BY textgroup, work, version_short_id, id
        """)
        for row in cursor.fetchall():
            tg2, wk2, vid, subdoc, chapter, section, sjson, prose, literal = row
            key = f"{tg2}.{wk2}/{vid}"
            if key not in extracted_treebanks:
                extracted_treebanks[key] = {}
            if chapter not in extracted_treebanks[key]:
                extracted_treebanks[key][chapter] = []
            extracted_treebanks[key][chapter].append({
                "subdoc": subdoc,
                "section": section,
                "tokens": json.loads(sjson),
                "prose": prose,
                "literal": literal,
            })
        print(f"  ✓ Extracted treebank data: {sum(sum(len(v) for v in ch.values()) for ch in extracted_treebanks.values())} sentences")
    else:
        print("  ⚠ treebank_sentences table not found — run Cell 1 to ingest treebanks")

    if 'treebank_speakers' in _tb_tables:
        cursor.execute("SELECT textgroup, work, subdoc, speaker FROM treebank_speakers")
        for row in cursor.fetchall():
            tg2, wk2, subdoc, speaker = row
            skey = f"{tg2}.{wk2}"
            if skey not in extracted_speakers:
                extracted_speakers[skey] = {}
            extracted_speakers[skey][subdoc] = speaker

    # 4. Extract metrical lines keyed by work+version+book+chapter
    extracted_metrics = {}  # { "tg.wk/v_id": { book: { chapter: { line_ref: [words] } } } }
    _mt_tables = {r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='metrical_lines'"
    ).fetchall()}
    if 'metrical_lines' in _mt_tables:
        cursor.execute("""
            SELECT textgroup, work, version_short_id, line_ref, book, chapter, line_json
            FROM metrical_lines
            ORDER BY textgroup, work, version_short_id, id
        """)
        for row in cursor.fetchall():
            tg2, wk2, vid, line_ref, book, chapter, ljson = row
            mkey = f"{tg2}.{wk2}/{vid}"
            if mkey not in extracted_metrics:
                extracted_metrics[mkey] = {}
            if book not in extracted_metrics[mkey]:
                extracted_metrics[mkey][book] = {}
            if chapter not in extracted_metrics[mkey][book]:
                extracted_metrics[mkey][book][chapter] = {}
            extracted_metrics[mkey][book][chapter][line_ref] = json.loads(ljson)
        total_ml = sum(sum(len(ch) for bk in wk.values() for ch in bk.values())
                       for wk in extracted_metrics.values())
        print(f"  \u2713 Extracted metrical data: {total_ml} lines")
    else:
        print("  \u26a0 metrical_lines table not found \u2014 run Cell 1 to ingest")

    # 5. Extract token alignment pairs
    # Structure: { "tg.wk": { "pair_id": { "label": "...", "src_version": "...", "tgt_version": "...",
    #                           "segments": { "1.1": [ {src_indices, tgt_indices, src_tokens, tgt_tokens, score}, ...] } } } }
    extracted_alignments = {}

    _aln_tables = {r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_alignments'"
    ).fetchall()}

    if 'token_alignments' in _aln_tables:
        # Load alignment pair metadata from work registry (stored in WORK_REGISTRY in cell 0,
        # but we re-derive it here from the DB content so cell 2 stays self-contained)
        cursor.execute("""
            SELECT DISTINCT textgroup, work, pair_id, src_version, tgt_version
            FROM token_alignments
        """)
        pair_rows = cursor.fetchall()
        for tg2, wk2, pair_id, src_ver, tgt_ver in pair_rows:
            wkey = f"{tg2}.{wk2}"
            extracted_alignments.setdefault(wkey, {})
            extracted_alignments[wkey][pair_id] = {
                "src_version": src_ver,
                "tgt_version": tgt_ver,
                "segments": {}
            }
            cursor.execute("""
                SELECT segment, src_indices, tgt_indices, src_tokens, tgt_tokens, score, meta_json
                FROM token_alignments
                WHERE textgroup=? AND work=? AND pair_id=?
                ORDER BY segment, id
            """, (tg2, wk2, pair_id))
            for row in cursor.fetchall():
                seg_id = row[0]
                extracted_alignments[wkey][pair_id]["segments"].setdefault(seg_id, [])
                extracted_alignments[wkey][pair_id]["segments"][seg_id].append({
                    "s": json.loads(row[1]),   # src_indices
                    "t": json.loads(row[2]),   # tgt_indices
                    "st": json.loads(row[3]),  # src_tokens
                    "tt": json.loads(row[4]),  # tgt_tokens
                    "sc": round(row[5], 4),    # score
                    "meta": json.loads(row[6] or "{}")
                })


    # ── Alignment extraction summary ──────────────────────────────────────────
    if extracted_alignments:
        for wk, pairs in extracted_alignments.items():
            for pid, pdata in pairs.items():
                n_segs = len(pdata.get("segments", {}))
                n_groups = sum(len(g) for g in pdata["segments"].values())
                print(f"  ✓ Alignments [{wk}] {pid}: {n_segs} segments, {n_groups} groups")
    else:
        print("  ⚠ No alignment data found in DB.")
        print("    → Did you re-run Cell 0 after adding the 'alignments' keys to WORK_REGISTRY?")
        print("    → Check that the JSON files exist at the paths in WORK_REGISTRY.")

    _merge_catalog_only_versions(extracted_structures, extracted_registries)

    # Serialize configurations directly into JS injection tokens
    struct_map_json      = json.dumps(extracted_structures)
    text_registry_json   = json.dumps(extracted_registries)
    # v39: the heavy annotation layers (treebank / speakers / metrical / alignments)
    # are NO LONGER inlined into index.html. They already live in
    # corpus_alignment_grid.db, which the page loads at startup, and are read on
    # demand by the DB-backed accessors in the app (see the accessor block below).
    # The extracted_* dicts are kept only for the console summary prints; the
    # *_REPLACE tokens for these four layers were removed from the HTML template,
    # so these strings inject nothing.
    treebank_data_json   = '{}'
    speakers_data_json   = '{}'
    metrics_data_json    = '{}'
    alignment_data_json  = '{}'


    # ── 1. Compile Repository README.md Asset ─────────────────────
    README_MD_CONTENT = """# Perseus 6 -- Serverless Prototype

    Our goal is to provide public facing versions of the Perseus Digital Library that can run for as long as possible with minimal -- and ideally no -- changes. The Canadian [Endings Project](https://endings.uvic.ca/) provided an initial inspiration for this work but it was not clear to me whether this approach could accommodate the demands of the Perseus Digital Library. In his contributions to the Ajax Multicommentary Project, Charles Pletcher, however, created a [minimal computing version of this challenging philological use case](https://multi.ajmc.ch/passages/urn:cts:greekLit:tlg0011.tlg003:1-133). Pletcher's work made it clear that we could build every feature of the Perseus Digital Library, current and planned, in format that Tufts could serve far more easily than the traditional serverb-based versions of Perseus and that was designed to run, securely and without modification,for a long period of time. 

    In summer 2026, there are two serverless Perseus efforts. Peter Nadel, Charles Pletcher, and Clifford Wulfman are working on a Minimum Viable Perseus (MVP) -- essentially a replacement for Perseus 4: the Hopper, a version that David Mimno first designed in 2003, that was developed through 2013 and has been running on virtual servers unchanged ever since. Minimum Viable Perseus aims to provide the functionality of Perseus 4 for all Perseus textual data -- essentially, MVP provides a streamlined digital library that can be updated and expanded over time.

    In 2018, support from the Alexander von Humboldt Foundation allowed us to create Perseus 5: the Scaife Viewer. Scaife did not fully replicate the core functionality of Perseus 4 - it did not include the morphological services, dictionary lookups or commentaries that Scaife now supports -- but it did provide us with scalable reading environment that we could update and expand. 

    Support from the Mellon Foundation, Harvard's Center for Hellenic Studies, the National Endowment for the Humanities, and Tufts University allowed us to prototype a next generation version of the Perseus Digital Library, one that built on the 2018 Scaife Viewer. Support from Schmidt Sciences has allowed us to carry this work forward and to build this experimental serverless implementation.

    An NEH-funded project to create a digital edition of Aristotle's Poetics in Greek, Arabic and Latin has the driving force behind this particular effort to build a Perseus 6. We needed to be able to compare multiple versions of the Poetics, to include commentaries, to show word and phrase alignments between source texts and translations and to provide the rich linguistic annotations that treebanks in Greek, Latin and other languages have begun to make available.

    Using Claude and Gemini, Gregory Crane developed the basic version of this Serverless Perseus 6 over ten days. We are are using GitHub Pages both because GitHub Pages can publish the front end work and because the constraints of GitHub Pages help us develop something sufficiently secure and lightweight that Tufts University -- and other institutions -- could easily host. Storage limits will prevent us from hosting the entire content of Perseus 6 on GitHub pages but the 1 gigabyte limitation should allow us to include enough content that we can thoroughly test the architecture and prepare for a complete implementation at Tufts.

    ## Infrastructure Sustainability Paradigm

    Rather than relying on a continuous, monolithic server daemon—or fragmenting the corpus into hundreds of thousands of brittle static chunks strewn across a fragile local filesystem—durable architecture calls for a **decentralized, serverless delivery model**. The corpus is compiled into many small, self-contained binary shards: one read-only SQLite database per work, each holding all of that work's editions, translations, commentaries, and annotation layers, arranged as a flat directory tree addressed directly by CTS URN. Because SQLite's on-disk format is openly documented and exceptionally long-lived, every shard is a preservation-grade asset, and the deployed corpus is simply a tree of such files that can be copied, mirrored, or checksummed wholesale.

    Since each shard is small, the client fetches only the single work it needs—whole—and queries it in the browser through WebAssembly, with no byte-range paging, no special server behavior, and no headers to tune. That property is what makes the system genuinely portable: it runs identically on a globally distributed object store, an institutional web server, or a researcher's laptop behind any static file server, with no backend process, no database daemon, and no writable endpoint to maintain or attack. The result is a robust, replicable foundation for permanent digital philology that scales gracefully—simply by adding shards—toward the full extent of the textual record."""
    (WORKSPACE_DIR / "README.md").write_text(README_MD_CONTENT, encoding='utf-8')


    # ── 2. Compile Branded HTML Workspace Application ──────────────
    # ── Front-end source lives as real files under web/ (no Python-string escaping) ──
    # Edit web/styles.css, web/app.js, web/index_shell.html directly: backslashes, regexes
    # and quotes are authored normally. This cell only assembles them and injects the
    # DB-derived JSON, producing a byte-identical index.html to the previous inline version.
    # was: WEB_SRC = Path("web")  (CWD-dependent) with a WORKSPACE_DIR/"web"
    # fallback that doesn't match this repo's real layout -- web/ lives under
    # SRC_DIR, not WORKSPACE_DIR. Resolve from SRC_DIR directly instead.
    WEB_SRC = SRC_DIR / "web"
    if not (WEB_SRC / "index_shell.html").exists():
        raise FileNotFoundError(
            f"index_shell.html not found under {WEB_SRC}. Expected web/ at "
            f"{SRC_DIR / 'web'} (SRC_DIR / 'web')."
        )
    _shell  = open(WEB_SRC / "index_shell.html", encoding="utf-8", newline="").read()
    _styles = open(WEB_SRC / "styles.css",       encoding="utf-8", newline="").read()
    _app_js = open(WEB_SRC / "app.js",           encoding="utf-8", newline="").read()
    # Optional, URL-gated collections trial. Default routes remain unchanged.
    if (WEB_SRC / "fragment-collections.js").exists():
        _styles += (WEB_SRC / "fragment-collections.css").read_text(encoding="utf-8")
        _app_js = (WEB_SRC / "fragment-collections.js").read_text(encoding="utf-8") + "\n" + _app_js
    INDEX_HTML_CONTENT = (
        _shell
        .replace("%%PERSEUS_STYLES%%", _styles)
        .replace("%%PERSEUS_APP_JS%%", _app_js)
        .replace("STRUCT_REPLACE",    struct_map_json)
        .replace("REGISTRY_REPLACE",  text_registry_json)
        .replace("TREEBANK_REPLACE",  treebank_data_json)
        .replace("SPEAKERS_REPLACE",  speakers_data_json)
        .replace("METRICAL_REPLACE",  metrics_data_json)
        .replace("ALIGNMENT_REPLACE", alignment_data_json)
    )

    (WORKSPACE_DIR / "index.html").write_text(INDEX_HTML_CONTENT, encoding='utf-8')
    (WORKSPACE_DIR / ".nojekyll").write_text("", encoding='utf-8')
    print("[SUCCESS] Production Standalone Workspace compiled cleanly.")
    return WORKSPACE_DIR / "index.html"
