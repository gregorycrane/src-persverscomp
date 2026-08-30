
    // Explicitly anchor framework mechanics to top-level global window references
    window.SQL_WASM_ENGINE = null;
    window.dbInstance = null;

    const GLOBAL_STRUCTURES = STRUCT_REPLACE;
    const TEXT_REGISTRY    = REGISTRY_REPLACE;
    // ── Treebank search-app link config ─────────────────────────────────
    // Path from this reader (repo root) to the sibling treebank search app,
    // used by the Gloss/Lemma links in the annotation detail panel below.
    // Adjust if the search app is deployed somewhere other than ./search/.
    const SEARCH_APP_URL = './search/index.html';
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

    // Cache of column-existence checks per table, since PRAGMA table_info is
    // static for a given shard/session and this can get called once per
    // treebank hydration. Needed because a corpus can legitimately be in a
    // mixed state during a staged rebuild -- some works' shards carry the
    // newer `book` column on treebank_sentences, others (not yet rebuilt)
    // don't -- and a query that unconditionally selects a column absent from
    // an older shard throws, which _dbRows swallows into a silent [], making
    // that work's treebank vanish entirely rather than just losing the
    // book-qualified lookup it would have enabled.
    const _COLUMN_CACHE = new Map();
    function _hasColumn(table, col) {
        const key = `${table}.${col}`;
        if (_COLUMN_CACHE.has(key)) return _COLUMN_CACHE.get(key);
        let has = false;
        try {
            const db = window.dbInstance;
            if (db) {
                const res = db.exec(`PRAGMA table_info(${table})`);
                if (res.length) has = res[0].values.some(r => r[1] === col);
            }
        } catch (e) { /* leave false */ }
        _COLUMN_CACHE.set(key, has);
        return has;
    }

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
        // Older, not-yet-rebuilt shards may not have the `book` column yet
        // (added alongside the Propertius work -- see comment below); only
        // request it when it actually exists, so this degrades gracefully
        // to the pre-`book` behavior instead of finding zero rows.
        const hasBookCol = _hasColumn('treebank_sentences', 'book');
        const rows = _dbRows(
            `SELECT subdoc, section, chapter, ${hasBookCol ? 'book,' : ''} sentence_json, prose_translation, literal_translation, transliteration, credits_json ` +
            "FROM treebank_sentences WHERE textgroup=? AND work=? AND version_short_id=? ORDER BY id",
            [tg, work, vid]);
        let out = null;
        if (rows.length) {
            out = {};
            rows.forEach(r => {
                // Group under the book-qualified key ("1.1") whenever a real
                // `book` value is present, in addition to the bare chapter
                // key ("1"). renderTreebankColumn() already looks up
                // `${payload.book}.${chapter}` first and falls back to bare
                // `chapter` -- that compound lookup previously only ever hit
                // for prose works, where book.chapter is folded straight
                // into the `chapter` column itself. Poetry/card-based works
                // (Propertius, and any existing multi-book milestone-carded
                // work -- Homer, Vergil, etc.) store `chapter` bare, so
                // without this, sentences from every book sharing the same
                // card number (book 1 poem 1, book 2 poem 1, ...) all landed
                // under one bare key and got shown together regardless of
                // which book was actually open. `book` (added alongside
                // `chapter`/`section` in the treebank schema) is what makes
                // the compound key constructible here at all.
                const sentObj = {
                    subdoc: r.subdoc, section: r.section,
                    tokens: _jp(r.sentence_json, []),
                    prose: r.prose_translation, literal: r.literal_translation,
                    translit: r.transliteration,
                    credits: _jp(r.credits_json, null)
                };
                (out[r.chapter] = out[r.chapter] || []).push(sentObj);
                if (r.book) {
                    const bkKey = `${r.book}.${r.chapter}`;
                    (out[bkKey] = out[bkKey] || []).push(sentObj);
                }
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

// ── Author-level lexica (Cunliffe, Dindorf, ...) ───────────────────────────
// Separate from the work-shard cache above: lexica are keyed by shard FILE
// (a shard can bundle several lexicon_ids, e.g. Cunliffe words + names),
// not by work, and are loaded lazily on first token click rather than
// eagerly with the work.
let LEXICA_CATALOG = null;
const LEXICON_SHARD_CACHE = new Map();    // shardFile -> sql.js Database
const LEXICON_SHARD_INFLIGHT = new Map(); // shardFile -> Promise

// Top-level copy of escHtml -- the lexicon functions below live at module
// scope, but the existing escHtml() is nested inside renderTreebankColumn()
// and isn't reachable from here. Same implementation, kept in sync.
function escHtmlTopLevel(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function loadLexicaCatalog() {
    if (LEXICA_CATALOG) return LEXICA_CATALOG;
    try {
        const r = await fetch(`./site/lexica.json?v=${Date.now()}`, { cache: "no-store" });
        if (!r.ok) throw new Error("lexica.json not found");
        LEXICA_CATALOG = await r.json();
    } catch (e) {
        console.warn("[lexica] no lexica.json (no lexica configured for this build):", e.message);
        LEXICA_CATALOG = { lexica: {}, textgroups: {} };
    }
    return LEXICA_CATALOG;
}

// Which lexicon_ids apply to a textgroup, each with its shard file + display meta.
async function lexiconsForTextgroup(textgroup) {
    const catalog = await loadLexicaCatalog();
    const ids = catalog.textgroups[textgroup] || [];
    return ids.map(id => ({ lexicon_id: id, ...catalog.lexica[id] }));
}

async function getLexiconShard(shardFile) {
    if (LEXICON_SHARD_CACHE.has(shardFile)) return LEXICON_SHARD_CACHE.get(shardFile);
    if (LEXICON_SHARD_INFLIGHT.has(shardFile)) return LEXICON_SHARD_INFLIGHT.get(shardFile);

    const p = (async () => {
        const resp = await fetch(`./site/data/lexica/${shardFile}`);
        if (!resp.ok) throw new Error(`Lexicon shard not found: ${shardFile}`);
        const buf = new Uint8Array(await resp.arrayBuffer());
        const db = new window.SQL_WASM_ENGINE.Database(buf);
        LEXICON_SHARD_CACHE.set(shardFile, db);
        LEXICON_SHARD_INFLIGHT.delete(shardFile);
        return db;
    })();
    LEXICON_SHARD_INFLIGHT.set(shardFile, p);
    return p;
}

// Same accent/case-folding logic as the notebook's norm_key() (Cell 1b/1c) --
// MUST be kept in sync so a token's lemma and a lexicon's headword_key are
// directly comparable. Strips Greek polytonic diacritics (combining marks),
// folds final sigma, lowercases.
function normalizeHeadwordKey(s) {
    if (!s) return null;
    let t = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    t = t.normalize('NFC').toLowerCase();
    t = t.replace(/\u03c2/g, '\u03c3'); // final sigma -> medial sigma
    return t;
}

// Looks up one lexicon's entries for a normalized headword key, resolving
// through lexicon_aliases first (covers "see X" pointer entries) so a hit
// on an alias returns the fuller target entry instead of a stub.
function lookupLexiconEntries(db, lexiconId, headwordKey) {
    if (!headwordKey) return [];
    const direct = queryAll(db,
        "SELECT entry_id, headword_display, headword_translit, entry_html FROM lexicon_entries " +
        "WHERE lexicon_id=? AND headword_key=?", [lexiconId, headwordKey]);
    if (direct.length) return direct;
    const aliasHit = queryAll(db,
        "SELECT entry_id FROM lexicon_aliases WHERE lexicon_id=? AND alias_key=?",
        [lexiconId, headwordKey]);
    if (aliasHit.length) {
        const ids = aliasHit.map(r => r.entry_id);
        const placeholders = ids.map(() => "?").join(",");
        return queryAll(db,
            `SELECT entry_id, headword_display, headword_translit, entry_html FROM lexicon_entries ` +
            `WHERE lexicon_id=? AND entry_id IN (${placeholders})`, [lexiconId, ...ids]);
    }
    return [];
}

function lookupLexiconEntryById(db, lexiconId, entryId) {
    const rows = queryAll(db,
        "SELECT entry_id, headword_display, headword_translit, entry_html FROM lexicon_entries " +
        "WHERE lexicon_id=? AND entry_id=?", [lexiconId, entryId]);
    return rows[0] || null;
}

// Logeion short-definition complement for inline treebank glosses.
// Prefetched per-textgroup (fire-and-forget, same "lazy, first render may
// miss it, re-render fills it in" pattern already used for the Browse
// Lexica shards above) rather than making renderTreebankColumn async --
// avoids restructuring its call sites, at the cost of the very first
// render after navigating to a new work not having the complement yet.
const LOGEION_SHARDS_FOR_TEXTGROUP = new Map(); // textgroup -> [{lexicon_id, db}]

async function ensureLogeionShardsLoaded(textgroup, onLoaded) {
    if (LOGEION_SHARDS_FOR_TEXTGROUP.has(textgroup)) return;
    let logeionLexica = [];
    try {
        const lexica = await lexiconsForTextgroup(textgroup);
        logeionLexica = lexica.filter(l => l.lexicon_id && l.lexicon_id.startsWith('logeion-'));
    } catch (e) {
        console.warn('[logeion] could not resolve lexica for', textgroup, e);
    }
    const dbs = [];
    for (const lex of logeionLexica) {
        try {
            const db = await getLexiconShard(lex.shard_file);
            dbs.push({ lexicon_id: lex.lexicon_id, db });
        } catch (e) {
            console.warn('[logeion] shard fetch failed for', lex.lexicon_id, e);
        }
    }
    LOGEION_SHARDS_FOR_TEXTGROUP.set(textgroup, dbs);
    if (onLoaded) onLoaded();
}

// Synchronous lookup against whatever Logeion shard(s) are already
// cached for this textgroup -- returns null (not yet loaded, or no
// entry for this lemma) rather than throwing, since callers use this
// inline during synchronous DOM-building and can't await here.
function logeionGlossFor(tok, textgroup) {
    const dbs = LOGEION_SHARDS_FOR_TEXTGROUP.get(textgroup);
    if (!dbs || !dbs.length) return null;
    const key = normalizeHeadwordKey(tok.lemma);
    if (!key) return null;
    for (const { lexicon_id, db } of dbs) {
        const rows = lookupLexiconEntries(db, lexicon_id, key);
        if (rows.length) {
            // Logeion entries are always one flat definition string with
            // no nested markup -- strip the wrapping div/span down to
            // plain text rather than injecting raw HTML into a gloss span.
            const text = rows[0].entry_html.replace(/<[^>]+>/g, '').trim();
            if (text) return text;
        }
    }
    return null;
}

function _tbHeadwordScriptClass(s) {
    // Arabic/Persian script range -- gets RTL + Perso-Arabic font styling
    // instead of the Greek serif used for Cunliffe/Dindorf headwords.
    return /[\u0600-\u06FF]/.test(s || '') ? 'tb-lex-fa' : 'tb-greek';
}

function renderLexiconBlock(lexMeta, entryRows) {
    if (!entryRows.length) {
        return `<div class="tb-lex-empty">No entry in ${escHtmlTopLevel(lexMeta.title)}</div>`;
    }
    const body = entryRows.map(row => {
        const scriptCls = _tbHeadwordScriptClass(row.headword_display);
        const translit = row.headword_translit
            ? ` <span class="tb-lex-headword-translit">${escHtmlTopLevel(row.headword_translit)}</span>`
            : '';
        return `
        <div class="tb-lex-headword ${scriptCls}">${escHtmlTopLevel(row.headword_display)}${translit}</div>
        <div class="tb-lex-body">${row.entry_html}</div>
    `;
    }).join('<div class="tb-lex-divider"></div>');

    // Some lexica (e.g. Bétant's Lexicon Thucydideum) give definitions in
    // Latin with an added English translation alongside; most don't. Rather
    // than a permanent global toolbar toggle that's meaningless for every
    // other lexicon, show "Hide Latin" only on the entries where it applies,
    // right next to the source label it affects. The preference itself is
    // still global (see toggleLexiconLatin), so flipping it here also
    // updates any other Latin-bearing lexicon block currently on screen.
    const hasLatin = entryRows.some(row => row.entry_html && row.entry_html.includes('tb-lex-lat'));
    const latinToggle = hasLatin
        ? `<label class="tb-lex-latin-toggle-label" title="${escHtmlTopLevel(lexMeta.title)} gives definitions in Latin with an added English translation alongside">
             <input type="checkbox" class="tb-lex-latin-toggle" ${localStorage.getItem(LEXICON_LATIN_PREF_KEY) === '1' ? 'checked' : ''} onchange="toggleLexiconLatin(this.checked)">
             Hide Latin
           </label>`
        : '';

    return `
        <div class="tb-lex-entry">
            <div class="tb-lex-source">${escHtmlTopLevel(lexMeta.title)}${latinToggle}</div>
            ${body}
        </div>`;
}

// Called after the base detail panel (gloss/lemma/morph) is already shown,
// so the dictionary lookup never blocks the synchronous part of the panel.
// `slot` is an empty <div> already in the DOM; this fills it in place once
// the relevant shard(s) have loaded, tolerating a work with no configured
// lexica (slot just stays empty, nothing printed).
async function populateLexiconSlot(slot, tok, textgroup) {
    const lexica = await lexiconsForTextgroup(textgroup);
    if (!lexica.length) return;

    const key = normalizeHeadwordKey(tok.lemma && tok.lemma !== '_' ? tok.lemma : tok.form);
    if (!key) return;

    // Proper-name tokens check the names lexicon (if any) first, so a
    // homograph between a common word and a name resolves to the more
    // relevant one when both exist.
    const ordered = tok.upos === 'PROPN'
        ? [...lexica].sort((a, b) => (a.entry_kind === 'name' ? -1 : 1))
        : lexica;

    let html = '';
    for (const lex of ordered) {
        try {
            const db = await getLexiconShard(lex.shard);
            const rows = lookupLexiconEntries(db, lex.lexicon_id, key);
            if (rows.length) html += renderLexiconBlock(lex, rows);
        } catch (e) {
            console.warn(`[lexica] lookup failed for ${lex.lexicon_id}:`, e);
        }
    }
    if (html) slot.innerHTML = html;
    // If nothing at all was found across every configured lexicon, the slot
    // is left empty rather than printing an empty-state per lexicon --
    // quieter for the common case of function words with no dictionary entry.
}

// Global so it can be called from onclick="" attributes baked into
// entry_html at build time (see notebook Cell 1c's _lex_inline_html).
async function openLexiconEntry(lexiconId, entryId) {
    const catalog = await loadLexicaCatalog();
    const lexMeta = catalog.lexica[lexiconId];
    if (!lexMeta) { console.warn(`[lexica] unknown lexicon_id: ${lexiconId}`); return; }
    try {
        const db = await getLexiconShard(lexMeta.shard);
        const row = lookupLexiconEntryById(db, lexiconId, entryId);
        if (!row) { console.warn(`[lexica] entry not found: ${lexiconId}/${entryId}`); return; }
        const panel = document.querySelector('.tb-detail-panel.tb-detail-visible .tb-lex-slot')
                   || document.querySelector('.tb-detail-panel.tb-detail-visible');
        if (panel) {
            panel.innerHTML = renderLexiconBlock(lexMeta, [row]);
            panel.scrollIntoView({ block: "nearest" });
        }
    } catch (e) {
        console.warn(`[lexica] openLexiconEntry failed:`, e);
    }
}
window.openLexiconEntry = openLexiconEntry;

// ── Lexicon language display toggle (e.g. Bétant's Latin defs + added ───
// English translations) ─────────────────────────────────────────────────
// A global reader preference, not per-panel: entries render both
// <gloss xml:lang="lat"> and <gloss xml:lang="eng"> every time (tagged
// with tb-lex-lat / tb-lex-eng classes by the notebook's _lex_inline_html),
// and this just flips a body-level class that CSS uses to hide one side.
// Persisted across sessions the same way column count / layout mode would
// be if this app tracked those in storage.
const LEXICON_LATIN_PREF_KEY = 'persvers_hideLexiconLatin';

function applyLexiconLatinPref() {
    const hidden = localStorage.getItem(LEXICON_LATIN_PREF_KEY) === '1';
    document.body.classList.toggle('lexicon-hide-latin', hidden);
    document.querySelectorAll('.tb-lex-latin-toggle').forEach(cb => { cb.checked = hidden; });
}

function toggleLexiconLatin(hidden) {
    localStorage.setItem(LEXICON_LATIN_PREF_KEY, hidden ? '1' : '0');
    document.body.classList.toggle('lexicon-hide-latin', hidden);
    document.querySelectorAll('.tb-lex-latin-toggle').forEach(cb => { cb.checked = hidden; });
}
window.toggleLexiconLatin = toggleLexiconLatin;

// urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.10  ->  parts
function parseCtsUrn(urn) {
    const m = /^urn:cts:([^:]+):([^.]+)\.([^.:]+)(?:\.([^:]+))?(?::(.*))?$/.exec(urn || "");
    if (!m) return null;
    const passage = m[5] || null;
    // Passage may be a range ("1.4-1.7") rather than a single ref ("1.4").
    // startRef/endRef are equal when there's no range, so callers that want
    // a single passage can just always use startRef.
    const [startRef, endRefRaw] = passage ? passage.split('-') : [null, null];
    return { textClass: m[1], textgroup: m[2], work: m[3],
             version: m[4] || null, passage,
             startRef, endRef: endRefRaw || startRef,
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
// Places attested in a given chapter, sourced from ToposText's place-mention
// index (see the place_references ingestion cell). Unlike treebank/metrical
// data, this isn't per-edition -- a work has one place index regardless of
// which translation/edition column is showing -- so there's no version_id
// filter. `book` is optional (pass it whenever the reader has one selected,
// same as getChapterDataPayload's own "AND book=?" pattern) -- prose rows
// always have a NULL book in place_references and match on chapter alone
// regardless of what book is passed, since their chapter is already the
// self-disambiguating folded "book.chapter" string; poetry rows have a
// real book value and only match when it agrees, since bare card labels
// like "1-21" legitimately recur across different books. Returns one row
// per (mention, place) pair; the same place can legitimately appear more
// than once if it's mentioned more than once in the same chapter --
// callers that want one pin per place should de-duplicate by place_id.
function placesForChapter(db, chapter, book) {
    return queryAll(db,
        "SELECT mention_type, mention_name, place_id, place_name, lat, lon, feature_type, chapter, book " +
        "FROM place_references WHERE chapter=? AND (? IS NULL OR book IS NULL OR book=?)",
        [chapter, book || null, book || null]);
}
// All places attested anywhere in a given book. Handles both addressing
// conventions this table can contain: poetry's real `book` column
// (Iliad: book="2", chapter="1-15"), and prose's folded "book.chapter"
// string with book always NULL (Thucydides: book=NULL, chapter="2.13").
// A single work's shard only ever uses one convention, so there's no
// collision risk in checking both -- a prose row's book is always NULL
// (never equals the poetry-style numeric match), and a poetry row's
// bare card-label chapter (e.g. "1-21") never contains a "." so it can
// never spuriously match the prose-style prefix check either.
function placesForBook(db, book) {
    return queryAll(db,
        "SELECT mention_type, mention_name, place_id, place_name, lat, lon, feature_type, chapter, book " +
        "FROM place_references WHERE book=? OR chapter=? OR chapter LIKE ?",
        [book, book, `${book}.%`]);
}
// Every place attested anywhere in the work, for bookless works (e.g.
// Agamemnon) where there's no book to scope to -- the natural "show
// everything" equivalent of placesForBook for a flat-structured text.
function placesForWork(db) {
    return queryAll(db,
        "SELECT mention_type, mention_name, place_id, place_name, lat, lon, feature_type, chapter " +
        "FROM place_references");
}
// The next (book, chapter) passage after the given one, in true global
// reading order (spans book boundaries correctly). Mirrors the same
// "GROUP BY book, chapter ORDER BY MIN(sort_order)" pattern the build
// notebook itself already uses to enumerate a work's passages -- not a
// new convention invented here. Returns null at the end of the work.
function nextPassage(db, book, chapter) {
    const rows = queryAll(db,
        `WITH ordered AS (
            SELECT book, chapter, MIN(sort_order) AS so
            FROM alignment_grid
            GROUP BY book, chapter
        )
        SELECT book, chapter FROM ordered
        WHERE so > (
            SELECT MIN(sort_order) FROM alignment_grid
            WHERE chapter=? AND (book=? OR (book IS NULL AND ? IS NULL))
        )
        ORDER BY so ASC LIMIT 1`,
        [chapter, book || null, book || null]);
    return rows.length ? rows[0] : null;
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
    // Range counterpart to activeSectionFilter, set when routing from a CTS
    // URN that names a passage range (e.g. "...:1.4-1.7") rather than a
    // single passage. {start, end} are the last ref-component of each
    // endpoint (numeric line/section comparison; see sectionValueInRange).
    // Only same-chapter ranges are supported -- see initializeRoutingFromURL.
    let activeSectionRange = null;
    let currentActiveMode = "parallel";
    let activeColumnsCount = 3;
    let columnEditions = { f: "", c1: "", c2: "", c3: "", c4: "", c5: "", c6: "" };

    // Minimal default styling for TOC buttons the current Focus edition has
    // no real content at (see getChaptersWithContent / renderNavigationControls).
    // If a real stylesheet already defines .chapter-unavailable-focus, that
    // will simply take precedence -- this is just a safe fallback so the
    // feature isn't invisible out of the box.
    (function() {
        const s = document.createElement("style");
        s.textContent = ".chapter-unavailable-focus { opacity: 0.4; font-style: italic; }";
        document.head.appendChild(s);
    })();

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

    
    
    // Author/work display names now come from catalog.json's "authors" map
    // and each work's "title" field (written once, in the notebook, from
    // the same WORK_REGISTRY metadata the rest of the build already uses)
    // rather than being hand-typed here. This used to be two separate
    // hardcoded objects that had to be kept in sync by hand across every
    // page that needed a display name -- see buildWorkPickerFromCatalog
    // below and map.html for the two places that read catalog.authors /
    // catalog.works[wk].title now.

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
    // Extracts a language code from a version's short_id (e.g.
    // "daphne-tb-grc1" -> "grc", "daphne-tb-cn1" -> "cn"). Mirrors the
    // same suffix-scanning approach used elsewhere in this project (the
    // Logeion lexicon's textgroup scoping): checks every hyphen-
    // separated segment, not just the trailing one, since a real
    // edition id has been seen embedding its code mid-string; strips
    // trailing digits before matching; explicitly excludes "tb" itself
    // (a literal infix in treebank ids like "kassel-tb-grc1", not a
    // language code).
    function _versionLangCode(shortId) {
        const segs = (shortId || "").split("-");
        let found = null;
        for (const seg of segs) {
            const code = seg.replace(/\d+$/, "").toLowerCase();
            if (/^[a-z]{2,4}$/.test(code) && code !== "tb") {
                found = code;
            }
        }
        return found;
    }

    // A treebank id's language-like suffix (grc/ara/fas) marks the SOURCE
    // text's own script, not the annotation/gloss language -- that's a
    // different thing, and for these three it defaults to English
    // (unmarked in the id). Only a genuinely different annotation
    // language gets its own explicit marker (e.g. "cn" for Chinese) --
    // and that marker-only id doesn't restate the source script itself
    // (e.g. "daphne-tb-cn1" has no "grc" in it at all, even though it
    // annotates the same Greek text as its "daphne-tb-grc1" sibling).
    // So the source script comes from the WORK's own edition(s), not
    // from each individual treebank id, and is combined with each
    // treebank's own annotation language for display (e.g. "grc-en",
    // "grc-cn").
    const TREEBANK_SOURCE_SCRIPT_CODES = new Set(['grc', 'ara', 'fas']);

    function countDocTypes(versions) {
        const counts = { edition: 0, translation: 0, commentary: 0 };
        const treebankLangs = {};

        // Source script: the language of this work's own edition(s) --
        // first one found wins (a work's editions are normally all the
        // same source language anyway).
        let sourceLang = null;
        for (const v of versions || []) {
            if (v && v.doc_type === 'edition') {
                const code = _versionLangCode(v.short_id);
                if (code) { sourceLang = code; break; }
            }
        }

        for (const v of versions || []) {
            if (!v) continue;
            if (Object.prototype.hasOwnProperty.call(counts, v.doc_type)) {
                counts[v.doc_type]++;
            } else if (v.doc_type === 'treebank') {
                const rawCode = _versionLangCode(v.short_id);
                let source, annotationLang;
                if (rawCode && TREEBANK_SOURCE_SCRIPT_CODES.has(rawCode)) {
                    // This id self-describes its own source script (it
                    // may be annotating a translation edition, not the
                    // work's primary language -- e.g. an Arabic treebank
                    // of Bishr Matta's translation of a Greek work) --
                    // trust it over the work-level default.
                    source = rawCode;
                    annotationLang = 'en';
                } else if (rawCode) {
                    // A non-script code (e.g. "cn") is the annotation
                    // language; this id doesn't self-describe a source,
                    // so fall back to the work's own edition language.
                    source = sourceLang || '?';
                    annotationLang = rawCode;
                } else {
                    source = sourceLang || '?';
                    annotationLang = 'en';
                }
                const lang = `${source}-${annotationLang}`;
                treebankLangs[lang] = (treebankLangs[lang] || 0) + 1;
            }
        }
        counts.treebankLangs = treebankLangs;
        return counts;
    }

    function formatWorkMeta(meta) {
        const counts = countDocTypes(meta.versions);
        const treebankBits = Object.keys(counts.treebankLangs).sort()
            .map(lang => counts.treebankLangs[lang] + " tb " + lang);
        if (counts.edition || counts.translation || counts.commentary || treebankBits.length) {
            const bits = [];
            if (counts.edition) bits.push(counts.edition + " ed" + (counts.edition > 1 ? "s" : ""));
            if (counts.translation) bits.push(counts.translation + " tr");
            if (counts.commentary) bits.push(counts.commentary + " comm");
            bits.push(...treebankBits);
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
            ((catalog.authors || {})[a] || a).localeCompare((catalog.authors || {})[b] || b));

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
            const author = (catalog.authors || {})[tg] || tg;
            const workKeys = byAuthor[tg].sort((a, b) =>
                ((works[a] || {}).title || a).localeCompare((works[b] || {}).title || b));

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
                const title = meta.title || meta.label;
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
                    // wParam may be a plain "workKey" or "workKey:passage", or
                    // a full CTS URN ("urn:cts:NS:tg.wk[.version]:range") --
                    // extract the work key accordingly rather than assuming
                    // "everything before the first colon" (which grabs "urn"
                    // for a CTS URN, since urn:cts: itself contains colons).
                    const ctsUrn = wParam.startsWith("urn:cts:") ? parseCtsUrn(wParam) : null;
                    const workKey = ctsUrn ? ctsUrn.workKey : wParam.split(":")[0];
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
        return  wKey.startsWith("tlg2045.") ||  wKey.startsWith("phi0620.") || wKey.startsWith("tlg0001.") || wKey.startsWith("tlg0006.") || wKey.startsWith("tlg0011.") || wKey.startsWith("tlg0012.") || wKey.startsWith("tlg0020.") || wKey.startsWith("ferdowsi.") || wKey.startsWith("tlg0085."); 
    }
    // Generic per-work terminology, replacing the old hardcoded "Book"/
    // "Chapter" literals scattered through the nav UI. Sourced from
    // catalog.json's works[workKey].unit_labels (set by the notebook from
    // work_registry.json's own optional "unit_labels" field -- see
    // WORK_REGISTRY docs). Defaults to the original Book/Chapter/Section
    // wording when a work doesn't specify its own, so every existing work
    // renders exactly as before with zero registry changes required.
    // Poetry's "Lines" override (isPoetryWork) is intentionally orthogonal
    // and still wins over whatever `chapter` label a work sets, since a
    // verse work's own unit_labels would normally just say "Chapter" too.
    const DEFAULT_UNIT_LABELS = { book: "Book", chapter: "Chapter", section: "Section" };
    function getUnitLabels(wKey) {
        const fromCatalog = CATALOG && CATALOG.works && CATALOG.works[wKey] && CATALOG.works[wKey].unit_labels;
        return Object.assign({}, DEFAULT_UNIT_LABELS, fromCatalog || {});
    }
    // Optional per-book display titles (e.g. a speech collection's real
    // titles instead of bare numbers), from catalog.json's
    // works[workKey].book_titles = {"1": "I. Oratio nataliciis...", ...}.
    // Falls back to `${labels.book} ${bk}` when a work has none.
    function getBookTitle(wKey, bk) {
        const fromCatalog = CATALOG && CATALOG.works && CATALOG.works[wKey] && CATALOG.works[wKey].book_titles;
        if (fromCatalog && fromCatalog[bk]) return fromCatalog[bk];
        return `${getUnitLabels(wKey).book} ${bk}`;
    }
    // Optional one-line topic summary per book (e.g. Boeckh's own English
    // "SUMMARIES OF THE SPEECHES" front matter -- "On Sparta and Athens,
    // the most famous republics among the Greeks"), from catalog.json's
    // works[workKey].book_summaries = {"1": "On Sparta and Athens...", ...}.
    // Returns null (not a fallback string) when a work has none, so callers
    // can decide whether to show anything at all rather than rendering an
    // empty subtitle.
    function getBookSummary(wKey, bk) {
        const fromCatalog = CATALOG && CATALOG.works && CATALOG.works[wKey] && CATALOG.works[wKey].book_summaries;
        return (fromCatalog && fromCatalog[bk]) ? fromCatalog[bk] : null;
    }
    // True when this book has a real catalog title (not just the generic
    // "Book N" fallback) -- used to decide whether a nav button can safely
    // compact down to a bare number, since a bare number is only legible
    // when there's somewhere else (the hover popup) for the full title to
    // go. Works with no book_titles at all keep their existing short
    // "Book N"/"Speech N" labels unchanged -- those are already compact,
    // nothing to gain by hiding them behind a hover.
    function hasBookTitle(wKey, bk) {
        const fromCatalog = CATALOG && CATALOG.works && CATALOG.works[wKey] && CATALOG.works[wKey].book_titles;
        return !!(fromCatalog && fromCatalog[bk]);
    }
    function _escapeHtml(s) {
        const div = document.createElement("div");
        div.innerText = s;
        return div.innerHTML;
    }
    // Custom hover popup for compacted book buttons, replacing the native
    // `title` attribute tooltip: shows instantly on mouseenter (no ~1s
    // browser delay), is actually visible rather than relying on a sustained
    // hover nobody thinks to try on a bare number, and can hold both the
    // full title and the one-line summary together. Built once and reused/
    // repositioned per hover rather than recreated each time.
    let _bookHoverPopupEl = null;
    function _ensureBookHoverPopup() {
        if (_bookHoverPopupEl) return _bookHoverPopupEl;
        const el = document.createElement("div");
        el.id = "book-hover-popup";
        el.style.cssText = "position:fixed;z-index:9999;max-width:360px;padding:8px 12px;" +
            "background:#2b2b2b;color:#f0f0f0;font-size:13px;line-height:1.4;" +
            "border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,0.3);" +
            "pointer-events:none;display:none;";
        document.body.appendChild(el);
        _bookHoverPopupEl = el;
        return el;
    }
    function _showBookHoverPopup(anchorEl, title, summary) {
        const el = _ensureBookHoverPopup();
        el.innerHTML = `<div style="font-weight:600;${summary ? "margin-bottom:4px;" : ""}">${_escapeHtml(title)}</div>` +
            (summary ? `<div style="opacity:0.85;font-style:italic;">${_escapeHtml(summary)}</div>` : "");
        const rect = anchorEl.getBoundingClientRect();
        el.style.left = `${Math.round(rect.left)}px`;
        el.style.top = `${Math.round(rect.bottom + 6)}px`;
        el.style.display = "block";
    }
    function _hideBookHoverPopup() {
        if (_bookHoverPopupEl) _bookHoverPopupEl.style.display = "none";
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
        // NOTE (regression fix): these two queries used to have no
        // textgroup/work scoping at all -- fine only as long as the loaded
        // DB happened to contain exactly one work. The "Mount Local Data
        // Asset" flow in index_shell.html loads corpus_alignment_grid.db --
        // the full multi-work monolith, not a per-work shard -- straight
        // into the browser, so an unscoped "SELECT DISTINCT book/chapter
        // FROM alignment_grid" pulls in every OTHER work's books/chapters
        // (and whatever oddities their own book/chapter labels carry) right
        // alongside this one's, and folds them into the same sort_order
        // ordering, which is only coherent within a single work. Every
        // other query in this file scopes by (textgroup, work) exactly like
        // idx_grid_lookup expects (see getChaptersWithContent below) --
        // this one should too.
        const books_result = window.dbInstance.exec(
            "SELECT DISTINCT book FROM alignment_grid WHERE textgroup=? AND work=? AND book IS NOT NULL ORDER BY CAST(book AS INTEGER)",
            [tg, wk]);
        const books = books_result[0] ? books_result[0].values.map(r => r[0]) : [];
        
        if (books.length > 0) {
            const bookMap = {};
            books.forEach(bk => {
                const chapter_result = window.dbInstance.exec(
                    "SELECT DISTINCT chapter FROM alignment_grid WHERE textgroup=? AND work=? AND book=? ORDER BY sort_order",
                    [tg, wk, bk]);
                bookMap[bk] = chapter_result[0] ? chapter_result[0].values.map(r => r[0]) : [];
            });
            window.GLOBAL_STRUCTURES = window.GLOBAL_STRUCTURES || {};
            window.GLOBAL_STRUCTURES[activeWorkKey] = bookMap;
            console.log("[v40] multi-book structure with " + books.length + " books");
        } else {
            const chapter_result = window.dbInstance.exec(
                "SELECT DISTINCT chapter FROM alignment_grid WHERE textgroup=? AND work=? ORDER BY sort_order",
                [tg, wk]);
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

// Parses "urn:cts:NAMESPACE:TEXTGROUP.WORK[.VERSION]:REF" where REF is
// either a single passage ("1.4") or a range ("1.4-1.7"). VERSION (the
// edition/version short_id, e.g. "perseus-grc2") is optional -- CTS URNs
// are valid with or without it. Returns null if the string doesn't match a
// CTS URN shape at all (caller falls through to older URL forms).
// Given a raw citable line/section number (e.g. the "4" in a CTS URN ref
// "1.4"), finds which internal chapter actually contains it. "Chapter" is
// frequently an artificial pagination chunk rather than the line number
// itself -- Storr-style card intervals (Homer, Sophocles) and Ferdowsi's
// curated Pizzi reading selections both group several consecutive lines
// under one chapter id, so a raw line number can't be assumed to equal a
// chapter id directly. Pass book=null for flat-structure works (no book
// division at all, so nothing to filter by there). Falls back to treating
// rawLine as the chapter itself if no match is found or the db isn't
// ready -- which is only correct for works that genuinely don't chunk, so
// it's logged rather than failing silently.
function resolveChapterForRawLine(workKey, book, rawLine) {
    if (rawLine == null) return rawLine;

    // Card/line-range works (poetry_cards, card_prose, line_commentary parse
    // modes in the ingest notebook -- covers essentially all of Sophocles,
    // Homer, Hesiod, and Aeschylus) don't store one alignment_grid row per
    // verse line. Each card's whole line span is written as a SINGLE row
    // with section="1" (see parse_poetry_cards_tei /
    // parse_card_prose_tei), so a "WHERE section=?" lookup for a raw verse
    // line like "377" can never find anything for these works -- there is
    // no such row. What these works DO give us is the card's own line
    // range as the chapter label itself (e.g. "375-390", built by
    // build_poetry_canonical_intervals), already sitting in
    // GLOBAL_STRUCTURES from populateNavigationFromShard(). So resolve the
    // raw line against those chapter labels directly first -- exact, and
    // needs no DB query at all -- and only fall back to the alignment_grid
    // section lookup below for genuinely section-addressed works (e.g.
    // Thucydides, Aristotle's Poetics) where individual sections really
    // are stored as separate rows.
    if (!isNaN(parseInt(rawLine, 10))) {
        const ln = parseInt(rawLine, 10);
        const chapterList = isFlatStructure(workKey)
            ? (GLOBAL_STRUCTURES[workKey] || [])
            : ((GLOBAL_STRUCTURES[workKey] && GLOBAL_STRUCTURES[workKey][book]) || []);
        for (const chLabel of chapterList) {
            const m = /^(\d+)-(\d+)$/.exec(String(chLabel));
            if (m && ln >= parseInt(m[1], 10) && ln <= parseInt(m[2], 10)) {
                return chLabel;
            }
        }
    }

    if (!window.dbInstance) return rawLine;
    try {
        const [tg, wk] = workKey.split(".");
        let sql = "SELECT chapter FROM alignment_grid WHERE textgroup=? AND work=? AND section=?";
        const params = [tg, wk, String(rawLine)];
        if (book != null) { sql += " AND book=?"; params.push(String(book)); }
        sql += " LIMIT 1";
        const stmt = window.dbInstance.prepare(sql);
        stmt.bind(params);
        const found = stmt.step() ? stmt.getAsObject().chapter : null;
        stmt.free();
        if (found) return found;
        console.warn(`[url] no alignment_grid row and no matching card-range chapter for ${workKey} book=${book} section=${rawLine} -- ` +
            `falling back to treating "${rawLine}" as the chapter itself, which is likely wrong.`);
        return rawLine;
    } catch (e) {
        console.warn("[url] alignment_grid lookup failed:", e.message, "-- falling back to raw value as chapter.");
        return rawLine;
    }
}

// Resolves a passage spec ("377", "377-378", "1.4", "1.4-1.7", "1.5.12")
// into {book, chapter, sectionRange} for a given work. Shared by the plain
// "workKey:passage" URL form and the full CTS URN form -- both need
// identical book/chapter/range resolution once the work key itself is
// known, and keeping it in one place is deliberate: these two forms already
// drifted apart once (the URN form gained range + chapter-resolution
// support first; this consolidation is what brings the plain form back in
// sync with it, rather than fixing each in isolation again next time).
//
// For a SINGLE (non-range) spec, if its second-to-last component already
// names a known chapter/card id for this work, it's used directly with no
// database lookup -- this preserves exact behavior for links generated
// elsewhere in the app (e.g. the treebank search tool) that already pass a
// valid internal chapter id rather than a raw external line citation. A
// dash-range always skips that fast path and resolves both endpoints as
// raw lines, since a range is unambiguously a line citation, not a
// chapter-to-chapter span.
function resolvePassageSpec(workKey, spec) {
    spec = (spec || "").replace(/\s+/g, "");
    const isRange = spec.includes('-');
    const [startRef, endRefRaw] = spec.split('-');
    const endRef = endRefRaw || startRef;
    const startSegs = startRef.split(".");
    const endSegs = endRef.split(".");

    if (isFlatStructure(workKey)) {
        const startLine = startSegs[startSegs.length - 1];
        const endLine = endSegs[endSegs.length - 1];

        if (!isRange && (GLOBAL_STRUCTURES[workKey] || []).includes(startLine)) {
            return { book: null, chapter: startLine, sectionRange: null };
        }

        const chapter = resolveChapterForRawLine(workKey, null, startLine);
        if (endLine !== startLine) {
            const endCh = resolveChapterForRawLine(workKey, null, endLine);
            if (endCh !== chapter) {
                console.warn(`[url] passage "${spec}" spans multiple chapters (${chapter} vs ${endCh}) -- ` +
                    `only same-chapter ranges are currently supported; showing chapter ${chapter} only.`);
            }
        }
        return { book: null, chapter, sectionRange: { start: startLine, end: endLine } };
    } else {
        const book = startSegs[0];

        if (!isRange && startSegs.length >= 2) {
            const known = (GLOBAL_STRUCTURES[workKey] && GLOBAL_STRUCTURES[workKey][book]) || [];
            // Prose works store chapters in FOLDED "book.chapter" form
            // (e.g. "1.1"), so a plain 2-segment ref like "1.1" needs to
            // be checked against the FULL folded key (startRef), not
            // just its second segment alone -- checking only startSegs[1]
            // ("1") never matches a known list of folded keys like
            // ["1.1","1.2",...], so a bare whole-chapter reference (e.g.
            // "?w=tlg0003.tlg001:1.1", no section) always fell through to
            // the range-parsing code below, which then wrongly treated
            // that trailing "1" as a specific section to highlight
            // instead of recognizing the whole chapter was requested.
            if (startSegs.length === 2 && known.includes(startRef)) {
                return { book, chapter: startRef, sectionRange: null };
            }
            if (known.includes(startSegs[1])) {
                return { book, chapter: startSegs[1],
                         sectionRange: startSegs[2] ? { start: startSegs[2], end: startSegs[2] } : null };
            }
        }

        // endSegs[endSegs.length-1] is the line whether or not the end ref
        // carried its own book prefix -- for a plain range end like "379"
        // (no dot), endSegs is just ["379"] and endSegs[0] IS the line, not
        // a book. The previous `endSegs.length > 1 ? ... : startLine` guard
        // treated that as "no line given" and silently collapsed the end of
        // the range onto the start, so "1.377-379" resolved as if only
        // "377" had been requested. Mirrors the flat-structure branch above,
        // which never had this bug.
        const startLine = startSegs.length > 1 ? startSegs[startSegs.length - 1] : "1";
        const endLine = endSegs[endSegs.length - 1];
        const chapter = resolveChapterForRawLine(workKey, book, startLine);
        // Only treat this as a book mismatch when the end ref actually named
        // its own book (endSegs.length > 1) -- an end ref with no book
        // segment ("379") implicitly belongs to the same book as the start,
        // not to some other book that happens to match endSegs[0] (which
        // would be the line number, not a book, in that case).
        if (endSegs.length > 1 && endSegs[0] !== startSegs[0]) {
            console.warn(`[url] passage "${spec}" spans multiple books -- ` +
                `only same-book ranges are currently supported; showing book ${book} only.`);
        } else if (endLine !== startLine) {
            const endCh = resolveChapterForRawLine(workKey, book, endLine);
            if (endCh !== chapter) {
                console.warn(`[url] passage "${spec}" spans multiple chapters (${chapter} vs ${endCh}) -- ` +
                    `only same-chapter ranges are currently supported; showing chapter ${chapter} only.`);
            }
        }
        return { book, chapter, sectionRange: { start: startLine, end: endLine } };
    }
}

function initializeRoutingFromURL() { 
        console.log('[v40] initializeRoutingFromURL, activeWorkKey:', activeWorkKey); 
        
        // 1. Parse the URL safely
        const params = new URLSearchParams(window.location.search);
        // const rawParam = params.get("w") || "tlg0003.tlg001";
        const rawParam = params.get("w") || activeWorkKey;
        let b = null, ch = "1";
        activeSectionFilter = null;
        activeSectionRange = null;
        
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

        // A full CTS URN, e.g. "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.4-1.7"
        // -- optionally naming a specific edition/version, and optionally a
        // passage RANGE ("start-end") rather than a single passage. Checked
        // before the plain "workKey:passage" form below since a URN also
        // contains colons and would otherwise be misparsed by it.
        const ctsUrn = rawParam.startsWith("urn:cts:") ? parseCtsUrn(rawParam) : null;

        // 2. Resolve which work key the URL actually points to, and (re)build
        // GLOBAL_STRUCTURES/TEXT_REGISTRY for THAT work before doing any
        // passage resolution below. This has to happen before that
        // resolution -- populateNavigationFromShard() populates structures
        // keyed off whatever activeWorkKey currently is, and until this
        // point that's still the default/previous work, not the one named
        // in ?w=. Calling it too early (as a prior version of this function
        // did) leaves GLOBAL_STRUCTURES[urlWorkKey] undefined, which makes
        // isFlatStructure() misreport and resolvePassageSpec() silently
        // misparse -- and getChapterDataPayload() then fails to find the
        // work at all, so triggerTargetNavigation() bails out early and the
        // page hangs on "Mounting layout frameworks...".
        activeWorkKey = ctsUrn ? ctsUrn.workKey
            : rawParam.includes(":") ? rawParam.split(":")[0]
            : rawParam;
        populateNavigationFromShard();

        if (ctsUrn) {
            // Only apply the URN's own version if the URL didn't separately
            // specify ?focus= -- an explicit focus= always wins.
            if (ctsUrn.version && !columnEditions.f) columnEditions.f = ctsUrn.version;

            const spec = ctsUrn.endRef && ctsUrn.endRef !== ctsUrn.startRef
                ? `${ctsUrn.startRef}-${ctsUrn.endRef}` : (ctsUrn.startRef || "1");
            const resolved = resolvePassageSpec(activeWorkKey, spec);
            b = resolved.book; ch = resolved.chapter; activeSectionRange = resolved.sectionRange;
        } else if (rawParam.includes(":")) {
            const querySegments = rawParam.split(":");
            activeWorkKey = querySegments[0];
            const resolved = resolvePassageSpec(activeWorkKey, querySegments[1]);
            b = resolved.book; ch = resolved.chapter; activeSectionRange = resolved.sectionRange;
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
                        // Default column configuration: source edition,
                        // translation, treebank -- or, when this work has
                        // no treebank, a second translation instead.
                        // Applies only to the first three columns (the
                        // default column count); columns beyond that keep
                        // cycling through the existing interleaved
                        // priority list (editions/translations/
                        // commentaries/appcrits, then treebanks, then
                        // metrics), unchanged.
                        let defaultId = "";
                        if (prefix === 'f') {
                            defaultId = editions[0] ? editions[0][0] : (prioritizedList[0] || "");
                        } else if (prefix === 'c1') {
                            defaultId = translations[0] ? translations[0][0] : (prioritizedList[1] || "");
                        } else if (prefix === 'c2') {
                            defaultId = treebanks[0] ? treebanks[0][0]
                                : (translations[1] ? translations[1][0] : (prioritizedList[2] || ""));
                        } else {
                            defaultId = prioritizedList.length > 0
                                ? prioritizedList[idx % prioritizedList.length]
                                : "";
                        }
                        columnEditions[prefix] = defaultId;
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
        if (activeSectionRange) {
            // Center the FIRST highlighted line, not the whole match set --
            // for a short range this keeps every requested line on screen at
            // once; for a longer one it's at least a sane anchor point.
            setTimeout(() => {
                const el = document.querySelector('.urn-range-highlight');
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 50);
        }
        updateDiffToggleVisibility();
        // NOTE: previously gated on `!activePairId` too (skip reapply
        // whenever ANY alignment pair is active, regardless of which
        // columns), on the theory that diffing would destroy alignment
        // token spans. Confirmed by direct test that this isn't actually
        // true in practice -- manually toggling the diff checkbox while an
        // unrelated alignment pair (Bywater GRC <-> Butcher ENG) was active
        // cleanly applied 13 diffs with no corruption, because the columns
        // being diffed (F/C3, both Greek) were entirely different from the
        // columns holding the alignment (grc1/eng2). onDiffToggle (the
        // manual path) never had this check and was always the one actually
        // working; the automatic reapply was needlessly stricter than the
        // path it's supposed to mirror. Dropped to match.
        if (diffEnabled) {
            // Diff a single pair only — see onDiffToggle. Rendering every pairwise
            // combination overwrites shared column DOM and lights up identical neighbours.
            //
            // Deferred one frame: this runs synchronously in the same tick as
            // the appendChild calls just above that built the new chapter's
            // content, whereas the manual "uncheck, then recheck the diff
            // checkbox" workaround runs as a separate later browser event --
            // i.e. always after the browser has settled the just-inserted
            // DOM. Deferring via requestAnimationFrame makes the automatic
            // re-apply match that same timing rather than racing it, which
            // is the working theory for why navigating to a new chunk left
            // the checkbox checked but nothing highlighted, requiring the
            // manual uncheck/recheck to actually see a diff.
            requestAnimationFrame(() => {
                const pairs = findSameLangColumnPairs();
                console.log("[diff-reapply] fired. pairs:", pairs.length, pairs.map(p => p.leftPrefix+"v"+p.rightPrefix));
                if (pairs.length > 0) applyColumnDiff(pairs[0].leftPrefix, pairs[0].rightPrefix);
            });
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

    // Shared by both the prose and poetry diff paths: reads a text container's
    // word tokens from a cached clean baseline (so repeated toggles never
    // re-diff already-injected diff markup), stripping milestone/Bekker
    // number spans first since those remain in textContent even though CSS
    // hides them, and would otherwise shift token indices.
    function _diffTokensFromCell(cell) {
        if (cell.dataset.diffBaseline === undefined) cell.dataset.diffBaseline = cell.innerHTML;
        const clone = document.createElement('div');
        clone.innerHTML = cell.dataset.diffBaseline;
        clone.querySelectorAll('.inline-line-milestone, .milestone').forEach(el => el.remove());
        const text = (clone.textContent || "").trim();
        const isWord = t => /[a-zA-ZͰ-Ͽἀ-῿Ā-ɏЀ-ӿ]/.test(t);
        return text.split(/\s+/).filter(t => t && isWord(t));
    }

    // For a poetry row, map line-number -> its .line-text-cell element.
    // .line-num-cell and .line-text-cell are written as separate adjacent
    // sibling divs per line (see renderNavigationControls' urn-range-highlight
    // handling, which has the same data-n-or-textContent fallback for the
    // same reason: most editions don't set a lineno_sigil, so the line
    // number exists only as the num-cell's own text, not an attribute).
    function _poetryLineCells(row) {
        const map = new Map();
        row.querySelectorAll('.line-num-cell').forEach(numCell => {
            const n = numCell.hasAttribute('data-n')
                ? numCell.getAttribute('data-n')
                : numCell.textContent.trim();
            const textCell = numCell.nextElementSibling;
            if (n && textCell && textCell.classList.contains('line-text-cell')) {
                map.set(n, textCell);
            }
        });
        return map;
    }

    // Apply diff highlighting to already-rendered column content.
    // Skips treebank, metrical, and any column with an active alignment pair
    // (which would destroy aln-token spans). Handles two DOM shapes:
    // prose rows (.prose-body-inline, one blob per card) and poetry rows
    // (.line-num-cell/.line-text-cell pairs, one per verse line) -- these
    // are built by genuinely different code paths in renderNavigationControls
    // and previously only the prose shape was diffed; poetry rows have no
    // .prose-body-inline at all, so the diff silently found nothing to do.
    // Poetry lines are matched by LINE NUMBER, not row position, since two
    // editions can legitimately have different line counts within a shared
    // card (see the card_anchor="poem" work).
    function applyColumnDiff(leftPrefix, rightPrefix) {

        // Validate both columns are plain prose (not treebank/metrical)
        const leftMeta  = TEXT_REGISTRY[columnEditions[leftPrefix]];
        const rightMeta = TEXT_REGISTRY[columnEditions[rightPrefix]];
        if (!leftMeta || !rightMeta) { console.log("[diff] bail: missing TEXT_REGISTRY meta", leftPrefix, rightPrefix); return; }
        if (leftMeta.doc_type  === 'treebank' || leftMeta.doc_type  === 'metrical') { console.log("[diff] bail: left is treebank/metrical"); return; }
        if (rightMeta.doc_type === 'treebank' || rightMeta.doc_type === 'metrical') { console.log("[diff] bail: right is treebank/metrical"); return; }

        const leftCol  = document.getElementById(`content_${leftPrefix}`);
        const rightCol = document.getElementById(`content_${rightPrefix}`);
        if (!leftCol || !rightCol) { console.log("[diff] bail: missing content container", leftPrefix, rightPrefix); return; }

        const leftRows = leftCol.querySelectorAll('.section-row');
        console.log(`[diff] applyColumnDiff(${leftPrefix}, ${rightPrefix}): ${leftRows.length} .section-row in left column`);
        let matchedRows = 0, proseRows = 0, poetryRows = 0, diffsApplied = 0;

        leftRows.forEach(leftRow => {
            const secClass = [...leftRow.classList].find(c => c.startsWith('s-idx-'));
            if (!secClass) return;
            const rightRow = rightCol.querySelector(`.${secClass}`);
            if (!rightRow) return;
            matchedRows++;

            const leftBody  = leftRow.querySelector('.prose-body-inline');
            const rightBody = rightRow.querySelector('.prose-body-inline');

            if (leftBody && rightBody) {
                proseRows++;
                // ── Prose: one diff across the whole card's text ──
                const leftToks  = _diffTokensFromCell(leftBody);
                const rightToks = _diffTokensFromCell(rightBody);
                if (!leftToks.length || !rightToks.length) return;

                const {leftOut, rightOut} = tokenDiff(leftToks, rightToks);
                const hasDiff = leftOut.some(x => x.type !== "same") || rightOut.some(x => x.type !== "same");
                if (!hasDiff) return;
                diffsApplied++;

                leftBody.innerHTML  = renderDiffTokens(leftOut);
                rightBody.innerHTML = renderDiffTokens(rightOut);
                return;
            }

            // ── Poetry: align tokens across the WHOLE card, not line-by-line ──
            // Editions routinely disagree about where line breaks fall --
            // especially in lyric passages, where a print edition may break
            // mid-word at a column width (Boeckh's Antigone: his line 100 is
            // "...τὸ κάλ-", his 101 is "λιστον...", continuing the same word
            // Storr prints whole on one line). Matching by line NUMBER then
            // treats that as two "different" lines and the mismatch cascades
            // for everything after it. Fix: flatten every line's tokens into
            // one continuous sequence per column (tagging each token with
            // which line it actually came from), diff that ONE sequence
            // against the other column's, then regroup the aligned output
            // back by original line before injecting it -- so alignment
            // happens across the whole passage regardless of line breaks,
            // but each edition still displays under its own correct line
            // numbers afterward.
            poetryRows++;
            const leftLines  = _poetryLineCells(leftRow);
            const rightLines = _poetryLineCells(rightRow);
            if (!leftLines.size || !rightLines.size) {
                console.log(`[diff] poetry row ${secClass}: leftLines=${leftLines.size} rightLines=${rightLines.size} (no .line-num-cell found)`);
                return;
            }

            const flatten = (lineMap) => {
                const flat = [];
                lineMap.forEach((cell, lineN) => {
                    _diffTokensFromCell(cell).forEach(tok => flat.push({tok, lineN, cell}));
                });
                return flat;
            };
            const leftFlat  = flatten(leftLines);
            const rightFlat = flatten(rightLines);
            if (!leftFlat.length || !rightFlat.length) return;

            const {leftOut, rightOut} = tokenDiff(
                leftFlat.map(x => x.tok), rightFlat.map(x => x.tok));

            const hasDiff = leftOut.some(x => x.type !== "same") || rightOut.some(x => x.type !== "same");
            if (!hasDiff) return;
            diffsApplied++;

            // Regroup diff output back by the line it actually came from,
            // preserving within-line order, then render each line's cell
            // from just its own slice.
            const regroup = (flat, out) => {
                const byLine = new Map();
                out.forEach((item, k) => {
                    const lineN = flat[k].lineN;
                    if (!byLine.has(lineN)) byLine.set(lineN, []);
                    byLine.get(lineN).push(item);
                });
                return byLine;
            };
            const leftByLine  = regroup(leftFlat, leftOut);
            const rightByLine = regroup(rightFlat, rightOut);

            leftLines.forEach((cell, lineN) => {
                const items = leftByLine.get(lineN);
                if (items) cell.innerHTML = renderDiffTokens(items);
            });
            rightLines.forEach((cell, lineN) => {
                const items = rightByLine.get(lineN);
                if (items) cell.innerHTML = renderDiffTokens(items);
            });
        });
        console.log(`[diff] done: ${matchedRows} rows matched left<->right (${proseRows} prose, ${poetryRows} poetry), ${diffsApplied} diffs actually applied`);
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
            // Book buttons carry the raw book number in data-book (set at
            // creation time) -- NOT parsed from the displayed label, which
            // may be a work-specific term ("Speech 3") or a real title
            // ("I. Oratio nataliciis...") rather than literally "Book N".
            currentBk = currentActiveBkEl ? currentActiveBkEl.dataset.book : Object.keys(GLOBAL_STRUCTURES[activeWorkKey])[0];
        }
        triggerTargetNavigation(currentBk, currentCh);
    }

    // Opens map.html scoped to whatever passage is currently on screen.
    // Reuses the exact same current-book/current-chapter DOM reading as
    // triggerViewRefresh/updateURLState, and -- critically -- passes book
    // and chapter as SEPARATE params, the same way triggerTargetNavigation
    // itself does, rather than folding them into one string. The DOM
    // already shows the chapter value in whatever format alignment_grid
    // actually expects for this work (folded "book.chapter" for prose like
    // Thucydides, a bare card label like "1-21" for poetry like the Iliad
    // -- book is tracked separately there since bare card labels legally
    // recur across different books), so this reads it faithfully instead
    // of reconstructing it.
    function openMapForCurrentPassage() {
        let currentBk = null, currentCh = "1";
        const currentActiveChEl = document.querySelector("#chapter-items-container a.current");
        if (currentActiveChEl) currentCh = currentActiveChEl.innerText;

        if (!isFlatStructure(activeWorkKey)) {
            const currentActiveBkEl = document.querySelector("#book-items-container a.current");
            currentBk = currentActiveBkEl ? currentActiveBkEl.dataset.book : Object.keys(GLOBAL_STRUCTURES[activeWorkKey])[0];
        }

        // If a SECTION is also selected on top of a folded prose chapter
        // (dot-separated, e.g. "3.3.2"), roll up to chapter depth --
        // ToposText's citation data for these pilot works never goes
        // deeper than chapter. Never touches poetry card labels (dash-
        // separated, e.g. "1-21"), which never contain a dot.
        const dotParts = currentCh.split(".");
        const chapterValue = dotParts.length > 2 ? dotParts.slice(0, 2).join(".") : currentCh;

        const params = new URLSearchParams({ work: activeWorkKey, chapter: chapterValue });
        if (currentBk) params.set("book", currentBk);
        window.open(`./map.html?${params.toString()}`, "_blank");
    }

    // Opens map.html scoped to the whole book currently on screen (e.g.
    // all of Thucydides Book 3), rather than just the current chapter.
    // For flat/bookless works (no book concept -- e.g. Agamemnon), maps
    // the whole work instead, since "book" has no meaning there.
    function openMapForCurrentBook() {
        if (isFlatStructure(activeWorkKey)) {
            const url = `./map.html?work=${encodeURIComponent(activeWorkKey)}&whole=1`;
            window.open(url, "_blank");
            return;
        }
        const currentActiveBkEl = document.querySelector("#book-items-container a.current");
        const currentBk = currentActiveBkEl ? currentActiveBkEl.dataset.book : Object.keys(GLOBAL_STRUCTURES[activeWorkKey])[0];
        const url = `./map.html?work=${encodeURIComponent(activeWorkKey)}&book=${encodeURIComponent(currentBk)}`;
        window.open(url, "_blank");
    }

    function updateURLState(book, chapter) {
        const params = new URLSearchParams();
        // Prefer the originally-requested raw-line range over the resolved
        // chapter/card label when one is active. For card-based poetry
        // works, `chapter` here is an internal card id (e.g. "371-403")
        // that the ingest pipeline invented to group lines for storage --
        // not what the person typed or would recognize. Writing that back
        // into the URL silently swaps their citation ("377-379") for an
        // unrelated one and breaks re-sharing/reloading with the same
        // highlighted lines. activeSectionRange still holds the original
        // request (see resolvePassageSpec), so use it here when present.
        let passageValue;
        if (activeSectionRange) {
            const { start, end } = activeSectionRange;
            passageValue = book ? `${book}.${start}` : start;
            if (end !== start) passageValue += `-${end}`;
        } else {
            passageValue = book ? `${book}.${chapter}` : `${chapter}`;
            if (activeSectionFilter) passageValue += `.${activeSectionFilter}`;
        }

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
        activeSectionRange = null;
        triggerViewRefresh();
    }

    // Returns a Set of chapter labels, within `book`, that `versionShortId`
    // actually has a text_segments row for -- i.e. real content, not just a
    // slot in the union chapter_sequence some OTHER edition introduced (see
    // notebook cell 3: an edition with no content at a card gets no row at
    // all now, specifically so this query can distinguish the two cleanly).
    function getChaptersWithContent(workKey, book, versionShortId) {
        if (!window.dbInstance || !versionShortId) return null;
        const parts = workKey.split(".");
        let q = `SELECT DISTINCT ag.chapter FROM alignment_grid ag
                 JOIN text_segments ts ON ag.passage_urn = ts.passage_urn
                 WHERE ag.textgroup='${parts[0]}' AND ag.work='${parts[1]}'
                 AND ts.version_short_id='${versionShortId}'`;
        if (book) q += ` AND ag.book='${book}'`;
        const result = window.dbInstance.exec(q);
        if (!result.length) return new Set();
        return new Set(result[0].values.map(r => r[0]));
    }

    // Returns the Focus edition's OWN chapter reading order for (work, book)
    // as an array, or null when there's nothing to prefer -- no Focus
    // edition selected, or this shard predates edition_chapter_order (older
    // build), or this edition never diverges from canonical and simply has
    // no rows. Callers fall back to GLOBAL_STRUCTURES's canonical (shared
    // union) order in all of those cases.
    //
    // Why this matters: GLOBAL_STRUCTURES/alignment_grid.sort_order is ONE
    // order every edition shares (the union of all cards, sorted naturally).
    // That's wrong whenever an edition's own printed order genuinely differs
    // -- e.g. Sidgwick's Eumenides swaps two stanzas of the binding song
    // relative to Smyth's card numbering (372-376 before 368-371). The build
    // pipeline (Cell 4's _merge_local_order) already computes each edition's
    // true reading order at ingest time; this just reads it back.
    function getFocusChapterOrder(workKey, book, versionShortId) {
        if (!window.dbInstance || !versionShortId) return null;
        const [tg, wk] = workKey.split(".");
        let q = `SELECT chapter FROM edition_chapter_order
                 WHERE textgroup='${tg}' AND work='${wk}' AND version_short_id='${versionShortId}'`;
        q += book ? ` AND book='${book}'` : ` AND book IS NULL`;
        q += ` ORDER BY local_sort_index`;
        let result;
        try {
            result = window.dbInstance.exec(q);
        } catch (e) {
            // Older shard built before this table existed -- fall back silently.
            return null;
        }
        if (!result.length || !result[0].values.length) return null;
        return result[0].values.map(r => r[0]);
    }

    // Reorders `canonicalList` (GLOBAL_STRUCTURES's shared union order) into
    // the Focus edition's own reading order when one is recorded and its
    // chapter SET matches exactly (defensive: a length/content mismatch
    // means stale or partial data, so fall back to canonical rather than
    // risk silently dropping or duplicating a TOC entry).
    function focusAwareChapterOrder(workKey, book, versionShortId, canonicalList) {
        const order = getFocusChapterOrder(workKey, book, versionShortId);
        if (!order || order.length !== canonicalList.length) return canonicalList;
        const canonicalSet = new Set(canonicalList);
        for (const ch of order) if (!canonicalSet.has(ch)) return canonicalList;
        return order;
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
                    const a = document.createElement("a");
                    const fullTitle = getBookTitle(activeWorkKey, bk);
                    const summary = getBookSummary(activeWorkKey, bk);
                    const compact = hasBookTitle(activeWorkKey, bk);
                    // Compact to a bare number when there's a real title to
                    // show on hover instead -- otherwise keep the existing
                    // short "Book N"/"Speech N" label as-is (already compact,
                    // nothing gained by hiding it behind a hover).
                    a.innerText = compact ? bk : fullTitle;
                    a.dataset.book = bk;
                    if (compact || summary) {
                        a.addEventListener("mouseenter", () => _showBookHoverPopup(a, fullTitle, summary));
                        a.addEventListener("mouseleave", _hideBookHoverPopup);
                    }
                    if(bk === payload.book) a.className = "current";
                    a.onclick = () => { activeSectionFilter = null; activeSectionRange = null; triggerTargetNavigation(bk, GLOBAL_STRUCTURES[activeWorkKey][bk][0]); };
                    bookContainer.appendChild(a);
                });
            }
        }

        const bookLabelEl = document.getElementById("chapter-row-label");
        if (bookLabelEl) bookLabelEl.innerText = isDramaOrPoetry ? "Lines:" : `${getUnitLabels(activeWorkKey).chapter}s:`;

        const chapterContainer = document.getElementById("chapter-items-container");
        // Canonical union order (shared default) vs. the Focus edition's own
        // reading order, when recorded -- see focusAwareChapterOrder above.
        // Scoped to poetry/drama for now, matching getChaptersWithContent's
        // existing scoping just below; the build pipeline computes this for
        // every work regardless of genre, so prose could opt in later too.
        const canonicalChList = isFlatStructure(activeWorkKey) ? GLOBAL_STRUCTURES[activeWorkKey] : GLOBAL_STRUCTURES[activeWorkKey][payload.book];
        const chList = isDramaOrPoetry
            ? focusAwareChapterOrder(activeWorkKey, payload.book, columnEditions.f, canonicalChList)
            : canonicalChList;
        if (chapterContainer) {
            chapterContainer.innerHTML = "";
            // The TOC deliberately shows the UNION of every edition's own
            // card labels (e.g. Butler's "8a" alongside Muller's "13b"), so
            // an editorial split introduced by any one edition stays visible
            // and navigable -- that disagreement is real scholarly content,
            // not noise. But not every button leads to real Focus-edition
            // content: mark (don't remove) the ones the current Focus
            // edition has nothing at, so it's clear at a glance which clicks
            // land on real text vs. a "not divided separately here" note.
            let focusHasContent = isDramaOrPoetry
                ? getChaptersWithContent(activeWorkKey, payload.book, columnEditions.f)
                : null;
            // Sanity check: the chapter on screen right now is proof-positive
            // that the focus edition has content there (it's rendering, we're
            // looking at it). If the query disagrees -- claims the current
            // chapter has nothing -- the query result itself is wrong for
            // this render (bad book filter, stale/empty version_short_id,
            // whatever the exact cause), not the data. Trusting it anyway
            // greys out every button, including ones that plainly work, and
            // actively misleads with "not divided separately here" on
            // content that plainly IS there. Fail safe: skip greying
            // entirely for this render rather than mislabel real content.
            if (focusHasContent && payload.chapter && !focusHasContent.has(payload.chapter)) {
                console.log("[chapter-toc] getChaptersWithContent disagrees with what's on screen -- skipping greying this render", payload.chapter, [...focusHasContent]);
                focusHasContent = null;
            }
            chList.forEach(ch => {
                const a = document.createElement("a"); a.innerText = ch;
                if(ch === payload.chapter) a.className = "current";
                if (focusHasContent && !focusHasContent.has(ch)) {
                    a.classList.add("chapter-unavailable-focus");
                    a.title = "Not divided separately in the focus edition -- click to see other editions here";
                }
                a.onclick = () => { activeSectionFilter = null; activeSectionRange = null; triggerTargetNavigation(payload.book, ch); };
                chapterContainer.appendChild(a);
            });
        }

        if (!isDramaOrPoetry) {
            const sectionContainer = document.getElementById("section-items-container");
            if (sectionContainer) {
                sectionContainer.innerHTML = "";
                naturalSectionKeys(payload.sections).forEach(sec => {
                    const a = document.createElement("a"); a.innerText = sec; a.className = "sec-pill";
                    if (sec === activeSectionFilter || sectionValueInRange(sec)) a.classList.add("active-pill");
                    a.onclick = () => selectSectionDirectly(sec);
                    sectionContainer.appendChild(a);
                });
            }
        }

        const railNodesTarget = document.getElementById("rail-nodes-target");
        const railTitle = document.getElementById("rail-title");
        if (railNodesTarget) {
            railNodesTarget.innerHTML = "";
            const unitLabels = getUnitLabels(activeWorkKey);
            if (isFlatStructure(activeWorkKey)) {
                railTitle.innerText = isDramaOrPoetry ? "Lines Tree" : `${unitLabels.chapter}s Tree`;
                // Reuses the same (possibly Focus-reordered) chList computed
                // above for the main chapter TOC, so the rail tree and the
                // TOC never disagree about reading order.
                chList.forEach(ch => {
                    const n = document.createElement("div");
                    n.className = `rail-tree-item ${(payload.chapter === ch) ? 'active-rail-node' : ''}`;
                    n.innerText = isDramaOrPoetry ? `Lines ${ch}` : `${unitLabels.chapter} ${ch}`;
                    n.onclick = () => { activeSectionFilter = null; activeSectionRange = null; triggerTargetNavigation(null, ch); };
                    railNodesTarget.appendChild(n);
                });
            } else {
                const bookDisplay = getBookTitle(activeWorkKey, payload.book);
                railTitle.innerText = isPoetryWork(activeWorkKey) ? `${bookDisplay} Lines` : `${bookDisplay} ${unitLabels.chapter}s`;
                // Surface the book's one-line topic summary (if the work has
                // one -- see getBookSummary) right under the rail title,
                // where it's visible whenever you're browsing this book, not
                // just on hover like the nav-list tooltip set above.
                let subtitleEl = document.getElementById("rail-title-subtitle");
                const summary = getBookSummary(activeWorkKey, payload.book);
                if (summary) {
                    if (!subtitleEl) {
                        subtitleEl = document.createElement("div");
                        subtitleEl.id = "rail-title-subtitle";
                        subtitleEl.style.fontSize = "0.85em";
                        subtitleEl.style.opacity = "0.75";
                        subtitleEl.style.fontStyle = "italic";
                        subtitleEl.style.marginTop = "2px";
                        railTitle.insertAdjacentElement("afterend", subtitleEl);
                    }
                    subtitleEl.innerText = summary;
                    subtitleEl.style.display = "";
                } else if (subtitleEl) {
                    subtitleEl.style.display = "none";
                }
                chList.forEach(ch => {
                    const n = document.createElement("div");
                    n.className = `rail-tree-item ${(payload.chapter === ch) ? 'active-rail-node' : ''}`;
                    n.innerText = isPoetryWork(activeWorkKey) ? `Lines ${ch}` : `${unitLabels.chapter} ${ch}`;
                    n.onclick = () => { activeSectionFilter = null; activeSectionRange = null; triggerTargetNavigation(payload.book, ch); };
                    railNodesTarget.appendChild(n);
                });
            }
        }
    }

    // Numeric comparison, not string comparison -- "9" < "10" lexicographically
    // is false, which would silently break any range crossing a power of ten.
    // Falls back to exact-match-either-endpoint for non-numeric section ids
    // (rare, but some lexicon/apparatus-style sections use non-digit keys).
    function sectionValueInRange(secValue) {
        if (!activeSectionRange || secValue == null) return false;
        const n = parseInt(secValue, 10);
        const a = parseInt(activeSectionRange.start, 10);
        const b = parseInt(activeSectionRange.end, 10);
        if (!isNaN(n) && !isNaN(a) && !isNaN(b)) return n >= a && n <= b;
        return String(secValue) === String(activeSectionRange.start) ||
               String(secValue) === String(activeSectionRange.end);
    }

    function tbSentMatchesSection(sent, filter, isPoetry) {
        if (activeSectionRange) {
            // sent.section is a synthetic "1" for card-based poetry works
            // (one row covers a whole card's line span), and sent.chapter is
            // the resolved multi-line card label itself (e.g. "371-403") --
            // parseInt'ing that just grabs its first number ("371"), which
            // is essentially never inside the requested range and previously
            // caused EVERY sentence to fail this check, get tb-sent-dimmed,
            // and vanish (that class is display:none, not a dim effect --
            // see styles.css). sent.subdoc is the sentence's own citation
            // (the raw verse line, e.g. "377") and is what should actually
            // be compared against a raw-line range like 377-379.
            return isPoetry ? sectionValueInRange(sent.subdoc) : sectionValueInRange(sent.section);
        }
        if (!filter) return true;
        if (isPoetry) {
            // Two possible poetry addressing shapes: flat "chapter = line number"
            // (single-level poems, where this used to only check sent.chapter)
            // or "chapter = reading/grouping, section = line number within it"
            // (e.g. Ferdowsi's curated Pizzi selections -- chapter is WHICH
            // reading, section is the verse line inside it). Check both rather
            // than assuming every poetry work uses the flat shape; assuming
            // only sent.chapter silently hid every sentence for any poetry
            // work using the two-level shape, since chapter never equals a
            // line-number filter in that structure.
            return sent.chapter === filter || sent.section === filter;
        } else {
            return sent.section === filter;
        }
    }

function renderTreebankColumn(container, activeEditionMeta, payload) {
        const wKey = activeWorkKey;
        const tgKey = wKey.split('.')[0];
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
        // For book-structured works, prose treebank rows are now stored
        // under a book-qualified key ("book.chapter", e.g. "1.89") so that
        // the same chapter number in a different book (very common --
        // Thucydides book 2 chapter 1 vs book 3 chapter 1) doesn't collide
        // under one key -- treebank_sentences has no separate book column,
        // so this compound string IS the only disambiguator. Existing
        // card-based poetry treebanks (Homer, Sophocles, etc.) still store
        // the bare card label with no book prefix, so fall back to that if
        // the compound lookup misses.
        const lookupKey = payload.book ? `${payload.book}.${chapter}` : chapter;
        const allSentences = chapterData[lookupKey] || chapterData[chapter] || [];
        if (allSentences.length === 0) {
            container.innerHTML = '<p style="color:#999;font-style:italic;padding:12px">No treebank sentences for chapter ' + chapter + '.</p>';
            setTranslitControlVisible(prefix, false);
            return;
        }
        const speakerMap = SPEAKERS_DATA[wKey] || {};
        const docCredits = TREEBANK_DOC_CREDITS[tbKey] || { annotators: [], source: null };
        const isPoetry = isPoetryWork(wKey);
        container.innerHTML = '';

        if (!LOGEION_SHARDS_FOR_TEXTGROUP.has(tgKey)) {
            ensureLogeionShardsLoaded(tgKey, () => {
                // Only re-render if the reader is still looking at this
                // same chapter's treebank -- avoids a late-resolving fetch
                // clobbering content after they've since navigated away.
                if (TREEBANK_DATA[tbKey] === chapterData) {
                    renderTreebankColumn(container, activeEditionMeta, payload);
                }
            });
        }

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
            const inRange = activeSectionRange && inFocus;
            const block = document.createElement('div');
            block.className = 'tb-sentence-block' + (inFocus ? '' : ' tb-sent-dimmed') + (inRange ? ' urn-range-highlight' : '');
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
                    _tbFillDetailPanel(panel, tok, headTok, depToks);
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
                const sentHasGloss = sent.tokens.some(t => t.gloss || logeionGlossFor(t, tgKey));

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
                        const logeionDef = logeionGlossFor(tok, tgKey);
                        glossSpan.textContent = tok.gloss
                            ? (logeionDef ? `${tok.gloss} \u00b7 ${logeionDef}` : tok.gloss)
                            : (logeionDef || '\u00b7');
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
            if (!isPoetry && sent.tokens.some(t => t.gloss || logeionGlossFor(t, tgKey))) {
                const glRow = document.createElement('div');
                glRow.className = 'tb-gloss-row';
                sent.tokens.forEach(tok => {
                    const isPunct = tok.upos === 'PUNCT' || tok.upos === '_';
                    if (isPunct) return;
                    const span = document.createElement('span');
                    span.className = 'tb-tok tb-gloss-tok';
                    span.dataset.tokId = tok.id;
                    const logeionDef = logeionGlossFor(tok, tgKey);
                    span.textContent = tok.gloss
                        ? (logeionDef ? `${tok.gloss} \u00b7 ${logeionDef}` : tok.gloss)
                        : (logeionDef || '\u00b7');
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

            block.addEventListener('click', (e) => {
                if (e.target.closest('.tb-detail-panel')) return; // selecting/copying text inside the panel shouldn't close it
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

    // Builds an <a> to the sibling search app pre-filled with a gloss/lemma
    // search for `term`, restricted to `mode` ('gloss' | 'lemma'). Opens in
    // a new tab so the reader keeps its place. Falls back to plain escaped
    // text if `term` is empty.
    function tbSearchLink(term, mode, innerHtml) {
        if (!term) return innerHtml;
        const href = `${SEARCH_APP_URL}?q=${encodeURIComponent(term)}&mode=${mode}`;
        const label = mode === 'gloss' ? 'Search this gloss' : 'Search this lemma';
        return `<a class="tb-annot-link" href="${href}" target="_blank" rel="noopener" title="${label}">${innerHtml}</a>`;
    }

    function renderTokenDetail(tok, headTok, depToks) {
        const rc = tbRelColor(tok.deprel);
        const pc = tbPosColor(tok.upos);
        // Romanization sits right next to the word itself, not just in the
        // grid row below -- for a script most readers can't sound out
        // (Japanese, etc.), burying it in a conditional detail row means
        // it's easy to miss entirely. Shown inline whenever present; the
        // grid row further down is kept too, so it still lines up visually
        // with Gloss/POS/etc. for readers scanning that list.
        let h = `<div class="tb-detail-word">${escHtml(tok.form)}` +
            (tok.translit
                ? ` <span class="tb-detail-word-translit" dir="ltr" style="font-style:italic;font-weight:normal;font-size:0.55em;color:#888;vertical-align:middle">${escHtml(tok.translit)}</span>`
                : '') +
            `</div><div class="tb-detail-grid">`;
        if (tok.translit)
            h += `<span class="tb-dk">Translit</span><span class="tb-dv" dir="ltr" style="font-style:italic">${escHtml(tok.translit)}</span>`;
        if (tok.gloss)
            h += `<span class="tb-dk">Gloss</span><span class="tb-dv tb-gloss">${tbSearchLink(tok.gloss, 'gloss', escHtml(tok.gloss))}</span>`;
        if (tok.lemma && tok.lemma !== '_' && tok.lemma !== tok.form)
            h += `<span class="tb-dk">Lemma</span><span class="tb-dv tb-greek">${tbSearchLink(tok.lemma, 'lemma', escHtml(tok.lemma))}${tok.ltranslit ? ' <span dir="ltr" style="font-style:italic;color:#888;font-size:11px">'+escHtml(tok.ltranslit)+'</span>' : ''}</span>`;
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
        return h + '</div><div class="tb-lex-slot"></div>';
    }

    // Shared by all three token-detail call sites (text-mode interlinear,
    // tree-mode dependency diagram, tree-mode annotation grid). Fills the
    // panel synchronously as before, then kicks off the lexicon lookup
    // without blocking -- the dictionary section fades in once its shard
    // has loaded (first click on a work is the only slow one; the shard
    // is cached for every click after that).
    function _tbFillDetailPanel(panel, tok, headTok, depToks) {
        panel.innerHTML = renderTokenDetail(tok, headTok, depToks);
        panel.classList.add('tb-detail-visible');
        _tbApplyTranslitToPanel(panel);
        const slot = panel.querySelector('.tb-lex-slot');
        const textgroup = (typeof activeWorkKey === 'string' ? activeWorkKey.split('.')[0] : null);
        if (slot && textgroup) populateLexiconSlot(slot, tok, textgroup);
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
                        if (panel) { _tbFillDetailPanel(panel, t, ht, dps); }
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
            if (panel) { _tbFillDetailPanel(panel, t, ht, dps); }
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
                // For card-based poetry works (Sophocles, Homer, Hesiod,
                // Aeschylus -- anything ingested via poetry_cards/card_prose),
                // a whole card's line span is stored under ONE synthetic
                // section key ("1"), not one row per line -- see
                // resolveChapterForRawLine's comment. Comparing that "1"
                // against a requested line range like 377-379 can never
                // match, so the old range-hiding logic here hid the entire
                // card's content whenever a raw-line URL was used. The real
                // per-line granularity lives inside this section's own HTML,
                // as data-n attributes on .line-num-cell elements (written by
                // extract_text_recursive in the ingest notebook) -- so for
                // poetry, skip whole-section hiding/highlighting here and
                // instead highlight the matching individual lines below,
                // after the content is in the DOM.
                const inRange = !isPoetry && activeSectionRange && sectionValueInRange(sec);
                const isHidden = isPoetry ? false : (activeSectionRange
                    ? !inRange
                    : (activeSectionFilter !== null && activeSectionFilter !== sec));
                const row = document.createElement("div");
                row.className = `section-row s-idx-${sec} ${isHidden ? 'hidden-section' : ''} ${inRange ? 'urn-range-highlight' : ''}`;
                let txt = payload.sections[sec][shortId] || "<i>Not divided separately in this edition.</i>";
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
                // Line-level highlight for a requested raw-line range (see
                // comment above) -- .line-num-cell and its sibling
                // .line-text-cell are written as separate adjacent divs per
                // line (not a shared per-line wrapper), so both need the
                // class individually for the highlight to cover the whole line.
                if (activeSectionRange) {
                    // data-n is only written when the edition config sets a
                    // lineno_sigil (see extract_text_recursive in the ingest
                    // notebook); most editions -- including this one -- don't
                    // set one, so the line number exists only as the cell's
                    // own plain text content ("377"), not an attribute.
                    // Without this fallback, .line-num-cell[data-n] matches
                    // nothing for such editions and no line is ever
                    // highlighted, even though the range resolved correctly.
                    wrapper.querySelectorAll('.line-num-cell').forEach(numCell => {
                        const n = numCell.hasAttribute('data-n')
                            ? numCell.getAttribute('data-n')
                            : numCell.textContent.trim();
                        if (!n || !sectionValueInRange(n)) return;
                        numCell.classList.add('urn-range-highlight');
                        const textCell = numCell.nextElementSibling;
                        if (textCell && textCell.classList.contains('line-text-cell')) {
                            textCell.classList.add('urn-range-highlight');
                        }
                    });
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
        activeSectionRange = null;
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
        activeSectionRange = null;
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
            applyLexiconLatinPref();
        });
    })();

    const dz = document.getElementById('drop-zone');
    if(dz) {
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor = '#660000'; dz.style.background = '#fdfbef'; });
        dz.addEventListener('dragleave', () => { dz.style.borderColor = '#ccc'; dz.style.background = '#fafafa'; });
        dz.addEventListener('drop', e => { e.preventDefault(); dz.style.borderColor = '#ccc'; dz.style.background = '#fafafa'; handleFileSelection(e.dataTransfer.files); });
    }
  