
    // Explicitly anchor framework mechanics to top-level global window references
    window.SQL_WASM_ENGINE = null;
    window.dbInstance = null;

    const GLOBAL_STRUCTURES = STRUCT_REPLACE;
    const TEXT_REGISTRY    = REGISTRY_REPLACE;
    // ── Lazy, DB-backed annotation accessors (v39) ─────────────────────────
    // The loaded corpus DB (window.dbInstance) already contains every annotation
    // layer: treebank_sentences, treebank_speakers, metrical_lines,
    // token_alignments. Earlier builds ALSO inlined that same data as large JSON
    // blobs in this HTML file, shipping it to the browser twice. v39 drops the
    // inlined copies and reads each layer on demand from the DB, caching per
    // work/version. The objects returned below have exactly the same shape as the
    // old inlined globals (TREEBANK_DATA / SPEAKERS_DATA / METRICAL_DATA /
    // GLOBAL_ALIGNMENTS), so every downstream call site is unchanged.
    function _dbRows(sql, params) {
        const db = window.dbInstance;
        if (!db) return [];
        let res;
        try { res = db.exec(sql, params || []); }
        catch (e) { console.warn("annotation query failed:", e); return []; }
        if (!res.length) return [];
        const cols = res[0].columns;
        return res[0].values.map(row => {
            const o = {}; cols.forEach((c, i) => { o[c] = row[i]; }); return o;
        });
    }
    function _jp(s, fb) { try { return JSON.parse(s); } catch (e) { return fb; } }

    // ── Greek transliteration engine (client-side, no precomputation) ──────
    // Converts polytonic Greek Unicode text into Latin transliteration on the
    // fly. Two modes:
    //   'simple' — plain ASCII-ish reading form, no accents/breathing marks
    //              shown as diacritics, macrons dropped (e ~ eta, o ~ omega).
    //   'full'   — scholarly form: acute/grave/circumflex accents rendered as
    //              combining diacritics on the corresponding Latin vowel,
    //              long eta/omega marked with a macron (ē/ō), iota subscript
    //              shown as an appended -i, rough breathing as h-/rh-.
    // Works directly on HTML strings: it only rewrites contiguous runs of
    // Greek-range codepoints, so tags/attributes/entities pass through untouched.
    const GK_SMOOTH      = '\u0313';
    const GK_ROUGH        = '\u0314';
    const GK_ACUTE        = '\u0301';
    const GK_GRAVE        = '\u0300';
    const GK_CIRCUMFLEX_A = '\u0342'; // perispomeni
    const GK_CIRCUMFLEX_B = '\u0303'; // combining tilde (occasional alt encoding)
    const GK_IOTA_SUB     = '\u0345'; // ypogegrammeni
    const GK_DIAERESIS    = '\u0308';
    const GK_MACRON       = '\u0304';
    const GK_BREVE        = '\u0306';
    const GK_COMBINING_MARKS = new Set([
        GK_SMOOTH, GK_ROUGH, GK_ACUTE, GK_GRAVE, GK_CIRCUMFLEX_A, GK_CIRCUMFLEX_B,
        GK_IOTA_SUB, GK_DIAERESIS, GK_MACRON, GK_BREVE
    ]);

    const GREEK_BASE_LETTERS = {
        'α': { s: 'a',  f: 'a'  }, 'β': { s: 'b',  f: 'b'  }, 'γ': { s: 'g',  f: 'g'  },
        'δ': { s: 'd',  f: 'd'  }, 'ε': { s: 'e',  f: 'e'  }, 'ζ': { s: 'z',  f: 'z'  },
        'η': { s: 'e',  f: 'ē'  }, 'θ': { s: 'th', f: 'th' }, 'ι': { s: 'i',  f: 'i'  },
        'κ': { s: 'k',  f: 'k'  }, 'λ': { s: 'l',  f: 'l'  }, 'μ': { s: 'm',  f: 'm'  },
        'ν': { s: 'n',  f: 'n'  }, 'ξ': { s: 'x',  f: 'x'  }, 'ο': { s: 'o',  f: 'o'  },
        'π': { s: 'p',  f: 'p'  }, 'ρ': { s: 'r',  f: 'r'  }, 'σ': { s: 's',  f: 's'  },
        'ς': { s: 's',  f: 's'  }, 'τ': { s: 't',  f: 't'  }, 'υ': { s: 'u',  f: 'u'  },
        'φ': { s: 'ph', f: 'ph' }, 'χ': { s: 'kh', f: 'kh' }, 'ψ': { s: 'ps', f: 'ps' },
        'ω': { s: 'o',  f: 'ō'  },
    };
    const GREEK_DIPHTHONGS = {
        'αι': { s: 'ai', f: 'ai' }, 'ει': { s: 'ei', f: 'ei' }, 'οι': { s: 'oi', f: 'oi' },
        'υι': { s: 'ui', f: 'ui' }, 'αυ': { s: 'au', f: 'au' }, 'ευ': { s: 'eu', f: 'eu' },
        'ηυ': { s: 'eu', f: 'ēu' }, 'ου': { s: 'ou', f: 'ou' },
    };
    const GREEK_PUNCT_MAP = {
        '\u037E': '?',   // Greek question mark
        '\u0387': ';',   // ano teleia
        '\u1FBD': "'",   // koronis (elision)
        '\u1FBF': "'",   // psili used standalone
        '\u1FFE': "'",   // dasia used standalone
    };
    const GK_LATIN_VOWELS = 'aeiouyēō';

    function _gkGroupLetters(nfdStr) {
        const letters = [];
        for (const ch of nfdStr) {
            if (GK_COMBINING_MARKS.has(ch) && letters.length) {
                letters[letters.length - 1].marks.push(ch);
            } else {
                letters.push({ base: ch, marks: [] });
            }
        }
        return letters;
    }

    function _gkMergeDiphthongs(letters) {
        const out = [];
        for (let i = 0; i < letters.length; i++) {
            const cur = letters[i];
            const nxt = letters[i + 1];
            if (nxt) {
                const curLower = cur.base.toLowerCase();
                const nxtLower = nxt.base.toLowerCase();
                const pairKey = curLower + nxtLower;
                const hasDiaeresis = nxt.marks.includes(GK_DIAERESIS);
                const curHasIotaSub = cur.marks.includes(GK_IOTA_SUB);
                if (GREEK_DIPHTHONGS[pairKey] && !hasDiaeresis && !curHasIotaSub) {
                    out.push({
                        diphthong: pairKey,
                        marks: cur.marks.concat(nxt.marks),
                        isUpper: cur.base !== curLower,
                    });
                    i++; // consumed the second vowel
                    continue;
                }
            }
            out.push({ base: cur.base, marks: cur.marks, isUpper: cur.base !== cur.base.toLowerCase() });
        }
        return out;
    }

    function _gkInsertAccent(str, accentMark) {
        // Greek writes the accent over a diphthong's second vowel (e.g. αἵ ->
        // haî, not hâi), so scan from the end and mark the last Latin vowel.
        for (let i = str.length - 1; i >= 0; i--) {
            if (GK_LATIN_VOWELS.includes(str[i])) {
                return str.slice(0, i + 1) + accentMark + str.slice(i + 1);
            }
        }
        return str + accentMark;
    }

    function _gkRenderUnit(unit, mode, nextBaseLower) {
        let latin;
        if (unit.diphthong) {
            const d = GREEK_DIPHTHONGS[unit.diphthong];
            latin = (mode === 'full') ? d.f : d.s;
        } else {
            const lower = unit.base.toLowerCase();
            const entry = GREEK_BASE_LETTERS[lower];
            if (!entry) {
                // Not a recognized Greek letter (punctuation, space, markup char).
                return (GREEK_PUNCT_MAP[unit.base] !== undefined) ? GREEK_PUNCT_MAP[unit.base] : unit.base;
            }
            latin = (mode === 'full') ? entry.f : entry.s;
            if (lower === 'γ' && nextBaseLower && 'γκξχ'.includes(nextBaseLower)) {
                latin = 'n'; // gamma nasal (ἄγγελος -> angelos)
            }
            if (lower === 'ρ') {
                latin = unit.marks.includes(GK_ROUGH) ? 'rh' : 'r';
            }
        }
        const isRho = !unit.diphthong && unit.base.toLowerCase() === 'ρ';
        if (!isRho && unit.marks.includes(GK_ROUGH)) {
            latin = 'h' + latin;
        }
        if (mode === 'full') {
            if (unit.marks.includes(GK_ACUTE)) latin = _gkInsertAccent(latin, GK_ACUTE);
            else if (unit.marks.includes(GK_GRAVE)) latin = _gkInsertAccent(latin, GK_GRAVE);
            else if (unit.marks.includes(GK_CIRCUMFLEX_A) || unit.marks.includes(GK_CIRCUMFLEX_B)) latin = _gkInsertAccent(latin, '\u0302');
            if (unit.marks.includes(GK_IOTA_SUB)) latin += 'i';
        }
        if (unit.isUpper) latin = latin.charAt(0).toUpperCase() + latin.slice(1);
        return latin;
    }

    function transliterateGreekWord(word, mode) {
        const nfd = word.normalize('NFD');
        const letters = _gkGroupLetters(nfd);
        const units = _gkMergeDiphthongs(letters);
        let result = '';
        for (let i = 0; i < units.length; i++) {
            const nxt = units[i + 1];
            const nextBaseLower = nxt ? (nxt.diphthong ? nxt.diphthong[0] : nxt.base.toLowerCase()) : null;
            result += _gkRenderUnit(units[i], mode, nextBaseLower);
        }
        return result.normalize('NFC');
    }

    // Matches contiguous runs of Greek/Coptic + Greek Extended codepoints
    // (letters, breathing/accent marks, and Greek-specific punctuation).
    // Anything outside these ranges — HTML tags, attributes, English text,
    // ASCII punctuation — is left completely untouched.
    const GREEK_RUN_REGEX = /[\u0370-\u03FF\u1F00-\u1FFF]+/gu;
    // Non-global sibling used purely for "does this contain any Greek at all"
    // checks (a global regex's .test() mutates lastIndex between calls, which
    // would silently break repeated presence checks across renders).
    const GREEK_HAS_REGEX = /[\u0370-\u03FF\u1F00-\u1FFF]/u;

    function transliterateHtmlFragment(html, mode) {
        if (!mode) return html;
        return html.replace(GREEK_RUN_REGEX, (run) => transliterateGreekWord(run, mode));
    }

    // Re-derives a column's displayed HTML from its stored native-Greek
    // snapshot, applying (or clearing) transliteration without touching the DB.
    // Walks a live DOM subtree and transliterates (or restores) its text nodes
    // in place, without touching element structure — safe for parts of the
    // page (like the treebank view) that attach click handlers via
    // addEventListener rather than inline onclick, which innerHTML
    // replacement would silently destroy.
    function walkAndTransliterateNode(rootEl, mode) {
        if (!rootEl) return;
        const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, null);
        let node;
        while ((node = walker.nextNode())) {
            if (node.__gkOriginal === undefined) node.__gkOriginal = node.nodeValue;
            node.nodeValue = mode ? transliterateHtmlFragment(node.__gkOriginal, mode) : node.__gkOriginal;
        }
    }

    function applyGreekTransliteration(prefix) {
        const targetContainer = document.getElementById(`content_${prefix}`);
        if (!targetContainer) return;
        const mode = columnTranslitMode[prefix] || '';
        if (columnGreekOriginalHtml[prefix] !== undefined) {
            const original = columnGreekOriginalHtml[prefix];
            targetContainer.innerHTML = mode ? transliterateHtmlFragment(original, mode) : original;
        } else {
            walkAndTransliterateNode(targetContainer, mode);
        }
    }

    // Re-syncs a token detail panel (populated asynchronously on click, after
    // the column's initial transliteration pass already ran) to whatever
    // mode its column currently has selected.
    function _tbApplyTranslitToPanel(panel) {
        const containerEl = panel.closest && panel.closest('[id^="content_"]');
        if (!containerEl) return;
        const prefix = containerEl.id.slice(8);
        walkAndTransliterateNode(panel, columnTranslitMode[prefix] || '');
    }

    window.onTranslitModeChange = function(prefix, mode) {
        columnTranslitMode[prefix] = mode;
        applyGreekTransliteration(prefix);
    };

    // TREEBANK_DATA["tg.wk/vid"][chapter] -> [ {subdoc, section, tokens, prose, literal}, ... ]
    const _TB_CACHE = new Map();
    function _hydrateTreebank(tbKey) {
        if (_TB_CACHE.has(tbKey)) return _TB_CACHE.get(tbKey);
        if (!window.dbInstance) return null;            // not ready yet; don't cache
        const slash = tbKey.lastIndexOf("/");
        const [tg, work] = tbKey.slice(0, slash).split(".");
        const vid = tbKey.slice(slash + 1);
        const rows = _dbRows(
            "SELECT subdoc, section, chapter, sentence_json, prose_translation, literal_translation, transliteration, credits_json " +
            "FROM treebank_sentences WHERE textgroup=? AND work=? AND version_short_id=? ORDER BY id",
            [tg, work, vid]);
        let out = null;
        if (rows.length) {
            out = {};
            rows.forEach(r => {
                (out[r.chapter] = out[r.chapter] || []).push({
                    subdoc: r.subdoc, section: r.section,
                    tokens: _jp(r.sentence_json, []),
                    prose: r.prose_translation, literal: r.literal_translation,
                    translit: r.transliteration,
                    credits: _jp(r.credits_json, null)
                });
            });
        }
        _TB_CACHE.set(tbKey, out);
        return out;
    }
    const TREEBANK_DATA = new Proxy({}, {
        get: (_t, k) => (typeof k === "string" ? _hydrateTreebank(k) : undefined)
    });

    // TREEBANK_DOC_CREDITS["tg.wk/vid"] -> { annotators: [{name,address}], source: "..." }
    // Document-level fallback credits, used whenever a sentence doesn't carry
    // its own "# sentannotators" line (the common case).
    const _TB_CREDITS_CACHE = new Map();
    function _hydrateTreebankDocCredits(tbKey) {
        if (_TB_CREDITS_CACHE.has(tbKey)) return _TB_CREDITS_CACHE.get(tbKey);
        if (!window.dbInstance) return null;
        const slash = tbKey.lastIndexOf("/");
        const [tg, work] = tbKey.slice(0, slash).split(".");
        const vid = tbKey.slice(slash + 1);
        const rows = _dbRows(
            "SELECT source_repo, credits_json FROM treebank_doc_credits " +
            "WHERE textgroup=? AND work=? AND version_short_id=?",
            [tg, work, vid]);
        let out = { annotators: [], source: null };
        if (rows.length) {
            out = { annotators: _jp(rows[0].credits_json, []) || [], source: rows[0].source_repo || null };
        }
        _TB_CREDITS_CACHE.set(tbKey, out);
        return out;
    }
    const TREEBANK_DOC_CREDITS = new Proxy({}, {
        get: (_t, k) => (typeof k === "string" ? _hydrateTreebankDocCredits(k) : null)
    });

    // SPEAKERS_DATA["tg.wk"][subdoc] -> speaker
    const _SPK_CACHE = new Map();
    function _hydrateSpeakers(wKey) {
        if (_SPK_CACHE.has(wKey)) return _SPK_CACHE.get(wKey);
        if (!window.dbInstance) return {};              // not ready yet; don't cache
        const [tg, work] = wKey.split(".");
        const rows = _dbRows(
            "SELECT subdoc, speaker FROM treebank_speakers WHERE textgroup=? AND work=?",
            [tg, work]);
        const out = {};
        rows.forEach(r => { out[r.subdoc] = r.speaker; });
        _SPK_CACHE.set(wKey, out);
        return out;
    }
    const SPEAKERS_DATA = new Proxy({}, {
        get: (_t, k) => (typeof k === "string" ? _hydrateSpeakers(k) : {})
    });

    // METRICAL_DATA["tg.wk/vid"][chapter][line_ref] -> [words]
    const _MT_CACHE = new Map();
    function _hydrateMetrical(mKey) {
        if (_MT_CACHE.has(mKey)) return _MT_CACHE.get(mKey);
        if (!window.dbInstance) return null;            // not ready yet; don't cache
        const slash = mKey.lastIndexOf("/");
        const [tg, work] = mKey.slice(0, slash).split(".");
        const vid = mKey.slice(slash + 1);
        const rows = _dbRows(
            "SELECT chapter, line_ref, line_json FROM metrical_lines " +
            "WHERE textgroup=? AND work=? AND version_short_id=? ORDER BY id",
            [tg, work, vid]);
        let out = null;
        if (rows.length) {
            out = {};
            rows.forEach(r => { (out[r.chapter] = out[r.chapter] || {})[r.line_ref] = _jp(r.line_json, []); });
        }
        _MT_CACHE.set(mKey, out);
        return out;
    }
    const METRICAL_DATA = new Proxy({}, {
        get: (_t, k) => (typeof k === "string" ? _hydrateMetrical(k) : undefined)
    });

    // GLOBAL_ALIGNMENTS["tg.wk"][pairId] ->
    //   { src_version, tgt_version, segments: { segId: [ {s,t,st,tt,sc}, ... ] } }
    const _ALN_CACHE = new Map();
    let   _ALN_WORKKEYS = null;
    function _alnWorkKeys() {
        if (_ALN_WORKKEYS) return _ALN_WORKKEYS;
        if (!window.dbInstance) return [];              // not ready yet; don't cache
        _ALN_WORKKEYS = _dbRows("SELECT DISTINCT textgroup || '.' || work AS wk FROM token_alignments").map(r => r.wk);
        return _ALN_WORKKEYS;
    }
    function _hydrateAlignments(workKey) {
        if (_ALN_CACHE.has(workKey)) return _ALN_CACHE.get(workKey);
        if (!window.dbInstance) return undefined;       // not ready yet; don't cache
        const [tg, work] = workKey.split(".");
        const rows = _dbRows(
            "SELECT pair_id, src_version, tgt_version, segment, src_indices, tgt_indices, src_tokens, tgt_tokens, score " +
            "FROM token_alignments WHERE textgroup=? AND work=? ORDER BY pair_id, segment, id",
            [tg, work]);
        let out;
        if (rows.length) {
            out = {};
            rows.forEach(r => {
                let p = out[r.pair_id];
                if (!p) p = out[r.pair_id] = { src_version: r.src_version, tgt_version: r.tgt_version, segments: {} };
                (p.segments[r.segment] = p.segments[r.segment] || []).push({
                    s: _jp(r.src_indices, []), t: _jp(r.tgt_indices, []),
                    st: _jp(r.src_tokens, []), tt: _jp(r.tgt_tokens, []),
                    sc: Math.round(r.score * 1e4) / 1e4
                });
            });
        }
        _ALN_CACHE.set(workKey, out);
        return out;
    }
    const GLOBAL_ALIGNMENTS = new Proxy({}, {
        get: (_t, k) => (typeof k === "string" ? _hydrateAlignments(k) : undefined),
        ownKeys: () => _alnWorkKeys(),
        getOwnPropertyDescriptor: (_t, k) =>
            (_alnWorkKeys().indexOf(k) !== -1 ? { enumerable: true, configurable: true } : undefined)
    });
    
    
    // ── Sharded corpus loader (inlined) ────────────────────

// ── Sharded corpus loader ─────────────────────────────────────────────────
// Replaces the single-monolith fetch. Each work lives in its own small SQLite
// shard; we fetch the whole shard (it's small), open it with sql.js, and cache
// it. No httpvfs / Range requests -> runs on any static server, incl. file-less
// local `python -m http.server`, with no header tuning.

let CATALOG = null;
const SHARD_CACHE = new Map();   // workKey -> sql.js Database
const SHARD_INFLIGHT = new Map(); // workKey -> Promise (dedupe concurrent loads)

const DATA_DIR = "site/data";

// urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.10  ->  parts
function parseCtsUrn(urn) {
    const m = /^urn:cts:([^:]+):([^.]+)\.([^.:]+)(?:\.([^:]+))?(?::(.*))?$/.exec(urn || "");
    if (!m) return null;
    return { textClass: m[1], textgroup: m[2], work: m[3],
             version: m[4] || null, passage: m[5] || null,
             workKey: `${m[2]}.${m[3]}` };
}

// FLAT layout: data/<textgroup>/<work>/<tg>.<wk>.part1.db. This is now only a
// last-resort GUESS used if catalog.json can't be reached at all — the real
// source of truth for which file(s) make up a work is catalog.json's
// per-work `parts` list (see shardPartPathsForWorkKey below), since a large
// work may be split into several book-range parts to stay under GitHub's
// 100MB per-file limit.
function shardPathFor(textgroup, work) {
    return `${DATA_DIR}/${textgroup}/${work}/${textgroup}.${work}.part1.db`;
}
function shardPathForWorkKey(workKey) {
    const [tg, wk] = workKey.split(".");
    return shardPathFor(tg, wk);
}

async function loadCatalog() {
    if (CATALOG) return CATALOG;
    const r = await fetch(`./site/catalog.json?v=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error("catalog.json not found");
    CATALOG = await r.json();
    return CATALOG;
}

// Every work's shard files, in order, from catalog.json's `parts` list.
// Falls back to a single guessed path if the catalog can't be read at all
// or doesn't have this work's parts recorded (e.g. a stale catalog.json).
async function shardPartPathsForWorkKey(workKey, shardPathHint) {
    try {
        const catalog = await loadCatalog();
        const meta = catalog.works && catalog.works[workKey];
        if (meta && Array.isArray(meta.parts) && meta.parts.length) {
            const [tg, wk] = workKey.split(".");
            return meta.parts.map(p => `${DATA_DIR}/${tg}/${wk}/${p.file}`);
        }
    } catch (e) {
        console.warn(`Could not read catalog.json parts for ${workKey}, falling back to a guessed path:`, e);
    }
    return [shardPathHint || shardPathForWorkKey(workKey)];
}

// Fetch + open a shard for a work; cached and de-duplicated. If the work is
// split into multiple book-range parts, every part is fetched and merged
// into a single in-memory database before being cached/returned, so the
// rest of the app (treebankForChapter, alignmentsForPair, etc.) keeps
// working against one `db` handle exactly as it did before any work was
// ever split into multiple files on disk — the split is invisible past
// this point.
async function getDbForWork(workKey, shardPathHint) {
    if (SHARD_CACHE.has(workKey)) return SHARD_CACHE.get(workKey);
    if (SHARD_INFLIGHT.has(workKey)) return SHARD_INFLIGHT.get(workKey);

    const p = (async () => {
        const partPaths = await shardPartPathsForWorkKey(workKey, shardPathHint);
        const db = await loadAndMergeParts(partPaths);
        SHARD_CACHE.set(workKey, db);
        SHARD_INFLIGHT.delete(workKey);
        return db;
    })();
    SHARD_INFLIGHT.set(workKey, p);
    return p;
}

// Fetches every part file's bytes and merges them into one in-memory
// sql.js Database (the first part becomes the primary connection; the rest
// are merged into it, then closed). A single-part work just opens normally.
async function loadAndMergeParts(partPaths) {
    const buffers = await Promise.all(partPaths.map(async path => {
        const resp = await fetch(`./${path}`);
        if (!resp.ok) throw new Error(`Shard part not found: ${path}`);
        return new Uint8Array(await resp.arrayBuffer());
    }));

    const primary = new window.SQL_WASM_ENGINE.Database(buffers[0]);
    if (buffers.length > 1) {
        primary.exec("BEGIN TRANSACTION");
        try {
            for (let i = 1; i < buffers.length; i++) {
                const part = new window.SQL_WASM_ENGINE.Database(buffers[i]);
                mergePartInto(primary, part);
                part.close();
            }
            primary.exec("COMMIT");
        } catch (e) {
            primary.exec("ROLLBACK");
            throw e;
        }
    }
    return primary;
}

// Copies every row of every table in `part` into `primary`, keeping each
// row's ORIGINAL id. The notebook's sharder always inserts the full column
// list (id included) when writing a part, so autoincrement never
// reassigns a value there — every row's id is inherited straight from the
// shared monolith, never reassigned per part. That makes a single
// INSERT OR IGNORE correct and sufficient for every table:
//  - Partitioned tables (alignment_grid, text_segments, treebank_sentences,
//    treebank_tokens, metrical_lines) have disjoint ids between parts
//    (each part only holds its own book range's rows), so every row from
//    `part` just gets added.
//  - Wholesale tables (text_units, treebank_speakers, token_alignments,
//    edition_line_alignments) are byte-identical copies of the same source
//    rows in every part, WITH THE SAME ids — so INSERT OR IGNORE correctly
//    dedupes them instead of creating duplicates.
// (Verified against real generated part files before shipping this.)
function mergePartInto(primary, part) {
    const tables = queryAll(part, "SELECT name FROM sqlite_master WHERE type='table'").map(r => r.name);
    for (const table of tables) {
        const rows = queryAll(part, `SELECT * FROM ${table}`);
        if (rows.length === 0) continue;
        const cols = Object.keys(rows[0]);
        const stmt = primary.prepare(
            `INSERT OR IGNORE INTO ${table} (${cols.join(", ")}) VALUES (${cols.map(() => "?").join(", ")})`);
        for (const row of rows) stmt.run(cols.map(c => row[c]));
        stmt.free();
    }
}


// Optional memory hygiene for long sessions / "own machine" use.
function evictWorkExcept(keepWorkKey) {
    for (const [k, db] of SHARD_CACHE) {
        if (k !== keepWorkKey) { try { db.close(); } catch (e) {} SHARD_CACHE.delete(k); }
    }
}

// ── Per-work data access (replaces the inlined *_REPLACE globals) ──────────
// These read from the loaded shard instead of giant in-HTML JSON blobs.
function queryAll(db, sql, params = []) {
    const out = []; const st = db.prepare(sql); st.bind(params);
    while (st.step()) out.push(st.getAsObject());
    st.free(); return out;
}
function registryForWork(db) {
    return queryAll(db, "SELECT short_id, urn, label, doc_type, text_class FROM text_units ORDER BY doc_type, short_id");
}
function treebankForChapter(db, version, chapter) {
    return queryAll(db,
        "SELECT subdoc, chapter, section, sentence_json, prose_translation, literal_translation, transliteration " +
        "FROM treebank_sentences WHERE version_short_id=? AND chapter=? ORDER BY id",
        [version, chapter]);
}
function alignmentsForPair(db, pairId, segment) {
    return queryAll(db,
        "SELECT src_indices, tgt_indices, src_tokens, tgt_tokens, score " +
        "FROM token_alignments WHERE pair_id=? AND segment=?", [pairId, segment]);
}
function metricalForChapter(db, version, chapter) {
    return queryAll(db,
        "SELECT line_ref, line_json FROM metrical_lines WHERE version_short_id=? AND chapter=?",
        [version, chapter]);
}

// ── Entry point: deep-link routing ─────────────────────────────────────────
async function routeToUrn(urn) {
    const parsed = parseCtsUrn(urn);
    if (!parsed) throw new Error("Unparseable CTS URN: " + urn);
    const path = shardPathFor(parsed.textgroup, parsed.work);
    const db = await getDbForWork(parsed.workKey, path);
    window.dbInstance = db;          // existing text_segments / grid queries now hit the shard
    return { parsed, db };
}


    // ── End shard_loader ──────────────────────────────────────────

let activeWorkKey = "tlg0003.tlg001";
    let activeUrnContext = "";
    let activeSectionFilter = null;
    let currentActiveMode = "parallel";
    let activeColumnsCount = 3;
    let columnEditions = { f: "", c1: "", c2: "", c3: "", c4: "", c5: "", c6: "" };

    // ── Greek transliteration state ────────────────────────────────────
    // Per-column mode: '' (native Greek) | 'simple' | 'full'. Persists across
    // re-renders so switching chapters keeps the reader's chosen view.
    let columnTranslitMode = { f: "", c1: "", c2: "", c3: "", c4: "", c5: "", c6: "" };
    // Per-column snapshot of the un-transliterated HTML, captured each render
    // so toggling back to native Greek is lossless (no round-trip decay).
    let columnGreekOriginalHtml = {};

    // ── Diff state ───────────────────────────────────────────────────
    let diffEnabled = false;

    // ── Alignment state ──────────────────────────────────────────────
    // activePairId: currently selected alignment pair ("" = none)
    // activeAlignGroup: index of currently hovered group (for cross-column highlight)
    let activePairId      = "";
    let activeAlignGroups = new Set();  // set of group keys currently highlighted

    
    
    // Author (textgroup) display names used to group the splash list.
    const AUTHOR_NAMES = {
        "tlg0003": "Thucydides",
        "tlg0011": "Sophocles",
        "tlg0012": "Homer",
        "tlg0020": "Hesiod",
        "tlg0085": "Aeschylus",
        "tlg0086": "Aristotle"
    };

    // Per-work short titles shown under each author heading. This is the
    // only place a new work's display name needs to be added -- there used
    // to be a second "WORK_NAMES" map here too (full "Author Title" strings,
    // typed out by hand), but it was just AUTHOR_NAMES + WORK_TITLES
    // duplicated, and had silently fallen out of sync (missing Hesiod's
    // "Works and Days" and "Shield of Heracles", which only WORK_TITLES had).
    // Removed -- the fallback below builds the full name from these two maps
    // instead of requiring a third one to be kept in sync by hand.
    const WORK_TITLES = {
        "tlg0003.tlg001": "History",
        "tlg0011.tlg001": "Trachiniai",
        "tlg0011.tlg002": "Antigone",
        "tlg0011.tlg003": "Ajax",
        "tlg0011.tlg004": "Oedipus Rex",
        "tlg0011.tlg005": "Electra",
        "tlg0011.tlg006": "Philoctetes",
        "tlg0011.tlg007": "Oedipus at Colonus",
        "tlg0012.tlg001": "Iliad",
        "tlg0012.tlg002": "Odyssey",
        "tlg0020.tlg001": "Theogony",
        "tlg0020.tlg002": "Works and Days",
        "tlg0020.tlg003": "Shield of Heracles",
        "tlg0085.tlg001": "Suppliant Women",
        "tlg0085.tlg002": "Persians",
        "tlg0085.tlg003": "Prometheus Bound",
        "tlg0085.tlg004": "Seven Against Thebes",
        "tlg0085.tlg005": "Agamemnon",
        "tlg0085.tlg006": "Libation Bearers",
        "tlg0085.tlg007": "Eumenides",

        "tlg0086.tlg034": "Poetics"
    };

    // Right-hand summary chip for a work entry. Prefers a compact
    // editions/translations/commentaries count, computed from
    // meta.versions (short_id/urn/label/doc_type/text_class per version --
    // already written into catalog.json by split_corpus_by_work() for every
    // work, so no catalog-builder changes were needed for this). Falls back
    // to total file size, computed defensively (meta.bytes if present and
    // numeric, otherwise summed across meta.parts[].bytes, since the
    // catalog builder records bytes per part but never sums a work-level
    // total) -- and shows nothing at all rather than "NaNKB" if no usable
    // number can be found either way.
    function countDocTypes(versions) {
        const counts = { edition: 0, translation: 0, commentary: 0 };
        for (const v of versions || []) {
            if (v && Object.prototype.hasOwnProperty.call(counts, v.doc_type)) {
                counts[v.doc_type]++;
            }
        }
        return counts;
    }

    function formatWorkMeta(meta) {
        const counts = countDocTypes(meta.versions);
        if (counts.edition || counts.translation || counts.commentary) {
            const bits = [];
            if (counts.edition) bits.push(counts.edition + " ed" + (counts.edition > 1 ? "s" : ""));
            if (counts.translation) bits.push(counts.translation + " tr");
            if (counts.commentary) bits.push(counts.commentary + " comm");
            return bits.join(" · ");
        }

        let bytes = Number(meta.bytes);
        if (!Number.isFinite(bytes) || bytes <= 0) {
            if (Array.isArray(meta.parts) && meta.parts.length) {
                const summed = meta.parts.reduce((sum, p) => sum + (Number(p.bytes) || 0), 0);
                bytes = summed > 0 ? summed : NaN;
            }
        }
        if (!Number.isFinite(bytes) || bytes <= 0) return "";
        return bytes > 1e6 ? (bytes/1e6).toFixed(1)+"MB" : (bytes/1e3).toFixed(0)+"KB";
    }

    function buildWorkPickerFromCatalog(catalog) {
        const works = catalog.works || {};
        const root = document.getElementById("splash-view-root");
        if (!root) return;

        // Group work keys by author (textgroup).
        const byAuthor = {};
        for (const wk of Object.keys(works)) {
            const tg = works[wk].textgroup || wk.split(".")[0];
            (byAuthor[tg] = byAuthor[tg] || []).push(wk);
        }

        const authorKeys = Object.keys(byAuthor).sort((a, b) =>
            (AUTHOR_NAMES[a] || a).localeCompare(AUTHOR_NAMES[b] || b));

        // Whether each author's group was left open/closed last time (manual
        // toggles only -- filtering below expands/collapses temporarily
        // without touching this).
        const EXPANDED_KEY_PREFIX = "workPicker.expanded.";
        function getStoredExpanded(tg, fallback) {
            const v = localStorage.getItem(EXPANDED_KEY_PREFIX + tg);
            return v === null ? fallback : v === "true";
        }

        let html = "<div style='padding:20px;max-width:800px;margin:0 auto;'>";
        html += "<h2>Available Works</h2>";
        html += "<input type='text' id='work-filter' placeholder='Filter works or authors…' " +
                "style='width:100%;box-sizing:border-box;padding:8px 10px;margin-bottom:14px;" +
                "border:1px solid #ccc;border-radius:4px;font-size:0.95em;'>";

        for (const tg of authorKeys) {
            const author = AUTHOR_NAMES[tg] || tg;
            const workKeys = byAuthor[tg].sort((a, b) =>
                (WORK_TITLES[a] || a).localeCompare(WORK_TITLES[b] || b));

            // Default to open while the catalog is small; once there are
            // enough authors that a full expansion is unwieldy, default new
            // (never-toggled) groups to closed instead. Either way, a
            // group's own manually-set state always wins.
            const defaultOpen = authorKeys.length <= 8;
            const isOpen = getStoredExpanded(tg, defaultOpen);

            html += "<details class='author-group' data-author='" + tg + "'" +
                    (isOpen ? " open" : "") + " style='margin:10px 0;'>";
            html += "<summary style='cursor:pointer;font-size:1.05em;color:#7a1f1f;" +
                    "border-bottom:1px solid #e0d8c8;padding-bottom:3px;list-style:revert;'>" +
                    author + " <span class='author-count' style='color:#999;font-weight:normal;" +
                    "font-size:0.85em;'>(" + workKeys.length + ")</span></summary>";
            html += "<ul style='list-style:none;padding:0;margin:8px 0 0;'>";

            for (const wk of workKeys) {
                const meta = works[wk];
                const sz = formatWorkMeta(meta);
                const title = WORK_TITLES[wk] || meta.label;
                html += "<li data-work='" + wk + "' data-search='" +
                        (author + " " + title).toLowerCase() + "' style='display:flex;align-items:baseline;" +
                        "justify-content:space-between;gap:12px;margin:8px 0;padding:12px 14px;" +
                        "border:1px solid #ddd;border-radius:4px;cursor:pointer;background:#f9f9f9;'>";
                html += "<strong style='flex:1 1 auto;min-width:0;'>" + title + "</strong>";
                html += "<span style='flex:0 0 auto;color:#999;font-size:0.9em;white-space:nowrap;'>" + sz + "</span>";
                html += "</li>";
            }
            html += "</ul></details>";
        }

        html += "</div>";
        root.innerHTML = html;

        // Add click handlers after rendering
        root.querySelectorAll("li[data-work]").forEach(el => {
            el.onclick = function() {
                selectWorkAndRoute(this.getAttribute("data-work"));
            };
        });

        // Persist manual open/close toggles per author, but only when the
        // filter box is empty -- while filtering, groups are forced open
        // temporarily (see below) and that shouldn't overwrite a user's
        // real preference.
        root.querySelectorAll("details.author-group").forEach(el => {
            el.addEventListener("toggle", function() {
                const filterEl = document.getElementById("work-filter");
                if (filterEl && filterEl.value.trim() !== "") return;
                localStorage.setItem(EXPANDED_KEY_PREFIX + this.getAttribute("data-author"), String(this.open));
            });
        });

        // Filter box: hides non-matching works, auto-opens any group with a
        // match, hides groups with none, and restores each group's own
        // stored open/closed state when the filter is cleared.
        const filterInput = document.getElementById("work-filter");
        if (filterInput) {
            filterInput.oninput = function() {
                const q = this.value.trim().toLowerCase();
                root.querySelectorAll("details.author-group").forEach(details => {
                    let anyVisible = false;
                    details.querySelectorAll("li[data-work]").forEach(li => {
                        const match = q === "" || li.getAttribute("data-search").includes(q);
                        li.style.display = match ? "" : "none";
                        if (match) anyVisible = true;
                    });
                    details.style.display = anyVisible ? "" : "none";
                    if (q === "") {
                        details.open = getStoredExpanded(details.getAttribute("data-author"), authorKeys.length <= 8);
                    } else {
                        details.open = anyVisible;
                    }
                });
            };
        }
    }
    
    async function selectWorkAndRoute(wk) {
        console.log("[v40] selectWorkAndRoute:", wk);
        activeWorkKey = wk;  // SET FIRST
        console.log("[v40] activeWorkKey set to:", activeWorkKey);
        try {
            const db = await getDbForWork(wk);
            window.dbInstance = db;
            document.getElementById("splash-view-root").style.display = "none";
            document.getElementById("app-view-root").style.display = "flex";
            initializeRoutingFromURL();
        } catch (err) {
            console.error("[v40] error loading work:", err);
            alert("Error: " + err.message);
        }
    }
    
    function loadByUrn() {
        const inp = document.getElementById("urn-in");
        const urn = inp ? inp.value : "";
        if (!urn || !urn.trim()) { alert("Enter a URN"); return; }
        if (!window.dbInstance) { alert("No shard loaded. Drop a .db file first."); return; }
        console.log("[v40] loading URN:", urn);
        routeToUrn(urn).then(r => {
            window.dbInstance = r.db;
            activeWorkKey = r.parsed.workKey;
            document.getElementById("splash-view-root").style.display = "none";
            document.getElementById("app-view-root").style.display = "flex";
            initializeRoutingFromURL();
        }).catch(err => { 
            console.error("[v40] routeToUrn error:", err);
            alert("Error: " + err.message); 
        });
    }


    initSqlJs({ locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}` }).then(SQL => {
        window.SQL_WASM_ENGINE = SQL;
        document.getElementById("status-readout").innerText = "WebAssembly layer compiled. Auto-loading default database...";
        
        loadCatalog()
            .then(async catalog => {
                console.log("[v40] Catalog loaded");
                buildWorkPickerFromCatalog(catalog);
                
                // Check if URL specifies a work (e.g., ?w=tlg0011.tlg004:1-13)
                const params = new URLSearchParams(window.location.search);
                const wParam = params.get("w");
                
                if (wParam) {
                    // Parse work key from URL (before any colon)
                    const workKey = wParam.split(":")[0];
                    console.log("[v40] URL specifies work:", workKey);
                    
                    try {
                        // Load shard FIRST
                        const db = await getDbForWork(workKey);
                        window.dbInstance = db;
                        activeWorkKey = workKey;
                        console.log("[v40] shard loaded for URL navigation");
                        
                        // Hide splash, show app
                        document.getElementById("splash-view-root").style.display = "none";
                        document.getElementById("app-view-root").style.display = "flex";
                        
                        // Then call initialization which will populate structures and navigate
                        initializeRoutingFromURL();
                    } catch (err) {
                        console.error("[v40] error loading shard from URL:", err);
                        alert("Error loading work: " + err.message);
                    }
                }
            })
            .catch(err => {
                console.error("[v40] Catalog error:", err.message);
                document.getElementById("status-readout").innerHTML = 
                    "<strong>Catalog not found.</strong> Drop a work shard or enter URN:<br>" +
                    "<input id='urn-in' placeholder='urn:cts:greekLit:tlg0003.tlg001:1.1' style='width:90%;margin:4px;padding:4px;'/>" +
                    "<button onclick='loadByUrn()' style='padding:4px 8px;cursor:pointer;'>Load</button>";
            });

    }).catch(err => {
        console.error(err);
        document.getElementById("status-readout").innerText = "WebAssembly core initialization error.";
    });

    function launchReadingEnvironment() {
        if (!window.dbInstance) return;
        document.getElementById("splash-view-root").style.display = "none";
        document.getElementById("app-view-root").style.display = "flex";
        initializeRoutingFromURL();
    }

    function handleFileSelection(files) {
        if (!files || files.length === 0) return;
        
        if (!window.SQL_WASM_ENGINE) {
            document.getElementById("status-readout").innerText = "WebAssembly engine still loading — please wait a moment and try again.";
            const pendingFiles = files;
            const waitInterval = setInterval(() => {
                if (window.SQL_WASM_ENGINE) {
                    clearInterval(waitInterval);
                    handleFileSelection(pendingFiles);
                }
            }, 200);
            return;
        }
        document.getElementById("status-readout").innerText = "Parsing structural asset binary grid...";
        
        const file = files[0];
        const reader = new FileReader();
        
        reader.onload = function(e) {
            try {
                const buffer = new Uint8Array(e.target.result);
                window.dbInstance = new window.SQL_WASM_ENGINE.Database(buffer);
                
                document.getElementById("splash-view-root").style.display = "none";
                document.getElementById("app-view-root").style.display = "flex";
                
                initializeRoutingFromURL();
            } catch (err) {
                console.error(err);
                document.getElementById("status-readout").innerText = "Error parsing file: " + err.message;
            }
        };
        reader.readAsArrayBuffer(file);
    }

    function isFlatStructure(wKey) { return Array.isArray(GLOBAL_STRUCTURES[wKey]); }
    function isPoetryWork(wKey) { 
        return wKey.startsWith("tlg0011.") || wKey.startsWith("tlg0012.") || wKey.startsWith("tlg0020.") || wKey.startsWith("ferdowsi.") || wKey.startsWith("tlg0085."); 
    }
    function naturalSectionKeys(obj) {
        return Object.keys(obj).sort((a, b) => {
            const ma = a.match(/^(\d+)(.*)/);
            const mb = b.match(/^(\d+)(.*)/);
            if (ma && mb) {
                const na = parseInt(ma[1]), nb = parseInt(mb[1]);
                if (na !== nb) return na - nb;
                return ma[2].localeCompare(mb[2]);
            }
            if (ma) return -1;
            if (mb) return 1;
            return a.localeCompare(b);
        });
    }

    function getChapterDataPayload(workKey, book, chapter) {
        if (!window.dbInstance) { console.warn("getChapterDataPayload: no DB loaded"); return null; }
        const parts = workKey.split(".");
        let queryStr = `SELECT passage_urn, section, prev_urn, next_urn FROM alignment_grid WHERE textgroup='${parts[0]}' AND work='${parts[1]}' AND chapter='${chapter}'`;
        if (book) queryStr += ` AND book='${book}'`;
        queryStr += " ORDER BY sort_order";
        
        const gridResult = window.dbInstance.exec(queryStr);
        if (gridResult.length === 0) return null;
        
        const baseRows = gridResult[0].values;
        const sectionsPayload = {};
        let masterUrn = "";
        let navigation = { prev: null, next: null };
        
        baseRows.forEach(([pUrn, sec, prevUrn, nextUrn]) => {
            if(!masterUrn) masterUrn = pUrn.substring(0, pUrn.lastIndexOf('.'));
            navigation.prev = prevUrn;
            navigation.next = nextUrn;
            sectionsPayload[sec] = {};
            
            const contentQuery = window.dbInstance.exec(`SELECT version_short_id, content_html FROM text_segments WHERE passage_urn='${pUrn}'`);
            if (contentQuery.length > 0) {
                contentQuery[0].values.forEach(([vId, html]) => {
                    sectionsPayload[sec][vId] = html;
                });
            }
        });
        
        return {
            urn: masterUrn, textgroup: parts[0], work: parts[1], book: book, chapter: chapter,
            sections: sectionsPayload, navigation: navigation
        };
    }

    function populateDropdownsForWork(tg, wk) {
        // Populate alignment pair dropdown for the active work
        populateAlignmentDropdown(`${tg}.${wk}`);

        const validEditions = Object.entries(TEXT_REGISTRY).filter(([key, meta]) => {
            return meta.textgroup === tg && meta.work === wk;
        });

        ['f', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'].forEach((prefix) => {
            const selectEl = document.getElementById("select_" + prefix);
            if (!selectEl) return;
            
            selectEl.innerHTML = "";
            
            const categories = {
                edition: document.createElement("optgroup"),
                appcrit: document.createElement("optgroup"),
                translation: document.createElement("optgroup"),
                commentary: document.createElement("optgroup"),
                treebank: document.createElement("optgroup"),
                metrical: document.createElement("optgroup")
            };
            
            categories.edition.label = "Critical Editions";
            categories.appcrit.label = "Apparatus Critici";
            categories.translation.label = "Translations";
            categories.commentary.label = "Commentaries";
            categories.treebank.label = "Treebanks";
            categories.metrical.label = "Metrical Analysis";

            validEditions.forEach(([canonicalId, meta]) => {
                const opt = document.createElement("option");
                opt.value = canonicalId;
                opt.textContent = meta.label;
                
                if (categories[meta.doc_type]) {
                    categories[meta.doc_type].appendChild(opt);
                }
            });

            for (const key in categories) {
                if (categories[key].children.length > 0) {
                    selectEl.appendChild(categories[key]);
                }
            }
            
            if (columnEditions[prefix]) {
                selectEl.value = columnEditions[prefix];
            }
        });
    }
    
    
    
    function populateSectionsForBook(book) {
        if (!window.dbInstance) return;
        console.log("[v40] loading sections for book:", book);
        
        const sections_result = window.dbInstance.exec(
            "SELECT DISTINCT chapter FROM alignment_grid WHERE book='" + book + "' ORDER BY CAST(SUBSTR(chapter, 1, INSTR(chapter||'-', '-')-1) AS INTEGER)");
        const sections = sections_result[0] ? sections_result[0].values.map(r => r[0]) : [];
        console.log("[v40] found sections:", sections);
        
        // Try multiple possible container IDs
        const sectionsContainer = document.getElementById("chapter-items-container");
        if (sectionsContainer && sections.length > 0) {
            sectionsContainer.innerHTML = "";
            sections.forEach(section => {
                const link = document.createElement("a");
                link.href = "#";
                link.textContent = section;
                link.style.marginRight = "8px";
                link.style.cursor = "pointer";
                link.onclick = (e) => {
                    e.preventDefault();
                    console.log("[v40] selected section:", section);
                };
                sectionsContainer.appendChild(link);
            });
            console.log("[v40] populated", sections.length, "sections in", sectionsContainer.id);
        } else {
            console.warn("[v40] no container or no sections found");
        }
    }


function populateNavigationFromShard() {
        if (!window.dbInstance) {
            console.warn("[v40] no database instance");
            return;
        }
        console.log("[v40] populating GLOBAL_STRUCTURES + TEXT_REGISTRY for:", activeWorkKey);
        
        const [tg, wk] = activeWorkKey.split(".");
        
        // 1. Build GLOBAL_STRUCTURES for this work
        const books_result = window.dbInstance.exec(
            "SELECT DISTINCT book FROM alignment_grid WHERE book IS NOT NULL ORDER BY CAST(book AS INTEGER)");
        const books = books_result[0] ? books_result[0].values.map(r => r[0]) : [];
        
        if (books.length > 0) {
            const bookMap = {};
            books.forEach(bk => {
                const chapter_result = window.dbInstance.exec(
                    "SELECT DISTINCT chapter FROM alignment_grid WHERE book='" + bk + "' ORDER BY sort_order");
                bookMap[bk] = chapter_result[0] ? chapter_result[0].values.map(r => r[0]) : [];
            });
            window.GLOBAL_STRUCTURES = window.GLOBAL_STRUCTURES || {};
            window.GLOBAL_STRUCTURES[activeWorkKey] = bookMap;
            console.log("[v40] multi-book structure with " + books.length + " books");
        } else {
            const chapter_result = window.dbInstance.exec(
                "SELECT DISTINCT chapter FROM alignment_grid ORDER BY sort_order");
            const chapters = chapter_result[0] ? chapter_result[0].values.map(r => r[0]) : [];
            window.GLOBAL_STRUCTURES = window.GLOBAL_STRUCTURES || {};
            window.GLOBAL_STRUCTURES[activeWorkKey] = chapters;
            console.log("[v40] flat structure with " + chapters.length + " chapters");
        }
        
        // 2. Build TEXT_REGISTRY using the proper canonical_id to match the dropdowns
        const editions_result = window.dbInstance.exec(
            "SELECT canonical_id, urn, label, text_class, textgroup, work, short_id, doc_type FROM text_units");
        if (editions_result[0]) {
            window.TEXT_REGISTRY = window.TEXT_REGISTRY || {};
            editions_result[0].values.forEach(row => {
                window.TEXT_REGISTRY[row[0]] = {
                    urn: row[1],
                    label: row[2],
                    class: row[3],
                    textgroup: row[4],
                    work: row[5],
                    short_id: row[6],
                    doc_type: row[7]
                };
            });
            console.log("[v40] populated TEXT_REGISTRY with " + editions_result[0].values.length + " editions");
        }
        
        // NOTE: The rogue triggerTargetNavigation() call has been removed from here.
    }

function initializeRoutingFromURL() { 
        console.log('[v40] initializeRoutingFromURL, activeWorkKey:', activeWorkKey); 
        
        // 1. Silently map out the structures and registries first
        populateNavigationFromShard();

        // 2. Parse the URL safely
        const params = new URLSearchParams(window.location.search);
        // const rawParam = params.get("w") || "tlg0003.tlg001";
        const rawParam = params.get("w") || activeWorkKey;
        let b = null, ch = "1";
        activeSectionFilter = null;
        
        columnEditions.f = params.get("focus") || "";
        columnEditions.c1 = params.get("right") || "";
        columnEditions.c2 = params.get("right2") || "";
        columnEditions.c3 = params.get("right3") || "";
        columnEditions.c4 = params.get("right4") || "";
        columnEditions.c5 = params.get("right5") || "";
        columnEditions.c6 = params.get("right6") || "";

        const colParam = params.get("cols");
        if (colParam) {
            activeColumnsCount = parseInt(colParam, 10) || 3;
            setTimeout(() => {
                const ow = document.getElementById('outer-wrapper');
                if (activeColumnsCount === 4) ow.classList.add('four-columns');
                if (activeColumnsCount === 5) ow.classList.add('five-columns');
                if (activeColumnsCount === 6) ow.classList.add('six-columns');
                if (activeColumnsCount === 7) ow.classList.add('seven-columns');
                document.getElementById('btn-column-scaler').innerText = `Columns: ${activeColumnsCount}`;
            }, 0);
        }

        if (rawParam.includes(":")) {
            const querySegments = rawParam.split(":");
            activeWorkKey = querySegments[0];
            const passageSegments = querySegments[1].split(".");
            
            if (isFlatStructure(activeWorkKey)) {
                b = null; ch = passageSegments[0] || "1";
                if (passageSegments[1]) activeSectionFilter = passageSegments[1];
            } else {
                b = passageSegments[0]; ch = passageSegments[1] || "1";
                if (passageSegments[2]) activeSectionFilter = passageSegments[2];
            }
        } else {
            activeWorkKey = rawParam;
            if (isFlatStructure(activeWorkKey)) {
                b = null; ch = GLOBAL_STRUCTURES[activeWorkKey][0] || "1";
            } else {
                b = Object.keys(GLOBAL_STRUCTURES[activeWorkKey])[0];
                ch = GLOBAL_STRUCTURES[activeWorkKey][b][0] || "1";
            }
        }

        const workPrefix = activeWorkKey.split(".")[1];
        const tgPrefix = activeWorkKey.split(".")[0];
        ['f', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'].forEach(prefix => {
            const currentEd = columnEditions[prefix];
            if (currentEd && TEXT_REGISTRY[currentEd] &&
                (TEXT_REGISTRY[currentEd].work !== workPrefix ||
                 TEXT_REGISTRY[currentEd].textgroup !== tgPrefix)) {
                columnEditions[prefix] = ""; 
            }
        });

        // 3. Trigger a single, unified render using our validated state
        triggerTargetNavigation(b, ch);
    }

    function triggerTargetNavigation(book, chapter) {
        const payload = getChapterDataPayload(activeWorkKey, book, chapter);
        if (!payload) return;
        activeUrnContext = payload.urn;
        
        document.getElementById("frame-context-label").innerText = "Active Frame Context URN: " + payload.urn;
        
        const validEditions = Object.entries(TEXT_REGISTRY).filter(([key, meta]) => {
            return meta.textgroup === payload.textgroup && meta.work === payload.work;
        });
        
        if (validEditions.length > 0) {
            const editions = validEditions.filter(([_, m]) => m.doc_type === 'edition');
            const translations = validEditions.filter(([_, m]) => m.doc_type === 'translation');
            const commentaries = validEditions.filter(([_, m]) => m.doc_type === 'commentary');
            const appcrits = validEditions.filter(([_, m]) => m.doc_type === 'appcrit');
            const treebanks = validEditions.filter(([_, m]) => m.doc_type === 'treebank');
            const metrics  = validEditions.filter(([_, m]) => m.doc_type === 'metrical');

            let prioritizedList = [];
            let maxLen = Math.max(editions.length, translations.length, commentaries.length, appcrits.length);
            
            for (let i = 0; i < maxLen; i++) {
                if (editions[i]) prioritizedList.push(editions[i][0]);
                if (translations[i]) prioritizedList.push(translations[i][0]);
                if (commentaries[i]) prioritizedList.push(commentaries[i][0]);
                if (appcrits[i]) prioritizedList.push(appcrits[i][0]);
            }
            treebanks.forEach(([id]) => { if (!prioritizedList.includes(id)) prioritizedList.push(id); });
            metrics.forEach(([id])  => { if (!prioritizedList.includes(id)) prioritizedList.push(id); });

            prioritizedList = [...new Set(prioritizedList)];

            const prefixes = ['f', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'];
            prefixes.forEach((prefix, idx) => {
                let currentEd = columnEditions[prefix];
                // External-link support: a URL may carry a short_id instead of the canonical id.
                if (currentEd && !TEXT_REGISTRY[currentEd]) {
                    const byShort = Object.keys(TEXT_REGISTRY).find(k =>
                        TEXT_REGISTRY[k].short_id === currentEd &&
                        TEXT_REGISTRY[k].textgroup === payload.textgroup &&
                        TEXT_REGISTRY[k].work === payload.work);
                    if (byShort) { currentEd = byShort; columnEditions[prefix] = byShort; }
                }
                const belongsToCurrentWork = currentEd && TEXT_REGISTRY[currentEd] &&
                                             TEXT_REGISTRY[currentEd].textgroup === payload.textgroup &&
                                             TEXT_REGISTRY[currentEd].work === payload.work;
                if (!belongsToCurrentWork) {
                    if (currentEd) {
                        // The URL explicitly named an edition we cannot resolve for this work.
                        // Honor the URL: leave the column blank instead of substituting an
                        // unrelated default (which is what made a bad treebank id show as commentary).
                        const known = Object.keys(TEXT_REGISTRY).filter(k =>
                            TEXT_REGISTRY[k].textgroup === payload.textgroup &&
                            TEXT_REGISTRY[k].work === payload.work);
                        console.warn(`[url] column "${prefix}": "${currentEd}" not found for ${payload.textgroup}.${payload.work} - leaving blank. Valid ids: ${known.join(", ")}`);
                        columnEditions[prefix] = "";
                    } else {
                        columnEditions[prefix] = prioritizedList.length > 0
                            ? prioritizedList[idx % prioritizedList.length]
                            : "";
                    }
                }
            });
        }

        populateDropdownsForWork(payload.textgroup, payload.work);
        renderNavigationControls(payload);
        try {
            renderActiveContentLayers(payload);
        } catch(err) {
            console.error("renderActiveContentLayers error:", err);
            document.getElementById("status-readout").innerText = "Render error: " + err.message;
        }
        updateDiffToggleVisibility();
        if (diffEnabled && !activePairId) {
            // Diff a single pair only — see onDiffToggle. Rendering every pairwise
            // combination overwrites shared column DOM and lights up identical neighbours.
            const pairs = findSameLangColumnPairs();
            if (pairs.length > 0) applyColumnDiff(pairs[0].leftPrefix, pairs[0].rightPrefix);
        }
        
        updateURLState(payload.book, payload.chapter);
    }

    // ── Text Diff Functions ──────────────────────────────────────────────

    // Normalise a token for diff comparison: lowercase, strip punctuation
    function diffNorm(s) {
        return s.normalize("NFD")
            // .replace(/[̀-ͯ᷀-᷿]/g, "")              // combining diacritics (+supplement)
            .replace(/[­​-‏⁠﻿᠎]/g, "")   // invisible/format chars
            .replace(/[‐-―−⁃－]/g, "")         // all dash/hyphen variants
            .replace(/['’‘"“”ʼ᾽᾿῾ʾʿ]/g, "")                            // apostrophe/breathing/quotes
            // .toLowerCase()
            .replace(/[.,;:·!?"()\[\]{}«»·;…]/g, "")
            .trim();
    }

    // Longest-common-subsequence diff between two token arrays.
    // Returns an array of {tok, type} where type is "same"|"del"|"ins".
    // "del" = in left only, "ins" = in right only.
    function tokenDiff(leftToks, rightToks) {
        const L = leftToks.length, R = rightToks.length;
        // Build LCS table on normalised tokens
        const dp = Array.from({length: L+1}, () => new Int32Array(R+1));
        for (let i = L-1; i >= 0; i--) {
            for (let j = R-1; j >= 0; j--) {
                if (diffNorm(leftToks[i]) === diffNorm(rightToks[j])) {
                    dp[i][j] = dp[i+1][j+1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i+1][j], dp[i][j+1]);
                }
            }
        }
        // Traceback
        const leftOut = [], rightOut = [];
        let i = 0, j = 0;
        while (i < L || j < R) {
            if (i < L && j < R && diffNorm(leftToks[i]) === diffNorm(rightToks[j])) {
                leftOut.push({tok: leftToks[i], type: "same"});
                rightOut.push({tok: rightToks[j], type: "same"});
                i++; j++;
            } else if (j < R && (i >= L || dp[i][j+1] >= dp[i+1][j])) {
                rightOut.push({tok: rightToks[j], type: "ins"});
                j++;
            } else {
                leftOut.push({tok: leftToks[i], type: "del"});
                i++;
            }
        }
        return {leftOut, rightOut};
    }

    function renderDiffTokens(items) {
        return items.map(({tok, type}) => {
            const e = tok.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
            if (type === "del") return `<span class="diff-token-del">${e}</span>`;
            if (type === "ins") return `<span class="diff-token-ins">${e}</span>`;
            return e;
        }).join(" ");
    }

    // Find pairs of columns that share the same language class.
    // Returns [{leftPrefix, rightPrefix, cssClass}] for each same-lang pair.
    function findSameLangColumnPairs() {
        const prefixes = ['f', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'];
        // Only diff critical editions (doc_type="edition"), not translations.
        // Two translations of the same work are intentionally different —
        // diffing them produces noise, not scholarly signal.
        const active = prefixes
            .map(p => ({prefix: p, meta: TEXT_REGISTRY[columnEditions[p]]}))
            .filter(({meta}) =>
                meta &&
                meta.doc_type === 'edition' &&
                (meta.class === 'greek-text' || meta.class === 'latin-text')
            );
        const pairs = [];
        for (let i = 0; i < active.length; i++) {
            for (let j = i+1; j < active.length; j++) {
                if (active[i].meta.class === active[j].meta.class) {
                    pairs.push({
                        leftPrefix: active[i].prefix,
                        rightPrefix: active[j].prefix,
                        cssClass: active[i].meta.class
                    });
                }
            }
        }
        return pairs;
    }

    // Apply diff highlighting to already-rendered column content.
    // Only runs on prose columns; skips treebank, metrical, and any column
    // with an active alignment pair (which would destroy aln-token spans).
    function applyColumnDiff(leftPrefix, rightPrefix) {

        // Validate both columns are plain prose (not treebank/metrical)
        const leftMeta  = TEXT_REGISTRY[columnEditions[leftPrefix]];
        const rightMeta = TEXT_REGISTRY[columnEditions[rightPrefix]];
        if (!leftMeta || !rightMeta) return;
        if (leftMeta.doc_type  === 'treebank' || leftMeta.doc_type  === 'metrical') return;
        if (rightMeta.doc_type === 'treebank' || rightMeta.doc_type === 'metrical') return;

        const leftCol  = document.getElementById(`content_${leftPrefix}`);
        const rightCol = document.getElementById(`content_${rightPrefix}`);
        if (!leftCol || !rightCol) return;

        leftCol.querySelectorAll('.section-row').forEach(leftRow => {
            const secClass = [...leftRow.classList].find(c => c.startsWith('s-idx-'));
            if (!secClass) return;
            const rightRow = rightCol.querySelector(`.${secClass}`);
            if (!rightRow) return;

            // Use only the prose-body-inline element text — not the whole row
            // (avoids picking up section numbers, treebank IDs, etc.)
            const leftBody  = leftRow.querySelector('.prose-body-inline');
            const rightBody = rightRow.querySelector('.prose-body-inline');
            if (!leftBody || !rightBody) return;

            // Clone and strip milestone/Bekker number spans before reading text.
            // CSS hides them visually but they remain in textContent and shift token indices.
            // Read from a cached clean baseline so repeated toggles / multiple
            // applyColumnDiff calls never re-diff already-injected diff markup.
            if (leftBody.dataset.diffBaseline  === undefined) leftBody.dataset.diffBaseline  = leftBody.innerHTML;
            if (rightBody.dataset.diffBaseline === undefined) rightBody.dataset.diffBaseline = rightBody.innerHTML;
            const leftClone  = document.createElement('div'); leftClone.innerHTML  = leftBody.dataset.diffBaseline;
            const rightClone = document.createElement('div'); rightClone.innerHTML = rightBody.dataset.diffBaseline;
            leftClone.querySelectorAll('.inline-line-milestone, .milestone').forEach(el => el.remove());
            rightClone.querySelectorAll('.inline-line-milestone, .milestone').forEach(el => el.remove());

            const leftText  = (leftClone.textContent  || "").trim();
            const rightText = (rightClone.textContent || "").trim();
            if (!leftText || !rightText) return;

            // Keep only word-tokens (contain at least one letter).
            const isWord = t => /[a-zA-ZͰ-Ͽἀ-῿Ā-ɏЀ-ӿ]/.test(t);
            const leftToks  = leftText.split(/\s+/).filter(t => t && isWord(t));
            const rightToks = rightText.split(/\s+/).filter(t => t && isWord(t));

            const {leftOut, rightOut} = tokenDiff(leftToks, rightToks);

            const hasDiff = leftOut.some(x => x.type !== "same") || rightOut.some(x => x.type !== "same");
            if (!hasDiff) return;

            leftBody.innerHTML  = renderDiffTokens(leftOut);
            rightBody.innerHTML = renderDiffTokens(rightOut);
        });
    }

    function clearColumnDiff() {
        // Re-render to remove diff markup (simplest: just trigger a view refresh)
        triggerViewRefresh();
    }

    function updateDiffToggleVisibility() {
        const pairs    = findSameLangColumnPairs();
        const diffRow  = document.getElementById("diff-toggle-row");
        const sep      = document.getElementById("diff-aln-separator");
        const label    = document.getElementById("diff-pair-label");
        const alnSel   = document.getElementById("alignment-pair-select");
        const hasDiff  = pairs.length > 0;
        const hasAln   = alnSel && !alnSel.disabled;

        if (diffRow) diffRow.style.display = hasDiff ? "flex" : "none";
        if (sep)     sep.style.display     = (hasDiff && hasAln) ? "inline" : "none";

        if (hasDiff && label) {
            label.textContent = pairs.map(p =>
                `${p.leftPrefix.toUpperCase()} vs ${p.rightPrefix.toUpperCase()}`
            ).join(", ");
        }
        if (!hasDiff) {
            diffEnabled = false;
            const cb = document.getElementById("diff-toggle-checkbox");
            if (cb) cb.checked = false;
        }
    }

    function onDiffToggle(checked) {
        diffEnabled = checked;
        if (!checked) { clearColumnDiff(); return; }

        const pairs = findSameLangColumnPairs();
        if (pairs.length === 0) return;

        // A column's DOM can only display ONE diff. Rendering every pairwise
        // combination overwrites columns (last write wins), so each column ends
        // up diffed against the LAST column instead of its neighbour — which makes
        // identical neighbouring editions light up. Diff exactly one pair.
        const pair = pairs[0];
        if (pairs.length > 1) {
            console.warn(`Diff: ${pairs.length} same-language pairs available (` +
                pairs.map(p => p.leftPrefix.toUpperCase() + "v" + p.rightPrefix.toUpperCase()).join(", ") +
                `); showing ${pair.leftPrefix.toUpperCase()} vs ${pair.rightPrefix.toUpperCase()} only.`);
        }
        applyColumnDiff(pair.leftPrefix, pair.rightPrefix);
    }

    // ── Alignment Functions ──────────────────────────────────────────────

    function getAlignmentPairsForWork(workKey) {
        return GLOBAL_ALIGNMENTS[workKey] || {};
    }

    function versionLabel(vId) {
        // Turn "bywater1909-grc1" → "Bywater GRC (1909)"
        const m = vId.match(/^([a-zA-Z]+)(\d{4})-([a-z]+)\d+$/);
        if (m) {
            const name = m[1].charAt(0).toUpperCase() + m[1].slice(1);
            const year = m[2];
            const lang = m[3].toUpperCase();
            return `${name} ${lang} (${year})`;
        }
        return vId;
    }

    function populateAlignmentDropdown(workKey) {
        const sel = document.getElementById("alignment-pair-select");
        if (!sel) return;
        const pairs = getAlignmentPairsForWork(workKey);
        const pairIds = Object.keys(pairs);
        sel.innerHTML = '<option value="">— none —</option>';
        if (pairIds.length === 0) {
            sel.disabled = true;
            const leg = document.getElementById("alignment-legend");
            if (leg) {
                const allWorks = Object.keys(GLOBAL_ALIGNMENTS);
                if (allWorks.length === 0) {
                    leg.innerHTML = '<span style="color:#b05000">No alignment data loaded — re-run Cell 0 then Cell 2</span>';
                } else {
                    leg.innerHTML = '<span style="color:#777">No alignments for this work</span>';
                }
            }
            activePairId = "";
            return;
        }
        sel.disabled = false;

        // Find which pair best matches the currently displayed columns
        const displayedVersions = new Set(
            Object.values(columnEditions).filter(Boolean).map(cid => {
                const meta = TEXT_REGISTRY[cid];
                return meta ? meta.short_id : null;
            }).filter(Boolean)
        );

        let bestPairId = activePairId;
        let bestScore  = -1;
        pairIds.forEach(pid => {
            const p = pairs[pid];
            // Score = number of alignment sides currently visible in columns
            let score = 0;
            if (displayedVersions.has(p.src_version)) score++;
            if (displayedVersions.has(p.tgt_version)) score++;
            if (score > bestScore) { bestScore = score; bestPairId = pid; }
        });
        // Auto-select best matching pair if none currently active
        if (!activePairId) {
            activePairId = bestPairId;
        }

        pairIds.forEach(pid => {
            const p = pairs[pid];
            const opt = document.createElement("option");
            opt.value = pid;
            opt.textContent = `${versionLabel(p.src_version)} → ${versionLabel(p.tgt_version)}`;
            if (pid === activePairId) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.value = activePairId;
        updateAlignmentLegend();
    }

    function updateAlignmentLegend() {
        const leg = document.getElementById("alignment-legend");
        if (!leg) return;
        if (!activePairId) { leg.textContent = ""; return; }
        const pairs = getAlignmentPairsForWork(activeWorkKey);
        const pair  = pairs[activePairId];
        if (!pair) { leg.textContent = ""; return; }

        // Warn if src or tgt column is not currently displayed
        const displayedVersions = new Set(
            Object.values(columnEditions).filter(Boolean).map(cid => {
                const meta = TEXT_REGISTRY[cid];
                return meta ? meta.short_id : null;
            }).filter(Boolean)
        );
        const srcShown = displayedVersions.has(pair.src_version);
        const tgtShown = displayedVersions.has(pair.tgt_version);

        if (srcShown && tgtShown) {
            leg.innerHTML = `<span style="color:#555">Hover a token to highlight its correspondences</span>`;
        } else {
            const missing = [];
            if (!srcShown) missing.push(`<b>${versionLabel(pair.src_version)}</b>`);
            if (!tgtShown) missing.push(`<b>${versionLabel(pair.tgt_version)}</b>`);
            leg.innerHTML = `<span style="color:#b05000">⚠ Add ${missing.join(" and ")} to a column to see highlights</span>`;
        }
    }

    function onAlignmentPairChange(pairId) {
        activePairId = pairId;
        activeAlignGroups.clear();
        updateAlignmentLegend();
        triggerViewRefresh();
    }

    // Get alignment groups for a specific section under the active pair
    function getAlignmentGroupsForSection(workKey, segId) {
        if (!activePairId) return [];
        const pairs = GLOBAL_ALIGNMENTS[workKey];
        if (!pairs) return [];
        const pair = pairs[activePairId];
        if (!pair) return [];
        return pair.segments[segId] || [];
    }

    // Score → underline colour (blue-to-gold spectrum)
    function scoreToColor(score) {
        const t = Math.max(0, Math.min(1, (score - 0.25) / 0.55));
        const r = Math.round(74  + (230 - 74)  * (1 - t));
        const g = Math.round(144 + (160 - 144) * (1 - t));
        const b = Math.round(217 + (20  - 217) * (1 - t));
        return `rgb(${r},${g},${b})`;
    }

    // Wrap plain text tokens in <span class="aln-token"> elements.
    // groupMap: Map<tokenIdx, {groupKey, score, color}>
    function buildAlignedTokenSpans(tokens, groupMap, side) {
        return tokens.map((tok, idx) => {
            const info = groupMap.get(idx);
            if (!info) return escapeHtml(tok);
            const gk   = info.groupKey;
            const col  = info.color;
            return `<span class="aln-token" `
                 + `data-gk="${gk}" data-side="${side}" `
                 + `style="border-bottom-color:${col}" `
                 + `onmouseenter="alnHoverIn('${gk}')" `
                 + `onmouseleave="alnHoverOut()">`
                 + escapeHtml(tok)
                 + `</span>`;
        }).join(" ");
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;")
            .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }

    // Build group maps for a section's alignment groups.
    // Returns { srcMap: Map<idx,info>, tgtMap: Map<idx,info> }
    function buildGroupMaps(groups) {
        const srcMap = new Map();
        const tgtMap = new Map();
        groups.forEach((grp, gi) => {
            const gk    = String(gi);
            const color = scoreToColor(grp.sc);
            // Many-to-many: each index in src_indices maps to this group
            grp.s.forEach(si => srcMap.set(si, { groupKey: gk, score: grp.sc, color }));
            grp.t.forEach(ti => tgtMap.set(ti, { groupKey: gk, score: grp.sc, color }));
        });
        return { srcMap, tgtMap };
    }

    // groupKey format: "segKey__origIdx"  e.g. "1.8__3"
    // This namespacing ensures tokens from different sections never share a key,
    // so hovering a word in section [3] only lights up its match in [3], not [8].

    function alnHoverIn(groupKey) {
        activeAlignGroups.clear();
        activeAlignGroups.add(groupKey);
        // Extract segKey (everything before the last "__")
        const segKey = groupKey.substring(0, groupKey.lastIndexOf("__"));
        document.querySelectorAll(".aln-token").forEach(el => {
            el.classList.remove("aln-hl-strong", "aln-dimmed");
            el.style.borderBottomColor = "";
            const elGk  = el.dataset.gk || "";
            const elSeg = elGk.substring(0, elGk.lastIndexOf("__"));
            if (elGk === groupKey) {
                el.classList.add("aln-hl-strong");
                if (el.dataset.color) el.style.borderBottomColor = el.dataset.color;
            } else if (elSeg === segKey) {
                el.classList.add("aln-dimmed");
            }
            // tokens in other sections: untouched
        });
    }
    function alnHoverOut() {
        activeAlignGroups.clear();
        document.querySelectorAll(".aln-token").forEach(el => {
            el.classList.remove("aln-hl-strong", "aln-dimmed");
            el.style.borderBottomColor = "";
        });
    }

    // Filter alignment groups to meaningful 1-to-1 correspondences.
    // Returns [{group, origIdx}] — origIdx is position in the original array,
    // used as the stable cross-column group key.
    function filterGroups(groups, nSrcToks, nTgtToks) {
        const result = [];
        groups.forEach((g, origIdx) => {
            if (g.sc < 0.40) return;
            if (g.s.length > 6 || g.t.length > 6) return;
            if (nSrcToks > 0 && g.s.length / nSrcToks > 0.40) return;
            if (nTgtToks > 0 && g.t.length / nTgtToks > 0.40) return;
            if (!g.st || !g.tt || g.st.length === 0 || g.tt.length === 0) return;
            result.push({ group: g, origIdx });
        });
        return result;
    }

    function scoreToColor(score) {
        const t = Math.max(0, Math.min(1, (score - 0.25) / 0.55));
        const r = Math.round(74  + (230 - 74)  * (1 - t));
        const g = Math.round(144 + (160 - 144) * (1 - t));
        const b = Math.round(217 + (20  - 217) * (1 - t));
        return `rgb(${r},${g},${b})`;
    }

    function buildAlignedTokenSpans(tokens, groupMap, side) {
        return tokens.map((tok, idx) => {
            const info = groupMap.get(idx);
            if (!info) return escapeHtml(tok);
            const gk  = info.groupKey;  // "segKey__origIdx"
            const col = info.color;
            return `<span class="aln-token" `
                 + `data-gk="${gk}" data-side="${side}" data-color="${col}" `
                 + `onmouseenter="alnHoverIn('${gk}')" `
                 + `onmouseleave="alnHoverOut()">`
                 + escapeHtml(tok)
                 + `</span>`;
        }).join(" ");
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;")
            .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }

    // Render a prose section with aligned tokens wrapped in interactive spans.
    // segKey is "chapter.section" e.g. "1.8" — namespaces the group keys.
    function renderAlignedProse(rawHtml, versionShortId, groups, pair, segKey) {
        if (!groups || groups.length === 0 || !activePairId) return rawHtml;
        const isSrc = (versionShortId === pair.src_version);
        const isTgt = (versionShortId === pair.tgt_version);
        if (!isSrc && !isTgt) return rawHtml;

        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = rawHtml;
        // Remove milestone/Bekker number spans before tokenizing —
        // they shift token indices and break index-based alignment matching.
        tempDiv.querySelectorAll('.inline-line-milestone, .milestone').forEach(el => el.remove());
        const plainText = (tempDiv.textContent || tempDiv.innerText || "").trim();
        const displayToks = plainText.split(/\s+/).filter(t => t.length > 0);
        if (displayToks.length === 0) return rawHtml;

        // Filter: remove mega-groups and low-confidence pairs
        const usable = filterGroups(groups,
            isSrc ? displayToks.length : 0,
            isTgt ? displayToks.length : 0);
        if (usable.length === 0) return rawHtml;

        // normalise for surface matching: lowercase, strip punctuation
        const norm = s => s.toLowerCase()
            .replace(/^[.,;:·῾᾿''"([\]]+/, "")
            .replace(/[.,;:!?·῾᾿''"")\]]+$/, "")
            .trim();

        // Build surface → {groupKey, score, color} using "segKey__origIdx" as key
        const surfaceMap = new Map();
        usable.forEach(({ group: g, origIdx }) => {
            const color = scoreToColor(g.sc);
            const toks  = isSrc ? g.st : g.tt;
            toks.forEach(tok => {
                const key = norm(tok);
                if (!key) return;
                const existing = surfaceMap.get(key);
                if (!existing || g.sc > existing.score) {
                    surfaceMap.set(key, {
                        groupKey: `${segKey}__${origIdx}`,
                        score: g.sc,
                        color
                    });
                }
            });
        });

        if (surfaceMap.size === 0) return rawHtml;

        const indexMap = new Map();
        displayToks.forEach((tok, idx) => {
            const info = surfaceMap.get(norm(tok));
            if (info) indexMap.set(idx, info);
        });

        if (indexMap.size === 0) return rawHtml;

        const side  = isSrc ? "src" : "tgt";
        const spans = buildAlignedTokenSpans(displayToks, indexMap, side);
        const outerMatch = rawHtml.match(/^<div([^>]*)>/);
        if (outerMatch) return `<div${outerMatch[1]}>${spans}</div>`;
        return `<span class="aln-inline">${spans}</span>`;
    }



    function triggerViewRefresh() {
        let currentBk = null, currentCh = "1";
        const currentActiveChEl = document.querySelector("#chapter-items-container a.current");
        if (currentActiveChEl) currentCh = currentActiveChEl.innerText;
        
        if (!isFlatStructure(activeWorkKey)) {
            const currentActiveBkEl = document.querySelector("#book-items-container a.current");
            // Book buttons are labelled "Book N" but DB stores bare "N"
            const rawBk = currentActiveBkEl ? currentActiveBkEl.innerText : `Book ${Object.keys(GLOBAL_STRUCTURES[activeWorkKey])[0]}`;
            currentBk = rawBk.replace(/^Book\s+/, "");
        }
        triggerTargetNavigation(currentBk, currentCh);
    }

    function updateURLState(book, chapter) {
        const params = new URLSearchParams();
        let passageValue = book ? `${book}.${chapter}` : `${chapter}`;
        if (activeSectionFilter) passageValue += `.${activeSectionFilter}`;

        params.set("w", `${activeWorkKey}:${passageValue}`);

        if (columnEditions.f) params.set("focus", columnEditions.f);
        if (columnEditions.c1) params.set("right", columnEditions.c1);
        if (columnEditions.c2) params.set("right2", columnEditions.c2);
        if (columnEditions.c3) params.set("right3", columnEditions.c3);
        if (columnEditions.c4) params.set("right4", columnEditions.c4);
        if (columnEditions.c5) params.set("right5", columnEditions.c5);
        if (columnEditions.c6) params.set("right6", columnEditions.c6);
        params.set("cols", activeColumnsCount.toString());

        window.history.replaceState(null, "", window.location.pathname + "?" + params.toString());
    }

    function selectSectionDirectly(secId) {
        activeSectionFilter = (activeSectionFilter === secId) ? null : secId;
        triggerViewRefresh();
    }

    function renderNavigationControls(payload) {
        const isDramaOrPoetry = isPoetryWork(activeWorkKey);
        
        const rowBook = document.getElementById("row-book-container");
        const rowChapter = document.getElementById("row-chapter-selector");
        const rowSection = document.getElementById("row-section-selector");

        if (currentActiveMode === 'classic') {
            if (rowBook) rowBook.classList.add("hidden-row");
            if (rowChapter) rowChapter.classList.add("hidden-row");
            if (rowSection) { if (isDramaOrPoetry) rowSection.classList.add("hidden-row"); else rowSection.classList.remove("hidden-row"); }
        } else {
            if (rowChapter) rowChapter.classList.remove("hidden-row");
            if (rowSection) { if (isDramaOrPoetry) rowSection.classList.add("hidden-row"); else rowSection.classList.remove("hidden-row"); }
            if (rowBook) { if (isFlatStructure(activeWorkKey)) rowBook.classList.add("hidden-row"); else rowBook.classList.remove("hidden-row"); }
        }

        if (currentActiveMode !== 'classic' && !isFlatStructure(activeWorkKey)) {
            const bookContainer = document.getElementById("book-items-container");
            if (bookContainer) {
                bookContainer.innerHTML = "";
                Object.keys(GLOBAL_STRUCTURES[activeWorkKey]).forEach(bk => {
                    const a = document.createElement("a"); a.innerText = `Book ${bk}`;
                    if(bk === payload.book) a.className = "current";
                    a.onclick = () => { activeSectionFilter = null; triggerTargetNavigation(bk, GLOBAL_STRUCTURES[activeWorkKey][bk][0]); };
                    bookContainer.appendChild(a);
                });
            }
        }

        const bookLabelEl = document.getElementById("chapter-row-label");
        if (bookLabelEl) bookLabelEl.innerText = isDramaOrPoetry ? "Lines:" : "Chapters:";

        const chapterContainer = document.getElementById("chapter-items-container");
        if (chapterContainer) {
            chapterContainer.innerHTML = "";
            const chList = isFlatStructure(activeWorkKey) ? GLOBAL_STRUCTURES[activeWorkKey] : GLOBAL_STRUCTURES[activeWorkKey][payload.book];
            chList.forEach(ch => {
                const a = document.createElement("a"); a.innerText = ch;
                if(ch === payload.chapter) a.className = "current";
                a.onclick = () => { activeSectionFilter = null; triggerTargetNavigation(payload.book, ch); };
                chapterContainer.appendChild(a);
            });
        }

        if (!isDramaOrPoetry) {
            const sectionContainer = document.getElementById("section-items-container");
            if (sectionContainer) {
                sectionContainer.innerHTML = "";
                naturalSectionKeys(payload.sections).forEach(sec => {
                    const a = document.createElement("a"); a.innerText = sec; a.className = "sec-pill";
                    if(sec === activeSectionFilter) a.classList.add("active-pill");
                    a.onclick = () => selectSectionDirectly(sec);
                    sectionContainer.appendChild(a);
                });
            }
        }

        const railNodesTarget = document.getElementById("rail-nodes-target");
        const railTitle = document.getElementById("rail-title");
        if (railNodesTarget) {
            railNodesTarget.innerHTML = "";
            if (isFlatStructure(activeWorkKey)) {
                railTitle.innerText = isDramaOrPoetry ? "Lines Tree" : "Chapters Tree";
                GLOBAL_STRUCTURES[activeWorkKey].forEach(ch => {
                    const n = document.createElement("div");
                    n.className = `rail-tree-item ${(payload.chapter === ch) ? 'active-rail-node' : ''}`;
                    n.innerText = isDramaOrPoetry ? `Lines ${ch}` : `Chapter ${ch}`;
                    n.onclick = () => { activeSectionFilter = null; triggerTargetNavigation(null, ch); };
                    railNodesTarget.appendChild(n);
                });
            } else {
                railTitle.innerText = isPoetryWork(activeWorkKey) ? `Book ${payload.book} Lines` : `Book ${payload.book} Chapters`;
                GLOBAL_STRUCTURES[activeWorkKey][payload.book].forEach(ch => {
                    const n = document.createElement("div");
                    n.className = `rail-tree-item ${(payload.chapter === ch) ? 'active-rail-node' : ''}`;
                    n.innerText = isPoetryWork(activeWorkKey) ? `Lines ${ch}` : `Chapter ${ch}`;
                    n.onclick = () => { activeSectionFilter = null; triggerTargetNavigation(payload.book, ch); };
                    railNodesTarget.appendChild(n);
                });
            }
        }
    }

    function tbSentMatchesSection(sent, filter, isPoetry) {
        if (!filter) return true;
        if (isPoetry) {
            return sent.chapter === filter;
        } else {
            return sent.section === filter;
        }
    }

function renderTreebankColumn(container, activeEditionMeta, payload) {
        const wKey = activeWorkKey;
        const vid  = activeEditionMeta.short_id;
        const tbKey = `${wKey}/${vid}`;
        const prefix = container.id.replace('content_', '');
        delete columnGreekOriginalHtml[prefix]; // treebank always uses the DOM-walk transliteration strategy
        const chapterData = TREEBANK_DATA[tbKey];
        if (!chapterData) {
            container.innerHTML = '<p style="color:#999;font-style:italic;padding:12px">No treebank data for this chapter.</p>';
            setTranslitControlVisible(prefix, false);
            return;
        }
        const chapter = payload.chapter;
        const allSentences = chapterData[chapter] || [];
        if (allSentences.length === 0) {
            container.innerHTML = '<p style="color:#999;font-style:italic;padding:12px">No treebank sentences for chapter ' + chapter + '.</p>';
            setTranslitControlVisible(prefix, false);
            return;
        }
        const speakerMap = SPEAKERS_DATA[wKey] || {};
        const docCredits = TREEBANK_DOC_CREDITS[tbKey] || { annotators: [], source: null };
        const isPoetry = isPoetryWork(wKey);
        container.innerHTML = '';

        // Reader row-visibility state (persists across treebank re-renders)
        if (!window.__tbRowVis) window.__tbRowVis = { original: true, translit: true };
        if (!window.__tbMode) window.__tbMode = 'text';
        if (!window.__tbGridRows) window.__tbGridRows = { translit:true, lemma:true, relation:true, pos:true, morph:true, gloss:true };
        container.classList.toggle('tb-hide-original', !window.__tbRowVis.original);
        container.classList.toggle('tb-hide-translit', !window.__tbRowVis.translit);

        const filter = activeSectionFilter;

        // Persistent tracking variable for poetry line breaks across sentences
        let lastSeenLineNum = null;

        // ── Control bar: view mode + row visibility ──
        const visBar = document.createElement('div');
        visBar.className = 'tb-vis-controls';

        // View-mode switch: Text (interlinear) vs Tree (dependency syntax tree)
        const modeWrap = document.createElement('span');
        modeWrap.className = 'tb-mode-switch';
        const mkMode = (text, val) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'tb-mode-btn' + (window.__tbMode === val ? ' tb-mode-on' : '');
            b.textContent = text;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                if (window.__tbMode === val) return;
                window.__tbMode = val;
                renderTreebankColumn(container, activeEditionMeta, payload);
            });
            return b;
        };
        modeWrap.appendChild(mkMode('Text', 'text'));
        modeWrap.appendChild(mkMode('Tree', 'tree'));
        visBar.appendChild(modeWrap);

        const visLabel = document.createElement('span');
        visLabel.className = 'tb-vis-label';
        visLabel.textContent = 'show';
        visBar.appendChild(visLabel);

        if ((window.__tbMode || 'text') === 'tree') {
            // Tree mode: toggle which annotation rows appear in the word grid
            const gridLabels = { translit:'Translit', lemma:'Lemma', relation:'Relation', pos:'POS', morph:'Morph', gloss:'Gloss' };
            const mkGridToggle = (key) => {
                const on = window.__tbGridRows[key] !== false;
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'tb-vis-btn' + (on ? ' tb-vis-on' : '');
                b.textContent = gridLabels[key];
                b.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const now = !(window.__tbGridRows[key] !== false);
                    window.__tbGridRows[key] = now;
                    b.classList.toggle('tb-vis-on', now);
                    container.querySelectorAll('.tb-grid').forEach(g => g.classList.toggle('tb-ghide-' + key, !now));
                });
                return b;
            };
            ['translit','lemma','relation','pos','morph','gloss'].forEach(k => visBar.appendChild(mkGridToggle(k)));
        } else {
            // Text mode: show/hide the Arabic and transliteration rows
            const mkVisToggle = (text, key) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'tb-vis-btn' + (window.__tbRowVis[key] ? ' tb-vis-on' : '');
                b.textContent = text;
                b.addEventListener('click', (e) => {
                    e.stopPropagation();
                    window.__tbRowVis[key] = !window.__tbRowVis[key];
                    b.classList.toggle('tb-vis-on', window.__tbRowVis[key]);
                    container.classList.toggle('tb-hide-' + key, !window.__tbRowVis[key]);
                });
                return b;
            };
            visBar.appendChild(mkVisToggle('Original', 'original'));
            if (!isPoetry) visBar.appendChild(mkVisToggle('Translit', 'translit'));
        }
        container.appendChild(visBar);

        allSentences.forEach(sent => {
            const inFocus = tbSentMatchesSection(sent, filter, isPoetry);
            const block = document.createElement('div');
            block.className = 'tb-sentence-block' + (inFocus ? '' : ' tb-sent-dimmed');
            block.dataset.subdoc = sent.subdoc;
            block.dataset.section = sent.section;
            block.dataset.chapter = sent.chapter;

            // Citation label
            const citEl = document.createElement('div');
            citEl.className = 'tb-cit-label';
            citEl.innerHTML = `<a href="javascript:void(0)" onclick="selectSectionDirectly('${
                isPoetry ? sent.chapter : sent.section
            }')" title="Focus this sentence">${sent.subdoc}</a>`;
            block.appendChild(citEl);

            // Speaker (drama only)
            const speaker = speakerMap[sent.subdoc];
            if (speaker) {
                const spkEl = document.createElement('div');
                spkEl.className = 'tb-speaker';
                spkEl.innerHTML = '<strong>Speaker:</strong> ' + speaker;
                block.appendChild(spkEl);
            }

            // Credits: prefer this sentence's own "# sentannotators" (the
            // exception — some files vary annotator by sentence); otherwise
            // fall back to the document-level roster (the common case).
            const sentCredits = sent.credits
                || (docCredits.annotators.length
                    ? docCredits.annotators.map(a => ({ name: a.name, address: a.address, role: null }))
                    : null);
            if ((sentCredits && sentCredits.length) || docCredits.source) {
                const credWrap = document.createElement('div');
                credWrap.className = 'tb-credits-wrap';
                const toggle = document.createElement('a');
                toggle.href = 'javascript:void(0)';
                toggle.className = 'tb-credits-toggle';
                toggle.textContent = 'Show Metadata';
                const box = document.createElement('div');
                box.className = 'tb-credits-box';
                box.style.display = 'none';
                if (sentCredits && sentCredits.length) {
                    const annotSection = document.createElement('div');
                    annotSection.className = 'tb-credits-section';
                    annotSection.innerHTML = '<div class="tb-credits-heading">Annotator</div>' +
                        sentCredits.map(c =>
                            `<div class="tb-credits-line">${escHtml(c.name)}${c.address ? ', ' + escHtml(c.address) : ''}</div>`
                        ).join('');
                    box.appendChild(annotSection);
                }
                if (docCredits.source) {
                    const srcSection = document.createElement('div');
                    srcSection.className = 'tb-credits-section';
                    srcSection.innerHTML = '<div class="tb-credits-heading">Source</div>' +
                        `<div class="tb-credits-line">${escHtml(docCredits.source)}</div>`;
                    box.appendChild(srcSection);
                }
                toggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isOpen = box.style.display !== 'none';
                    box.style.display = isOpen ? 'none' : '';
                    toggle.textContent = isOpen ? 'Show Metadata' : 'Hide Metadata';
                });
                credWrap.appendChild(toggle);
                credWrap.appendChild(box);
                block.appendChild(credWrap);
            }

            // Prose translation on top, so Arabic / translit / gloss / treebank sit together below it
            if (sent.prose) {
                const trans = document.createElement('div');
                trans.className = 'tb-translation';
                const proDiv = document.createElement('div');
                proDiv.className = 'tb-trans-prose';
                proDiv.innerHTML = `<span class="tb-trans-label">Translation</span> ${escHtml(sent.prose)}`;
                trans.appendChild(proDiv);
                block.appendChild(trans);
            }

            // Filled in once the token-selection handler (tbSelect, or the poetry
            // equivalent) exists below — lets the tokenised translit spans below
            // trigger the same cross-row highlight even though they're built first.
            let tbSelectRef = null;

            if (sent.translit) {
                const trLine = document.createElement('div');
                trLine.className = 'tb-trans-translit';
                trLine.setAttribute('dir', 'ltr');
                const trLabel = document.createElement('span');
                trLabel.className = 'tb-trans-label';
                trLabel.textContent = 'Translit';
                trLine.appendChild(trLabel);
                trLine.appendChild(document.createTextNode(' '));

                if (sent.tokens.some(t => t.translit)) {
                    // Tokenised: one span per token, carrying the same data-tok-id
                    // as the original-script row, gloss row, and literal row, so
                    // clicking (or being selected via) any of them highlights here too.
                    sent.tokens.forEach(tok => {
                        const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                        const trSpan = document.createElement('span');
                        trSpan.className = 'tb-tok tb-translit-tok' + (isPunct ? ' tb-punct' : '');
                        trSpan.dataset.tokId = tok.id;
                        trSpan.textContent = tok.translit || tok.form;
                        if (!isPunct) trSpan.addEventListener('click', (e) => {
                            e.stopPropagation();
                            if (tbSelectRef) tbSelectRef(tok.id);
                        });
                        trLine.appendChild(trSpan);
                        if (!isPunct) trLine.appendChild(document.createTextNode(' '));
                    });
                } else {
                    // No per-token translit data on this sentence — fall back to the
                    // plain sentence-level string (not click/highlightable).
                    trLine.appendChild(document.createTextNode(sent.translit));
                }
                block.appendChild(trLine);
            }


            // ── View mode: 'tree' = full annotation grid + collapsible dependency tree; 'text' = interlinear rows ──
            const tbMode = window.__tbMode || 'text';
            if (tbMode === 'tree') {
                tbRenderGrid(block, sent);   // grid: every annotation as a row, one column per word (replaces interlinear)
                tbRenderTree(block, sent);   // collapsible dependency syntax tree below the grid
             } else {
            // Token row layout configuration
            const tokRow = document.createElement('div');
            tokRow.className = 'tb-token-row';
            
            // Build literal alignment maps for this sentence
            const litWords    = tbTokeniseLiteral(sent.literal);
            const alignment   = tbBuildAlignment(sent.tokens, litWords);
            const revAlignment = tbBuildReverseAlignment(alignment);

            // Shared selection: keeps the Arabic and transliteration rows in sync
            const tbSelect = (tokId) => {
                const tok = sent.tokens.find(t => t.id === tokId);
                if (!tok) return;
                const alreadyActive = !!block.querySelector(`.tb-tok.tb-active[data-tok-id="${tokId}"]`);
                block.querySelectorAll('.tb-tok').forEach(s => s.classList.remove('tb-active','tb-is-head','tb-is-dep'));
                block.querySelectorAll('.tb-lit-word').forEach(s => s.classList.remove('tb-lit-active'));
                const panel = block.querySelector('.tb-detail-panel');
                if (panel) { panel.innerHTML = ''; panel.classList.remove('tb-detail-visible'); }
                if (alreadyActive) return;
                block.querySelectorAll(`[data-tok-id="${tokId}"]`).forEach(s => s.classList.add('tb-active'));
                if (tok.head > 0)
                    block.querySelectorAll(`[data-tok-id="${tok.head}"]`).forEach(s => s.classList.add('tb-is-head'));
                sent.tokens.filter(t => t.head === tok.id).forEach(dep =>
                    block.querySelectorAll(`[data-tok-id="${dep.id}"]`).forEach(s => s.classList.add('tb-is-dep')));
                tbHighlightLiteral(block, alignment, tok.id, true);
                const headTok = tok.head > 0 ? sent.tokens.find(t => t.id === tok.head) : null;
                const depToks = sent.tokens.filter(t => t.head === tok.id && t.upos !== 'PUNCT');
                if (panel) {
                    panel.innerHTML = renderTokenDetail(tok, headTok, depToks);
                    panel.classList.add('tb-detail-visible');
                    _tbApplyTranslitToPanel(panel);
                }
            };
            tbSelectRef = tbSelect;

            if (isPoetry) {
                // Poetry Grid Container to match your standard 5-column structural layout rule
                const poetryGrid = document.createElement('div');
                poetryGrid.className = 'poetry-grid-layout';
                
                let currentLineWrapper = null;
                let currentTokensRow = null;
                let currentGlossRow = null;
                const sentHasGloss = sent.tokens.some(t => t.gloss);

                function startNewLineWrapper() {
                    currentLineWrapper = document.createElement('div');
                    currentLineWrapper.className = 'line-text-cell';
                    currentTokensRow = document.createElement('div');
                    currentTokensRow.className = 'line-tokens-row';
                    currentLineWrapper.appendChild(currentTokensRow);
                    if (sentHasGloss) {
                        currentGlossRow = document.createElement('div');
                        currentGlossRow.className = 'line-gloss-row tb-gloss-row';
                        currentLineWrapper.appendChild(currentGlossRow);
                    } else {
                        currentGlossRow = null;
                    }
                }

                sent.tokens.forEach((tok, tIdx) => {
                    const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                    const currentTokenLine = tok.ref ? tok.ref.trim() : null;

                    // 1. Detect if this is the very start of a sentence AND it continues an existing line
                    if (tIdx === 0 && currentTokenLine && currentTokenLine === lastSeenLineNum) {
                        // Insert an inline indentation block to signal an antilabe/mid-line sentence split
                        if (!currentLineWrapper) startNewLineWrapper();
                        const indentSpacer = document.createElement('span');
                        indentSpacer.style.display = 'inline-block';
                        indentSpacer.style.width = '3em';
                        indentSpacer.innerHTML = '&nbsp;';
                        currentTokensRow.appendChild(indentSpacer);
                        if (currentGlossRow) {
                            const glIndentSpacer = document.createElement('span');
                            glIndentSpacer.style.display = 'inline-block';
                            glIndentSpacer.style.width = '3em';
                            glIndentSpacer.innerHTML = '&nbsp;';
                            currentGlossRow.appendChild(glIndentSpacer);
                        }
                    }

                    // 2. Handle a brand new line number boundary shift
                    if (currentTokenLine && currentTokenLine !== lastSeenLineNum) {
                        // Flush previous text cell container if it exists
                        if (currentLineWrapper) {
                            poetryGrid.appendChild(currentLineWrapper);
                        }
                        
                        lastSeenLineNum = currentTokenLine;

                        // Create line number margin anchor cell
                        const numCell = document.createElement('div');
                        numCell.className = 'line-num-cell';
                        numCell.innerText = currentTokenLine;
                        poetryGrid.appendChild(numCell);

                        // Create matching text container cell for tokens on this line
                        // (holds a token row and, when this sentence carries glosses, a
                        // gloss row stacked directly beneath it so glosses follow the
                        // poetic linebreaks rather than sentence breaks)
                        startNewLineWrapper();
                    }

                    // Fallback container wrap if metadata fields are missing a Ref tag
                    if (!currentLineWrapper) {
                        startNewLineWrapper();
                    }

                    // Build token span item
                    const span = document.createElement('span');
                    span.className = 'tb-tok' + (isPunct ? ' tb-punct' : '');
                    span.dataset.tokId = tok.id;
                    span.textContent = tok.form;

                    // Matching gloss span, stacked directly under this token on the
                    // line's own gloss row (skips punctuation, same as the prose gloss row)
                    let glossSpan = null;
                    if (currentGlossRow && !isPunct) {
                        glossSpan = document.createElement('span');
                        glossSpan.className = 'tb-tok tb-gloss-tok';
                        glossSpan.dataset.tokId = tok.id;
                        glossSpan.textContent = tok.gloss || '·';
                    }

                    if (!isPunct) {
                        // Shared with prose: block-scoped (not poetryGrid-scoped), so it
                        // also lights up matching data-tok-id spans that live outside the
                        // poetry grid — e.g. the tokenised translit row above.
                        const selectThisToken = (e) => {
                            e.stopPropagation();
                            tbSelect(tok.id);
                        };
                        span.addEventListener('click', selectThisToken);
                        if (glossSpan) glossSpan.addEventListener('click', selectThisToken);
                    }

                    currentTokensRow.appendChild(span);
                    if (!isPunct) currentTokensRow.appendChild(document.createTextNode(' '));
                    if (currentGlossRow) {
                        if (glossSpan) currentGlossRow.appendChild(glossSpan);
                        if (!isPunct) currentGlossRow.appendChild(document.createTextNode(' '));
                    }
                });

                // Append trailing grid line row to final grid container
                if (currentLineWrapper) {
                    poetryGrid.appendChild(currentLineWrapper);
                }
                tokRow.appendChild(poetryGrid);
            } else {
                // Standard Prose Layout Logic Flow
                sent.tokens.forEach(tok => {
                    const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                    const span = document.createElement('span');
                    span.className = 'tb-tok' + (isPunct ? ' tb-punct' : '');
                    span.dataset.tokId = tok.id;
                    span.textContent = tok.form;
                    if (!isPunct) span.addEventListener('click', (e) => { e.stopPropagation(); tbSelect(tok.id); });
                    tokRow.appendChild(span);
                    if (!isPunct) tokRow.appendChild(document.createTextNode(' '));
                });
            }
            block.appendChild(tokRow);

            if (litWords.length) {
                const litRow = document.createElement('div');
                litRow.className = 'tb-literal-row';
                litRow.innerHTML = `<span class="tb-trans-label">Literal</span> ${tbLiteralHtml(litWords)}`;
                block.appendChild(litRow);
            }

            // Parallel clickable transliteration row (one span per token, same selection)
            if (!isPoetry && sent.tokens.some(t => t.translit)) {
                const trRow = document.createElement('div');
                trRow.className = 'tb-translit-row';
                sent.tokens.forEach(tok => {
                    const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                    const span = document.createElement('span');
                    span.className = 'tb-tok tb-translit-tok' + (isPunct ? ' tb-punct' : '');
                    span.dataset.tokId = tok.id;
                    span.textContent = tok.translit || tok.form;
                    if (!isPunct) span.addEventListener('click', (e) => { e.stopPropagation(); tbSelect(tok.id); });
                    trRow.appendChild(span);
                    if (!isPunct) trRow.appendChild(document.createTextNode(' '));
                });
                block.appendChild(trRow);
            }

            // Parallel clickable GLOSS row (one span per token, same selection) —
            // replaces the literal translation so Arabic / translit / gloss align one-to-one.
            if (!isPoetry && sent.tokens.some(t => t.gloss)) {
                const glRow = document.createElement('div');
                glRow.className = 'tb-gloss-row';
                sent.tokens.forEach(tok => {
                    const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                    if (isPunct) return;
                    const span = document.createElement('span');
                    span.className = 'tb-tok tb-gloss-tok';
                    span.dataset.tokId = tok.id;
                    span.textContent = tok.gloss || '·';
                    span.addEventListener('click', (e) => { e.stopPropagation(); tbSelect(tok.id); });
                    glRow.appendChild(span);
                    glRow.appendChild(document.createTextNode(' '));
                });
                block.appendChild(glRow);
            }
            } // end view-mode branch

            const detailPanel = document.createElement('div');
            detailPanel.className = 'tb-detail-panel';
            block.appendChild(detailPanel);

            block.addEventListener('click', () => {
                block.querySelectorAll('.tb-tok').forEach(s => s.classList.remove('tb-active','tb-is-head','tb-is-dep'));
                block.querySelectorAll('.tb-lit-word').forEach(s => s.classList.remove('tb-lit-active'));
                detailPanel.innerHTML = '';
                detailPanel.classList.remove('tb-detail-visible');
            });

            container.appendChild(block);
        });

        if (filter) {
            const focused = container.querySelector('.tb-sentence-block:not(.tb-sent-dimmed)');
            if (focused) focused.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        const footer = document.createElement('div');
        footer.className = 'viewport-footer-controls';
        let prevBtnHtml = '', nextBtnHtml = '';
        if (payload.navigation && payload.navigation.prev) {
            const prevParts = payload.navigation.prev.split(':');
            const prevPsg   = prevParts[prevParts.length - 1].split('.');
            const label     = isPoetry ? `Lines ${prevPsg[1]}` : (isFlatStructure(wKey) ? `Ch ${prevPsg[0]}` : `Bk ${prevPsg[0]} Ch ${prevPsg[1]}`);
            prevBtnHtml = `<a class="action-btn" onclick="navigateAdjacentUrn('${payload.navigation.prev}')">&larr; Previous (${label})</a>`;
        }
        if (payload.navigation && payload.navigation.next) {
            const nextParts = payload.navigation.next.split(':');
            const nextPsg   = nextParts[nextParts.length - 1].split('.');
            const label     = isPoetry ? `Lines ${nextPsg[1]}` : (isFlatStructure(wKey) ? `Ch ${nextPsg[0]}` : `Bk ${nextPsg[0]} Ch ${nextPsg[1]}`);
            nextBtnHtml = `<a class="action-btn" onclick="navigateAdjacentUrn('${payload.navigation.next}')">Next (${label}) &rarr;</a>`;
        }
        footer.innerHTML = `
            <div class="footer-group-left">
                ${prevBtnHtml}
                <a href="javascript:void(0)" class="action-btn secondary" onclick="clearSectionFilter(event)">Full View</a>
            </div>
            ${nextBtnHtml}
        `;
        container.appendChild(footer);

        // Greek transliteration: same content-based detection as reading
        // columns, but applied via DOM text-node walking (walkAndTransliterateNode)
        // rather than an innerHTML swap, since the treebank view attaches its
        // click-to-highlight/detail-panel handlers with addEventListener —
        // replacing innerHTML here would silently strip them.
        const hasGreek = GREEK_HAS_REGEX.test(container.textContent);
        setTranslitControlVisible(prefix, hasGreek);
        if (hasGreek) {
            const savedMode = document.getElementById(`translit_${prefix}`);
            if (savedMode) savedMode.value = columnTranslitMode[prefix] || '';
            applyGreekTransliteration(prefix);
        }
    }

    function renderMetricalColumn(container, activeEditionMeta, payload) {
        const wKey  = activeWorkKey;
        const vid   = activeEditionMeta.short_id;
        const mKey  = `${wKey}/${vid}`;
        const prefix = container.id.replace('content_', '');
        delete columnGreekOriginalHtml[prefix]; // metrical always uses the DOM-walk transliteration strategy
        const chapterData = METRICAL_DATA[mKey];
        if (!chapterData) {
            container.innerHTML = '<p style="color:#999;font-style:italic;padding:12px">No metrical data loaded.</p>';
            setTranslitControlVisible(prefix, false);
            return;
        }
        const chapter = payload.chapter;
        const lineMap = chapterData[chapter];
        if (!lineMap || Object.keys(lineMap).length === 0) {
            container.innerHTML = `<p style="color:#999;font-style:italic;padding:12px">No metrical data for chapter ${chapter}.</p>`;
            setTranslitControlVisible(prefix, false);
            return;
        }

        container.innerHTML = '';
        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'padding:12px 8px;font-family:"Gentium Plus","Gentium Book Basic","Times New Roman",serif;';

        const sortedRefs = Object.keys(lineMap).sort((a, b) => {
            const [ab, al] = a.split('.').map(Number);
            const [bb, bl] = b.split('.').map(Number);
            return ab !== bb ? ab - bb : al - bl;
        });

        sortedRefs.forEach(lineRef => {
            const words = lineMap[lineRef];
            if (!words || words.length === 0) return;

            const lineUnit = document.createElement('div');
            lineUnit.dataset.ref = lineRef;
            lineUnit.style.cssText = 'margin-bottom:2.4rem;';

            // Line reference label
            const refLabel = document.createElement('span');
            refLabel.style.cssText = 'font-family:monospace;font-size:0.78rem;color:#94a3b8;display:block;margin-bottom:6px;';
            refLabel.textContent = lineRef;
            lineUnit.appendChild(refLabel);

            // Flatten syllables with mora positions
            const syllables = [];
            words.forEach((w, wi) => {
                let mora = w.start;
                w.syls.forEach(syl => {
                    const weight = syl.q === 'long' ? 2 : syl.q === 'short' ? 1 : 0;
                    if (syl.q !== 'onset') {
                        syllables.push({ q: syl.q, text: syl.text, mora, word_idx: wi });
                    }
                    mora += weight;
                });
            });

            // Caesura/diaeresis foot marks (foot 0-5)
            const footMarks = {};
            words.forEach(w => {
                w.tags.forEach(tag => {
                    if (tag.startsWith('caes')) {
                        const fn = parseInt(tag.replace(/[^0-9]/g,'')) - 1;
                        if (!isNaN(fn)) footMarks[fn] = 'caesura';
                    }
                    if (tag.startsWith('diaer') || tag === 'bucdiaer') {
                        const fn = tag === 'bucdiaer' ? 3 : parseInt(tag.replace(/[^0-9]/g,'')) - 1;
                        if (!isNaN(fn)) footMarks[fn] = 'diaeresis';
                    }
                });
            });

            // Group syllables into 6 feet (4 morae each)
            const feet = [[], [], [], [], [], []];
            syllables.forEach(syl => {
                const fi = Math.min(5, Math.floor((syl.mora - 1) / 4));
                feet[fi].push(syl);
            });

            // Scansion bar
            const metricalBar = document.createElement('div');
            metricalBar.style.cssText = 'display:flex;align-items:center;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;flex-wrap:wrap;';

            feet.forEach((footSyls, fi) => {
                if (footSyls.length === 0) return;
                const footEl = document.createElement('div');
                footEl.style.cssText = 'display:flex;align-items:flex-end;padding:0 3px;padding-top:20px;position:relative;';

                footSyls.forEach(syl => {
                    const sylEl = document.createElement('span');
                    sylEl.style.cssText = 'position:relative;padding:0 5px;font-size:0.92rem;display:inline-block;';
                    const mark = document.createElement('span');
                    mark.style.cssText = 'position:absolute;left:50%;transform:translateX(-50%);top:-16px;font-weight:700;';
                    if (syl.q === 'long') {
                        mark.textContent = '–'; mark.style.color = '#1d4ed8'; mark.style.fontSize = '1.05rem';
                    } else {
                        mark.textContent = '˘'; mark.style.color = '#b91c1c'; mark.style.fontSize = '1.2rem';
                    }
                    sylEl.appendChild(mark);
                    const txt = document.createElement('span');
                    txt.textContent = syl.text;
                    txt.style.color = '#111827';
                    sylEl.appendChild(txt);
                    footEl.appendChild(sylEl);
                });

                if (fi < 5) {
                    const sep = document.createElement('span');
                    sep.style.cssText = 'margin:0 4px 0 6px;font-size:1.1rem;align-self:flex-end;padding-bottom:1px;font-weight:300;';
                    if      (footMarks[fi] === 'caesura')   { sep.style.color = '#059669'; sep.style.fontWeight = '600'; }
                    else if (footMarks[fi] === 'diaeresis') { sep.style.color = '#7c3aed'; sep.style.fontWeight = '600'; }
                    else { sep.style.color = '#94a3b8'; }
                    sep.textContent = '|';
                    footEl.appendChild(sep);
                }
                metricalBar.appendChild(footEl);
            });
            lineUnit.appendChild(metricalBar);

            // Word row with tags
            const wordRow = document.createElement('div');
            wordRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:1.2rem;padding:6px 14px 2px;align-items:flex-start;';

            words.forEach(w => {
                const wEl = document.createElement('div');
                wEl.style.cssText = 'display:flex;flex-direction:column;align-items:center;min-width:44px;';
                const wTxt = document.createElement('span');
                wTxt.style.cssText = 'font-size:1.35rem;font-weight:500;color:#111827;white-space:nowrap;';
                wTxt.textContent = w.word;
                wEl.appendChild(wTxt);
                const posLabel = document.createElement('span');
                posLabel.style.cssText = 'font-family:monospace;font-size:0.68rem;color:#6b7280;background:#f3f4f6;padding:1px 4px;border-radius:3px;margin-top:3px;';
                posLabel.textContent = `${w.start}–${w.end}`;
                wEl.appendChild(posLabel);
                if (w.tags && w.tags.length > 0) {
                    const tagBox = document.createElement('div');
                    tagBox.style.cssText = 'display:flex;flex-direction:column;gap:2px;margin-top:4px;width:100%;';
                    w.tags.forEach(tag => {
                        const badge = document.createElement('span');
                        badge.style.cssText = 'font-family:system-ui,sans-serif;font-size:0.62rem;font-weight:600;text-transform:uppercase;letter-spacing:0.03em;padding:1px 4px;border-radius:3px;text-align:center;white-space:nowrap;';
                        const tl = tag.toLowerCase();
                        if      (tl.startsWith('caes'))                         { badge.style.cssText += 'background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;'; }
                        else if (tl.startsWith('diaer') || tl === 'bucdiaer')  { badge.style.cssText += 'background:#f5f3ff;color:#6d28d9;border:1px solid #ddd6fe;'; }
                        else if (tl.startsWith('long2') || tl === 'synizesis') { badge.style.cssText += 'background:#fff7ed;color:#c2410c;border:1px solid #ffedd5;'; }
                        else                                                    { badge.style.cssText += 'background:#f8fafc;color:#64748b;border:1px solid #e2e8f0;'; }
                        badge.textContent = tag.split(':')[0];
                        tagBox.appendChild(badge);
                    });
                    wEl.appendChild(tagBox);
                }
                wordRow.appendChild(wEl);
            });
            lineUnit.appendChild(wordRow);
            wrapper.appendChild(lineUnit);
        });
        container.appendChild(wrapper);

        // Greek transliteration: same DOM-walk strategy as the treebank view.
        // Metrical lines are built purely with createElement/textContent (no
        // click handlers at all here), so this is even lower-risk than treebank.
        const hasGreek = GREEK_HAS_REGEX.test(container.textContent);
        setTranslitControlVisible(prefix, hasGreek);
        if (hasGreek) {
            const savedMode = document.getElementById(`translit_${prefix}`);
            if (savedMode) savedMode.value = columnTranslitMode[prefix] || '';
            applyGreekTransliteration(prefix);
        }
    }

    function tbNorm(s) {
        if (!s) return '';
        return s.toLowerCase()
                .replace(/[\(\)\’.,;:?!·;]/g, '')
                // .replace(/-/g, ' ')
                .trim();
    }

    function tbTokeniseLiteral(literal) {
        if (!literal) return [];
        const words = [];
        literal.split(/\s+/).forEach((orig, i) => {
            const norm    = tbNorm(orig);
            const display = orig;
            words.push({ orig, display, norm, idx: i, subwords: norm.split(' ') });
        });
        return words;
    }

    function tbBuildAlignment(tokens, litWords) {
        const alignment = new Map();
        if (!litWords || litWords.length === 0) return alignment;

        let cursor = 0;
        const n = litWords.length;

        tokens.forEach(tok => {
            if (!tok.gloss || tok.upos === 'PUNCT' || tok.upos === '_') return;

            const gWords = tbNorm(tok.gloss).split(/\s+/).filter(Boolean);
            if (gWords.length === 0) return;
            const m = gWords.length;

            const windowMatch = (i) => litWords[i].norm === gWords[0];
            const matchEnd = (i) => i;

            let found = -1, foundEnd = -1;
            for (let i = cursor; i < n; i++) {
                if (windowMatch(i)) { found = i; foundEnd = matchEnd(i); break; }
            }

            if (found < 0 && m === 1) {
                for (let i = cursor; i < n; i++) {
                    if (litWords[i].subwords.includes(gWords[0])) { found = i; foundEnd = i; break; }
                }
            }

            if (found < 0 && m > 1) {
                let bestScore = 0, bestI = -1;
                for (let i = cursor; i < n; i++) {
                    let hits = 0;
                    for (let j = 0; j < m && i + j < n; j++) {
                        if (litWords[i+j].subwords.includes(gWords[j])) hits++;
                    }
                    const score = hits / m;
                    if (score > bestScore && score >= 0.5) { bestScore = score; bestI = i; }
                }
                if (bestI >= 0) { found = bestI; foundEnd = matchEnd(bestI); }
            }

            if (found < 0) {
                for (let i = 0; i < n; i++) {
                    if (windowMatch(i)) { found = i; foundEnd = matchEnd(i); break; }
                }
            }
            if (found < 0 && m === 1) {
                for (let i = 0; i < n; i++) {
                    if (litWords[i].subwords.includes(gWords[0])) { found = i; foundEnd = i; break; }
                }
            }

            if (found >= 0) {
                alignment.set(tok.id, { start: found, end: foundEnd });
                if (found >= cursor) cursor = foundEnd + 1;
            }
        });

        return alignment;
    }

    function tbLiteralHtml(litWords) {
        return litWords.map((w, i) =>
            `<span class="tb-lit-word" data-li="${i}" title="${escHtml(w.orig)}">${escHtml(w.display)}</span>`
        ).join(' ');
    }

    function tbBuildReverseAlignment(alignment) {
        const rev = new Map();
        alignment.forEach((span, tokId) => {
            for (let i = span.start; i <= span.end; i++) {
                if (!rev.has(i)) rev.set(i, tokId);
            }
        });
        return rev;
    }

    function tbHighlightLiteral(block, alignment, tokId, on) {
        const span = alignment.get(tokId);
        if (!span) return;
        for (let i = span.start; i <= span.end; i++) {
            const el = block.querySelector(`.tb-lit-word[data-li="${i}"]`);
            if (el) el.classList.toggle('tb-lit-active', on);
        }
    }

    function renderTokenDetail(tok, headTok, depToks) {
        const rc = tbRelColor(tok.deprel);
        const pc = tbPosColor(tok.upos);
        let h = `<div class="tb-detail-word">${escHtml(tok.form)}</div><div class="tb-detail-grid">`;
        if (tok.translit)
            h += `<span class="tb-dk">Translit</span><span class="tb-dv" dir="ltr" style="font-style:italic">${escHtml(tok.translit)}</span>`;
        if (tok.gloss)
            h += `<span class="tb-dk">Gloss</span><span class="tb-dv tb-gloss">${escHtml(tok.gloss)}</span>`;
        if (tok.lemma && tok.lemma !== '_' && tok.lemma !== tok.form)
            h += `<span class="tb-dk">Lemma</span><span class="tb-dv tb-greek">${escHtml(tok.lemma)}${tok.ltranslit ? ' <span dir="ltr" style="font-style:italic;color:#888;font-size:11px">'+escHtml(tok.ltranslit)+'</span>' : ''}</span>`;
        if (tok.upos && tok.upos !== '_')
            h += `<span class="tb-dk">Part of Speech</span><span class="tb-dv"><span class="tb-pos-chip" style="color:${pc};border-color:${pc}40">${escHtml(tok.upos)}</span>${tok.xpos && tok.xpos !== '_' && tok.xpos !== tok.upos ? ' <span class="tb-xpos">'+escHtml(tok.xpos)+'</span>' : ''}</span>`;
        h += `<span class="tb-dk">Dependency</span><span class="tb-dv"><span class="tb-rel-chip" style="background:${rc}">${escHtml(tok.deprel)}</span></span>`;
        if (headTok)
            h += `<span class="tb-dk">Head</span><span class="tb-dv tb-greek">${escHtml(headTok.form)} <span style="font-size:10px;color:#aaa">[${headTok.id}]</span></span>`;
        else
            h += `<span class="tb-dk">Head</span><span class="tb-dv" style="color:#660000;font-weight:bold">Root</span>`;
        if (tok.feats && tok.feats !== '_') {
            const fp = tok.feats.split('|').map(f => { const [k,v] = f.split('='); return `<span class="tb-feat-k">${k}</span>=<span class="tb-feat-v">${v}</span>`; }).join(' ');
            h += `<span class="tb-dk">Morph</span><span class="tb-dv tb-feats">${fp}</span>`;
        }
        if (depToks.length > 0) {
            const dl = depToks.map(d => `<span class="tb-rel-chip" style="background:${tbRelColor(d.deprel)};font-size:9px">${escHtml(d.deprel)}</span>&nbsp;<span class="tb-greek">${escHtml(d.form)}</span>`).join('&ensp;');
            h += `<span class="tb-dk">Depends</span><span class="tb-dv">${dl}</span>`;
        }
        return h + '</div>';
    }

    // ── Dependency syntax-tree renderer (Tree mode) ──
    // Top-down tree: ROOT at top, words placed by syntactic structure, relation on each edge.
    // Hovering a word highlights its head and its dependents. Clicking a word with children
    // collapses/expands its subtree; clicking a leaf opens the detail panel.
    function tbRenderTree(block, sent) {
        const toks = (sent.tokens || []);
        if (!toks.length) return;
        const SVGNS = 'http://www.w3.org/2000/svg';
        const byId = new Map(); toks.forEach(t => byId.set(t.id, t));
        const headOf = (t) => { let h = (typeof t.head === 'number') ? t.head : 0; if (h !== 0 && !byId.has(h)) h = 0; return h; };
        const kids = new Map(); kids.set(0, []);
        toks.forEach(t => kids.set(t.id, []));
        toks.forEach(t => kids.get(headOf(t)).push(t.id));
        kids.forEach(a => a.sort((x, y) => x - y));

        const descCount = new Map();
        const countDesc = (id) => { let n = 0; (kids.get(id) || []).forEach(c => { n += 1 + countDesc(c); }); descCount.set(id, n); return n; };
        countDesc(0);

        const collapsed = new Set();
        const SLOT = 108, ROW = 96, PADX = 30, PADY = 22, LBH = 50;
        const wrap = document.createElement('div'); wrap.className = 'tb-tree-wrap';
        block.appendChild(wrap);

        const mk = (name, attrs, cls) => {
            const el = document.createElementNS(SVGNS, name);
            if (cls) el.setAttribute('class', cls);
            for (const k in attrs) el.setAttribute(k, attrs[k]);
            return el;
        };
        const clip = (s, n) => { s = s || ''; return s.length > n ? s.slice(0, n) + '...' : s; };

        const draw = () => {
            wrap.innerHTML = '';
            const eff = (id) => collapsed.has(id) ? [] : (kids.get(id) || []);
            const depth = new Map(); depth.set(0, 0);
            const q = [0]; let guard = 0;
            while (q.length && guard++ < 200000) { const u = q.shift(); eff(u).forEach(c => { if (!depth.has(c)) { depth.set(c, depth.get(u) + 1); q.push(c); } }); }
            let leaf = 0; const xOf = new Map();
            const placeX = (id) => {
                const ch = eff(id);
                if (!ch.length) { const x = leaf * SLOT + PADX + SLOT / 2; xOf.set(id, x); leaf++; return x; }
                let lo = Infinity, hi = -Infinity;
                ch.forEach(c => { const cx = placeX(c); if (cx < lo) lo = cx; if (cx > hi) hi = cx; });
                const x = (lo + hi) / 2; xOf.set(id, x); return x;
            };
            placeX(0);
            let maxD = 0; depth.forEach(d => { if (d > maxD) maxD = d; });
            const width = Math.max(leaf, 1) * SLOT + PADX * 2;
            const height = (maxD + 1) * ROW + PADY * 2;
            const y0 = (id) => depth.get(id) * ROW + PADY;
            const topY = (id) => y0(id) + 2;
            const botY = (id) => y0(id) + LBH;

            const svg = mk('svg', { width: width, height: height, viewBox: '0 0 ' + width + ' ' + height }, 'tb-tree-svg');

            // edges (visible nodes only)
            toks.forEach(t => {
                if (!depth.has(t.id)) return;
                const h = headOf(t);
                if (h !== 0 && !depth.has(h)) return;
                const px = xOf.get(h), cx = xOf.get(t.id);
                const py = (h === 0) ? (PADY + 14) : botY(h);
                const cy = topY(t.id);
                const g = mk('g', { 'data-child': t.id, 'data-parent': h }, 'tb-tree-edge');
                g.appendChild(mk('line', { x1: px, y1: py, x2: cx, y2: cy }, 'tb-tree-line'));
                const rel = (t.deprel && t.deprel !== '_') ? t.deprel : '';
                if (rel) {
                    const lbl = mk('text', { x: (px + cx) / 2, y: (py + cy) / 2, 'text-anchor': 'middle' }, 'tb-tree-rel');
                    lbl.setAttribute('fill', tbRelColor(t.deprel));
                    lbl.textContent = rel;
                    g.appendChild(lbl);
                }
                svg.appendChild(g);
            });

            const rootT = mk('text', { x: xOf.get(0), y: PADY + 10, 'text-anchor': 'middle' }, 'tb-tree-root');
            rootT.textContent = 'ROOT';
            svg.appendChild(rootT);

            toks.forEach(t => {
                if (!depth.has(t.id)) return;
                const cx = xOf.get(t.id), yy = y0(t.id);
                const hasKids = (kids.get(t.id) || []).length > 0;
                const g = mk('g', { 'data-tok-id': t.id }, 'tb-tree-node' + (t.upos === 'PUNCT' ? ' tb-tree-punct' : '') + (collapsed.has(t.id) ? ' tb-tree-collapsed' : ''));
                g.appendChild(mk('rect', { x: cx - SLOT / 2 + 6, y: yy - 2, width: SLOT - 12, height: LBH + 4, rx: 4 }, 'tb-tree-hit'));
                const form = mk('text', { x: cx, y: yy + 14, 'text-anchor': 'middle' }, 'tb-tree-form'); form.textContent = t.form; g.appendChild(form);
                if (t.translit) { const tr = mk('text', { x: cx, y: yy + 29, 'text-anchor': 'middle' }, 'tb-tree-translit'); tr.textContent = clip(t.translit, 16); g.appendChild(tr); }
                if (t.gloss) { const gl = mk('text', { x: cx, y: yy + 43, 'text-anchor': 'middle' }, 'tb-tree-gloss'); gl.textContent = clip(t.gloss, 16); g.appendChild(gl); }
                const ttl = mk('title', {}); ttl.textContent = t.form + (t.translit ? '  [' + t.translit + ']' : '') + (t.gloss ? '  - ' + t.gloss : '') + (t.deprel ? '  (' + t.deprel + ')' : ''); g.appendChild(ttl);

                if (hasKids) {
                    const my = yy + LBH + 1;
                    if (collapsed.has(t.id)) {
                        g.appendChild(mk('path', { d: 'M ' + (cx - 3) + ' ' + (my - 4) + ' L ' + (cx - 3) + ' ' + (my + 4) + ' L ' + (cx + 3) + ' ' + my + ' Z' }, 'tb-tree-caret'));
                        const cnt = mk('text', { x: cx + 8, y: my + 3, 'text-anchor': 'start' }, 'tb-tree-count'); cnt.textContent = '+' + descCount.get(t.id); g.appendChild(cnt);
                    } else {
                        g.appendChild(mk('path', { d: 'M ' + (cx - 4) + ' ' + (my - 3) + ' L ' + (cx + 4) + ' ' + (my - 3) + ' L ' + cx + ' ' + (my + 3) + ' Z' }, 'tb-tree-caret'));
                    }
                }

                const clearHi = () => {
                    svg.querySelectorAll('.tb-tree-node').forEach(n => n.classList.remove('tb-active', 'tb-is-head', 'tb-is-dep'));
                    svg.querySelectorAll('.tb-tree-edge').forEach(e => e.classList.remove('tb-edge-head', 'tb-edge-dep'));
                };
                g.addEventListener('mouseenter', () => {
                    clearHi();
                    g.classList.add('tb-active');
                    const h = headOf(t);
                    if (h !== 0) { const hn = svg.querySelector('.tb-tree-node[data-tok-id="' + h + '"]'); if (hn) hn.classList.add('tb-is-head'); }
                    const he = svg.querySelector('.tb-tree-edge[data-child="' + t.id + '"]'); if (he) he.classList.add('tb-edge-head');
                    (kids.get(t.id) || []).forEach(c => {
                        const dn = svg.querySelector('.tb-tree-node[data-tok-id="' + c + '"]'); if (dn) dn.classList.add('tb-is-dep');
                        const de = svg.querySelector('.tb-tree-edge[data-child="' + c + '"]'); if (de) de.classList.add('tb-edge-dep');
                    });
                });
                g.addEventListener('mouseleave', clearHi);
                g.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (hasKids) {
                        if (collapsed.has(t.id)) collapsed.delete(t.id); else collapsed.add(t.id);
                        draw();
                    } else {
                        const ht = headOf(t) ? byId.get(headOf(t)) : null;
                        const dps = (kids.get(t.id) || []).map(id => byId.get(id)).filter(d => d && d.upos !== 'PUNCT');
                        const panel = block.querySelector('.tb-detail-panel');
                        if (panel) { panel.innerHTML = renderTokenDetail(t, ht, dps); panel.classList.add('tb-detail-visible'); _tbApplyTranslitToPanel(panel); }
                    }
                });
                svg.appendChild(g);
            });
            wrap.appendChild(svg);
        };
        draw();
    }

    // ── Per-word annotation grid (Tree mode) ──
    // One column per word; rows are the annotations (form, translit, lemma, relation, pos, morph, gloss).
    // Which rows show is controlled by the grid toggles in the control bar. Clicking a column opens detail.
    function tbRenderGrid(block, sent) {
        const toks = (sent.tokens || []);
        if (!toks.length) return;
        const byId = new Map(); toks.forEach(t => byId.set(t.id, t));

        // detect RTL script (Arabic/Hebrew ranges) from the word forms
        const isRTL = toks.some(t => {
            const f = t.form || '';
            for (let i = 0; i < f.length; i++) {
                const c = f.charCodeAt(i);
                if ((c >= 0x0590 && c <= 0x05FF) || (c >= 0x0600 && c <= 0x06FF) || (c >= 0x0750 && c <= 0x077F) ||
                    (c >= 0x08A0 && c <= 0x08FF) || (c >= 0xFB1D && c <= 0xFDFF) || (c >= 0xFE70 && c <= 0xFEFF)) return true;
            }
            return false;
        });

        const state = window.__tbGridRows || {};
        const rows = [
            { key: 'form',     label: 'word',     val: t => t.form,                                          cls: 'tb-gc-form' },
            { key: 'translit', label: 'translit', val: t => t.translit || '',                                cls: 'tb-gc-translit' },
            { key: 'lemma',    label: 'lemma',    val: t => (t.lemma && t.lemma !== '_') ? t.lemma : '',     cls: 'tb-gc-lemma' },
            { key: 'relation', label: 'relation', chip: 'rel',                                               cls: 'tb-gc-relation' },
            { key: 'pos',      label: 'pos',      chip: 'pos',                                               cls: 'tb-gc-pos' },
            { key: 'morph',    label: 'morph',    val: t => (t.feats && t.feats !== '_') ? t.feats : '',     cls: 'tb-gc-morph' },
            { key: 'gloss',    label: 'gloss',    val: t => t.gloss || '',                                   cls: 'tb-gc-gloss' },
        ];

        const scroll = document.createElement('div');
        scroll.className = 'tb-grid-scroll';
        if (isRTL) scroll.style.direction = 'rtl';
        const grid = document.createElement('div');
        grid.className = 'tb-grid';
        rows.forEach(r => { if (r.key !== 'form' && state[r.key] === false) grid.classList.add('tb-ghide-' + r.key); });

        const openDetail = (t) => {
            const ht = (t.head > 0) ? byId.get(t.head) : null;
            const dps = toks.filter(d => d.head === t.id && d.upos !== 'PUNCT');
            grid.querySelectorAll('.tb-gcell.tb-gcol-active').forEach(c => c.classList.remove('tb-gcol-active'));
            grid.querySelectorAll('.tb-gcell[data-tok-id="' + t.id + '"]').forEach(c => c.classList.add('tb-gcol-active'));
            const panel = block.querySelector('.tb-detail-panel');
            if (panel) { panel.innerHTML = renderTokenDetail(t, ht, dps); panel.classList.add('tb-detail-visible'); _tbApplyTranslitToPanel(panel); }
        };

        rows.forEach(r => {
            const rowEl = document.createElement('div');
            rowEl.className = 'tb-grow ' + r.cls;
            const lab = document.createElement('div');
            lab.className = 'tb-glabel';
            lab.textContent = r.label;
            rowEl.appendChild(lab);
            toks.forEach(t => {
                const cell = document.createElement('div');
                cell.className = 'tb-gcell' + (t.upos === 'PUNCT' ? ' tb-gcell-punct' : '');
                cell.dataset.tokId = t.id;
                if (r.chip === 'rel') {
                    if (t.deprel && t.deprel !== '_') {
                        const chip = document.createElement('span');
                        chip.className = 'tb-rel-chip';
                        chip.style.background = tbRelColor(t.deprel);
                        chip.textContent = t.deprel;
                        cell.appendChild(chip);
                    }
                } else if (r.chip === 'pos') {
                    if (t.upos && t.upos !== '_') {
                        const chip = document.createElement('span');
                        chip.className = 'tb-pos-chip';
                        const pc = tbPosColor(t.upos);
                        chip.style.color = pc; chip.style.borderColor = pc + '66';
                        chip.textContent = t.upos;
                        cell.appendChild(chip);
                        if (t.xpos && t.xpos !== '_' && t.xpos !== t.upos) {
                            const x = document.createElement('span'); x.className = 'tb-xpos'; x.textContent = ' ' + t.xpos; cell.appendChild(x);
                        }
                    }
                } else {
                    const v = r.val(t);
                    cell.textContent = v;
                    if (v) cell.title = v;
                }
                cell.addEventListener('click', (e) => { e.stopPropagation(); openDetail(t); });
                rowEl.appendChild(cell);
            });
            grid.appendChild(rowEl);
        });
        scroll.appendChild(grid);
        block.appendChild(scroll);
    }

    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    const TB_REL_COLORS = {
        root:'#660000',nsubj:'#1a5276','nsubj:pass':'#1a5276',obj:'#1d6a3e',iobj:'#145a32',
        obl:'#784212','obl:agent':'#784212',vocative:'#6c3483',expl:'#935116',advcl:'#0e6655',
        advmod:'#555577',aux:'#7b241c','aux:pass':'#7b241c',cop:'#6e2f1a',mark:'#5b2c6f',
        nmod:'#1f618d',appos:'#117a65',nummod:'#b7950b',acl:'#1a5276','acl:relcl':'#154360',
        amod:'#2471a3',det:'#d4ac0d',case:'#7d6608',conj:'#1e8449',cc:'#2874a6',
        fixed:'#922b21',flat:'#1a5276',compound:'#0e6655',parataxis:'#78281f',
        orphan:'#5d6d7e',punct:'#bbb',dep:'#555',ccomp:'#0e6655',xcomp:'#117a65',
        csubj:'#6c3483',discourse:'#4a235a',
        PRED:'#660000',SB:'#1a5276',OBJ:'#1d6a3e',ATR:'#2471a3',ADV:'#0e6655',
        AuxP:'#7b241c',AuxC:'#5b2c6f',AuxX:'#bbb',AuxV:'#7b241c',
        Coord:'#1e8449',ExD:'#935116',Apos:'#117a65',Pars:'#6c3483',
    };
    function tbRelColor(rel) {
        if (!rel || rel === '_') return '#888';
        return TB_REL_COLORS[rel] || TB_REL_COLORS[rel.split(':')[0]] || '#555';
    }
    const TB_POS_COLORS = {
        NOUN:'#1d4e8a',VERB:'#7b1c1c',ADJ:'#276b27',ADV:'#7b5c00',PRON:'#4a2a6e',
        DET:'#a65c00',ADP:'#555',AUX:'#8b2500',CCONJ:'#2e7d32',SCONJ:'#2e7d32',
        PUNCT:'#bbb',NUM:'#006666',PROPN:'#1d4e8a',PART:'#666',INTJ:'#880044',X:'#888',
    };
    function tbPosColor(pos) { return TB_POS_COLORS[pos] || '#444'; }

    function renderActiveContentLayers(payload) {
        ['f', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'].forEach(prefix => {
            const targetContainer = document.getElementById(`content_${prefix}`);
            if (!targetContainer) return;
            targetContainer.innerHTML = "";
            
            const vId = columnEditions[prefix];
            const activeEditionMeta = TEXT_REGISTRY[vId];
            const cssClass = activeEditionMeta ? activeEditionMeta.class : "english-text";
            const shortId = activeEditionMeta ? activeEditionMeta.short_id : vId;
            const isPoetry = isPoetryWork(activeWorkKey);

            if (activeEditionMeta && activeEditionMeta.doc_type === 'treebank') {
                renderTreebankColumn(targetContainer, activeEditionMeta, payload);
                return;
            }
            if (activeEditionMeta && activeEditionMeta.doc_type === 'metrical') {
                renderMetricalColumn(targetContainer, activeEditionMeta, payload);
                return;
            }
            
            // Get alignment groups for this version + work (if an alignment pair is active)
            const alnPairs   = GLOBAL_ALIGNMENTS[activeWorkKey] || {};
            const alnPair    = activePairId ? alnPairs[activePairId] : null;
            const isAlnSrc   = alnPair && (shortId === alnPair.src_version);
            const isAlnTgt   = alnPair && (shortId === alnPair.tgt_version);
            const hasAln     = isAlnSrc || isAlnTgt;

            naturalSectionKeys(payload.sections).forEach(sec => {
                const isHidden = activeSectionFilter !== null && activeSectionFilter !== sec;
                const row = document.createElement("div");
                row.className = `section-row s-idx-${sec} ${isHidden ? 'hidden-section' : ''}`;
                let txt = payload.sections[sec][shortId] || "<i>[Text range missing in alignment layer]</i>";
                const visualIndexLabel = isPoetry ? sec : `[${sec}]`;

                // Apply token alignment wrapping for source/target columns
                if (hasAln && !isPoetry && alnPair) {
                    // Segment key in GLOBAL_ALIGNMENTS is "ch.sec" (matches ch_id.sec pattern)
                    // payload.chapter is the chapter; sec is the section
                    const segKey = `${payload.chapter}.${sec}`;
                    const groups = (alnPair.segments || {})[segKey] || [];
                    if (groups.length > 0) {
                        txt = renderAlignedProse(txt, shortId, groups, alnPair, segKey);
                    }
                }

            if (isPoetry) {
                const wrapper = document.createElement("div");
                wrapper.className = `${cssClass} poetry-grid-layout`;
                wrapper.innerHTML = txt;
                if (!wrapper.querySelector('.line-num-cell')) {
                    wrapper.classList.remove('poetry-grid-layout');
                }
                row.appendChild(wrapper);
            } else {
                    row.innerHTML = `
                        <div class="prose-inline-layout ${cssClass}">
                            <span class="prose-marker"><a href="javascript:void(0)" onclick="selectSectionDirectly('${sec}')">${visualIndexLabel}</a></span>
                            <div class="prose-body-inline">${txt}</div>
                        </div>
                    `;
                }
                targetContainer.appendChild(row);
            });

            const footer = document.createElement("div");
            footer.className = "viewport-footer-controls";
            let prevBtnHtml = "", nextBtnHtml = "";
            if (payload.navigation.prev) {
                const prevParts = payload.navigation.prev.split(":");
                const prevPsg = prevParts[prevParts.length - 1].split(".");
                const label = isPoetry ? "Chapter" : (isFlatStructure(activeWorkKey) ? `Ch ${prevPsg[0]}` : `Bk ${prevPsg[0]} Ch ${prevPsg[1]}`);
                prevBtnHtml = `<a class="action-btn" onclick="navigateAdjacentUrn('${payload.navigation.prev}')">&larr; Previous (${label})</a>`;
            }
            if (payload.navigation.next) {
                const nextParts = payload.navigation.next.split(":");
                const nextPsg = nextParts[nextParts.length - 1].split(".");
                const label = isPoetry ? "Chapter" : (isFlatStructure(activeWorkKey) ? `Ch ${nextPsg[0]}` : `Bk ${nextPsg[0]} Ch ${nextPsg[1]}`);
                nextBtnHtml = `<a class="action-btn" onclick="navigateAdjacentUrn('${payload.navigation.next}')">Next (${label}) &rarr;</a>`;
            }
            
            footer.innerHTML = `
                <div class="footer-group-left">
                    ${prevBtnHtml}
                    <a href="javascript:void(0)" class="action-btn secondary" onclick="clearSectionFilter(event)">Full View</a>
                </div>
                ${nextBtnHtml}
            `;
            targetContainer.appendChild(footer);

            // Greek transliteration: gate on whether this column's *rendered
            // content* actually contains Greek right now, not on the edition's
            // declared class. A translation column with Greek in its footnotes,
            // or a commentary column that's mostly English discussion around
            // quoted Greek, both qualify — only the Greek runs get converted,
            // everything else in the column passes through untouched.
            const containerHtml = targetContainer.innerHTML;
            const isGreekColumn = GREEK_HAS_REGEX.test(containerHtml);
            setTranslitControlVisible(prefix, isGreekColumn);
            if (isGreekColumn) {
                columnGreekOriginalHtml[prefix] = containerHtml;
                const savedMode = document.getElementById(`translit_${prefix}`);
                if (savedMode) savedMode.value = columnTranslitMode[prefix] || '';
                applyGreekTransliteration(prefix);
            } else {
                delete columnGreekOriginalHtml[prefix];
            }
        });
    }

    function setTranslitControlVisible(prefix, visible) {
        const el = document.getElementById(`translit_${prefix}`);
        if (el) el.style.display = visible ? '' : 'none';
    }

    window.navigateAdjacentUrn = function(urn) {
        activeSectionFilter = null;
        const parts = urn.split(":");
        const psg = parts[parts.length - 1].split(".");
        if (isFlatStructure(activeWorkKey)) {
            triggerTargetNavigation(null, psg[0]);
        } else {
            triggerTargetNavigation(psg[0], psg[1]);
        }
    };

    window.clearSectionFilter = function(e) {
        if(e) e.preventDefault();
        activeSectionFilter = null;
        triggerViewRefresh();
    };

    window.updateColumnContent = function(prefix, value) {
        columnEditions[prefix] = value;
        triggerViewRefresh();
        // Refresh alignment legend: it may now warn about missing/present columns
        updateAlignmentLegend();
    };

    window.setWorkspaceLayoutMode = function(mode) {
        currentActiveMode = mode;
        const frame = document.getElementById("outer-wrapper");
        const btnParallel = document.getElementById("btn-mode-parallel");
        const btnClassic = document.getElementById("btn-mode-classic");
        
        if (mode === 'classic') {
            frame.className = "mode-classic";
            if (activeColumnsCount === 4) frame.classList.add('four-columns');
            if (activeColumnsCount === 5) frame.classList.add('five-columns');
            if (activeColumnsCount === 6) frame.classList.add('six-columns');
            if (activeColumnsCount === 7) frame.classList.add('seven-columns');
            btnClassic.classList.add("active-mode"); btnParallel.classList.remove("active-mode");
        } else {
            frame.className = "mode-parallel";
            if (activeColumnsCount === 4) frame.classList.add('four-columns');
            if (activeColumnsCount === 5) frame.classList.add('five-columns');
            if (activeColumnsCount === 6) frame.classList.add('six-columns');
            if (activeColumnsCount === 7) frame.classList.add('seven-columns');
            btnParallel.classList.add("active-mode"); btnClassic.classList.remove("active-mode");
        }
        
        updateClassicGridForColumns();
        triggerViewRefresh();
    };
  
    window.cycleColumns = function() {
        if (activeColumnsCount === 3) activeColumnsCount = 4;
        else if (activeColumnsCount === 4) activeColumnsCount = 5;
        else if (activeColumnsCount === 5) activeColumnsCount = 6;
        else if (activeColumnsCount === 6) activeColumnsCount = 7;
        else activeColumnsCount = 3;

        const btn = document.getElementById('btn-column-scaler');
        const ow = document.getElementById('outer-wrapper');
        
        ow.classList.remove('four-columns', 'five-columns', 'six-columns', 'seven-columns');
        btn.innerText = `Columns: ${activeColumnsCount}`;
        
        if (activeColumnsCount === 4) ow.classList.add('four-columns');
        if (activeColumnsCount === 5) ow.classList.add('five-columns');
        if (activeColumnsCount === 6) ow.classList.add('six-columns');
        if (activeColumnsCount === 7) ow.classList.add('seven-columns');
        
        updateClassicGridForColumns();
        triggerViewRefresh();
    };

    function updateClassicGridForColumns() {
        const ow = document.getElementById('outer-wrapper');
        const colF = document.getElementById('col_f');
        if (!ow || !colF || !ow.classList.contains('mode-classic')) return;
        
        if (activeColumnsCount === 7) {
            colF.style.gridRow = '1 / span 6';
        } else if (activeColumnsCount === 6) {
            colF.style.gridRow = '1 / span 5';
        } else if (activeColumnsCount === 5) {
            colF.style.gridRow = '1 / span 4';
        } else if (activeColumnsCount === 4) {
            colF.style.gridRow = '1 / span 3';
        } else {
            colF.style.gridRow = '1 / span 2';
        }
    }
    
    window.swapToFocus = function(sourcePrefix) {
        const focusEdition = columnEditions['f'];
        const sourceEdition = columnEditions[sourcePrefix];
        
        columnEditions['f'] = sourceEdition;
        columnEditions[sourcePrefix] = focusEdition;
        
        document.getElementById('select_f').value = sourceEdition;
        document.getElementById('select_' + sourcePrefix).value = focusEdition;
        updateAlignmentLegend();
        
        triggerViewRefresh();
    };

    (function() {
        function initResizeHandles() {
            document.querySelectorAll('.resize-handle').forEach(h => {
                h.addEventListener('mousedown', startResize);
                h.addEventListener('touchstart', startResize, {passive: false});
            });
        }

        function startResize(e) {
            e.preventDefault();
            const handle = e.currentTarget;
            const isHorizontal = handle.classList.contains('resize-handle-h');
            const container = document.getElementById('main-container');
            const isClassic = document.getElementById('outer-wrapper').classList.contains('mode-classic');

            handle.classList.add('dragging');
            document.body.classList.add(isHorizontal ? 'resizing-cols' : 'resizing-rows');

            if (isClassic) {
                handleClassicResize(e, handle, container);
            } else {
                handleParallelResize(e, handle, container);
            }
        }

        function handleParallelResize(startEvent, handle, container) {
            const columns = Array.from(container.querySelectorAll('.reading-column'));
            const handleIndex = Array.from(container.children).indexOf(handle);
            const prevCol = container.children[handleIndex - 1];
            const nextCol = container.children[handleIndex + 1];
            if (!prevCol || !nextCol) return;

            const startX = (startEvent.touches ? startEvent.touches[0] : startEvent).clientX;
            const prevStart = prevCol.getBoundingClientRect().width;
            const nextStart = nextCol.getBoundingClientRect().width;

            columns.forEach(col => { col.style.flex = 'none'; col.style.width = col.getBoundingClientRect().width + 'px'; });

            function onMove(e) {
                const clientX = (e.touches ? e.touches[0] : e).clientX;
                const dx = clientX - startX;
                prevCol.style.width = Math.max(100, prevStart + dx) + 'px';
                nextCol.style.width = Math.max(100, nextStart - dx) + 'px';
            }
            function onEnd() {
                handle.classList.remove('dragging'); document.body.classList.remove('resizing-cols', 'resizing-rows');
                document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onEnd);
            }
            document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onEnd);
        }

        function handleClassicResize(startEvent, handle, container) {
            const startX = (startEvent.touches ? startEvent.touches[0] : startEvent).clientX;
            const startY = (startEvent.touches ? startEvent.touches[0] : startEvent).clientY;
            const style = getComputedStyle(container);
            const colWidths = style.gridTemplateColumns.split(' ').map(parseFloat);
            const rowHeights = style.gridTemplateRows.split(' ').map(parseFloat);

            function onMove(e) {
                const clientX = (e.touches ? e.touches[0] : e).clientX;
                const clientY = (e.touches ? e.touches[0] : e).clientY;

                if (handle.id === 'resize-f-c1') {
                    const dx = clientX - startX; const totalW = colWidths[0] + colWidths[1];
                    const newLeft = Math.max(150, Math.min(totalW - 150, colWidths[0] + dx));
                    container.style.gridTemplateColumns = newLeft + 'px ' + (totalW - newLeft) + 'px';
                    positionClassicHandles();
                } else if (handle.id === 'resize-c1-c2') {
                    const dy = clientY - startY; const totalH = rowHeights[0] + rowHeights[1];
                    const newTop = Math.max(80, Math.min(totalH - 80, rowHeights[0] + dy));
                    container.style.gridTemplateRows = newTop + 'px ' + (totalH - newTop) + 'px';
                    positionClassicHandles();
                }
            }
            function onEnd() {
                handle.classList.remove('dragging'); document.body.classList.remove('resizing-cols', 'resizing-rows');
                document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onEnd);
            }
            document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onEnd);
        }

        function createClassicOverlayHandles() {
            const mc = document.getElementById('main-container');
            if (!mc) return;

            let vHandle = document.getElementById('classic-resize-col');
            if (!vHandle) {
                vHandle = document.createElement('div'); vHandle.id = 'classic-resize-col';
                vHandle.className = 'resize-handle resize-handle-h'; vHandle.style.cssText = 'position:absolute; top:0; bottom:0; z-index:25;';
                mc.style.position = 'relative'; mc.appendChild(vHandle);
                vHandle.addEventListener('mousedown', classicColResize);
            }
            let hHandle = document.getElementById('classic-resize-row');
            if (!hHandle) {
                hHandle = document.createElement('div'); hHandle.id = 'classic-resize-row';
                hHandle.className = 'resize-handle resize-handle-v'; hHandle.style.cssText = 'position:absolute; left:0; right:0; z-index:25;';
                mc.appendChild(hHandle); hHandle.addEventListener('mousedown', classicRowResize);
            }
            positionClassicHandles();
        }

        function positionClassicHandles() {
            const mc = document.getElementById('main-container');
            const colF = document.getElementById('col_f'); const colC1 = document.getElementById('col_c1');
            if (!mc || !colF || !colC1 || !document.getElementById('outer-wrapper')?.classList.contains('mode-classic')) return;

            const mcRect = mc.getBoundingClientRect(); const fRect = colF.getBoundingClientRect(); const c1Rect = colC1.getBoundingClientRect();
            if (document.getElementById('classic-resize-col')) document.getElementById('classic-resize-col').style.left = (fRect.right - mcRect.left - 2) + 'px';
            if (document.getElementById('classic-resize-row')) {
                document.getElementById('classic-resize-row').style.top = (c1Rect.bottom - mcRect.top - 2) + 'px';
                document.getElementById('classic-resize-row').style.left = (fRect.right - mcRect.left + 3) + 'px';
                document.getElementById('classic-resize-row').style.right = '0';
            }
        }

        function classicColResize(startEvent) {
            startEvent.preventDefault();
            const mc = document.getElementById('main-container'); const handle = document.getElementById('classic-resize-col');
            handle.classList.add('dragging'); document.body.classList.add('resizing-cols');
            const colWidths = getComputedStyle(mc).gridTemplateColumns.split(' ').map(parseFloat);
            const startX = startEvent.clientX;

            function onMove(e) {
                const dx = e.clientX - startX; const totalW = colWidths[0] + colWidths[1];
                const newLeft = Math.max(150, Math.min(totalW - 150, colWidths[0] + dx));
                mc.style.gridTemplateColumns = newLeft + 'px ' + (totalW - newLeft) + 'px';
                positionClassicHandles();
            }
            function onEnd() {
                handle.classList.remove('dragging'); document.body.classList.remove('resizing-cols');
                document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onEnd);
            }
            document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onEnd);
        }

        function classicRowResize(startEvent) {
            startEvent.preventDefault();
            const mc = document.getElementById('main-container'); const handle = document.getElementById('classic-resize-row');
            handle.classList.add('dragging'); document.body.classList.add('resizing-rows');
            const rowHeights = getComputedStyle(mc).gridTemplateRows.split(' ').map(parseFloat);
            const startY = startEvent.clientY;

            function onMove(e) {
                const dy = e.clientY - startY; const totalH = rowHeights[0] + rowHeights[1];
                const newTop = Math.max(80, Math.min(totalH - 80, rowHeights[0] + dy));
                mc.style.gridTemplateRows = newTop + 'px ' + (totalH - newTop) + 'px';
                positionClassicHandles();
            }
            function onEnd() {
                handle.classList.remove('dragging'); document.body.classList.remove('resizing-rows');
                document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onEnd);
            }
            document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onEnd);
        }

        const modeObserver = new MutationObserver(function() {
            const isClassic = document.getElementById('outer-wrapper')?.classList.contains('mode-classic');
            const h1 = document.getElementById('resize-f-c1'); const h2 = document.getElementById('resize-c1-c2'); 
            const h3 = document.getElementById('resize-c2-c3'); const h4 = document.getElementById('resize-c3-c4');
            const h5 = document.getElementById('resize-c4-c5'); const h6 = document.getElementById('resize-c5-c6');
            const ch = document.getElementById('classic-resize-col'); const rh = document.getElementById('classic-resize-row');
            
            if (isClassic) {
                if (h1) h1.style.display = 'none'; if (h2) h2.style.display = 'none'; if (h3) h3.style.display = 'none'; if (h4) h4.style.display = 'none';
                if (h5) h5.style.display = 'none'; if (h6) h6.style.display = 'none';
                createClassicOverlayHandles();
                if (ch) ch.style.display = ''; 
                
                if (activeColumnsCount === 3) {
                    if (rh) rh.style.display = '';
                } else {
                    if (rh) rh.style.display = 'none';
                    const mc = document.getElementById('main-container');
                    if (mc) {
                        const currentStyle = mc.style.gridTemplateColumns;
                        mc.style.gridTemplateRows = ''; 
                        if (currentStyle) {
                            mc.style.gridTemplateColumns = currentStyle;
                        }
                    }
                }
                setTimeout(positionClassicHandles, 50);
            } else {
                if (h1) h1.style.display = ''; if (h2) h2.style.display = ''; 
                if (h3) h3.style.display = activeColumnsCount >= 4 ? '' : 'none';
                if (h4) h4.style.display = activeColumnsCount >= 5 ? '' : 'none';
                if (h5) h5.style.display = activeColumnsCount >= 6 ? '' : 'none';
                if (h6) h6.style.display = activeColumnsCount === 7 ? '' : 'none';
                if (ch) ch.style.display = 'none'; if (rh) rh.style.display = 'none';
            }
        });
        
        document.addEventListener('DOMContentLoaded', function() {
            initResizeHandles();
            const ow = document.getElementById('outer-wrapper');
            if (ow) modeObserver.observe(ow, { attributes: true, attributeFilter: ['class'] });
            window.addEventListener('resize', positionClassicHandles);
        });
    })();

    const dz = document.getElementById('drop-zone');
    if(dz) {
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor = '#660000'; dz.style.background = '#fdfbef'; });
        dz.addEventListener('dragleave', () => { dz.style.borderColor = '#ccc'; dz.style.background = '#fafafa'; });
        dz.addEventListener('drop', e => { e.preventDefault(); dz.style.borderColor = '#ccc'; dz.style.background = '#fafafa'; handleFileSelection(e.dataTransfer.files); });
    }
  