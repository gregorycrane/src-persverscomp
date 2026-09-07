"""Explode treebank_sentences.sentence_json into one-row-per-token
treebank_tokens, for client-side SQL search (WHERE lemma_norm=? etc.)
instead of deserializing every sentence's JSON in the browser.

Relocated from Cell 5 ("CELL 1b"), wrapped as a function taking an open
connection instead of opening BUILD_DIR/DB_PATH itself, so it composes with
ingest_work.py's persistent-connection model and with reconstitute.py
(call this AFTER merging shards to regenerate treebank_tokens with fresh,
internally-consistent sentence_id values -- see core/storage.py's
DERIVED_TABLES note for why treebank_tokens is never merged directly).

Run AFTER treebank_sentences is populated/merged and BEFORE sharding.
"""
import json as _json
from pipeline.treebank.norm_key import norm_key


def flatten_treebank_tokens(conn, work_keys=None):
    """Refresh all tokens, or only the supplied ``textgroup.work`` keys."""
    cur = conn.cursor()
    required_cols = {
        "id", "textgroup", "work", "version_short_id", "sentence_id",
        "chapter", "section", "subdoc", "book", "tok_id", "stable_id",
        "form", "form_norm", "lemma", "lemma_norm", "upos", "xpos",
        "feats", "head", "deprel", "gloss", "ref", "translit", "ltranslit",
    }
    existing_cols = {
        row[1] for row in cur.execute("PRAGMA table_info(treebank_tokens)").fetchall()
    }
    partial = bool(work_keys) and required_cols.issubset(existing_cols)

    if partial:
        pairs = [tuple(key.split(".", 1)) for key in work_keys]
        cur.executemany(
            "DELETE FROM treebank_tokens WHERE textgroup=? AND work=?", pairs)
    else:
        cur.execute("DROP TABLE IF EXISTS treebank_tokens")
        cur.execute("""
            CREATE TABLE treebank_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textgroup TEXT NOT NULL,
            work TEXT NOT NULL,
            version_short_id TEXT NOT NULL,
            sentence_id INTEGER NOT NULL,
            chapter TEXT NOT NULL,
            section TEXT,
            subdoc TEXT,
            book TEXT,
            tok_id INTEGER NOT NULL,
            stable_id TEXT NOT NULL,
            form TEXT NOT NULL,
            form_norm TEXT NOT NULL,
            lemma TEXT,
            lemma_norm TEXT,
            upos TEXT,
            xpos TEXT,
            feats TEXT,
            head INTEGER,
            deprel TEXT,
            gloss TEXT,
            ref TEXT,
            translit TEXT,
            ltranslit TEXT
            )
        """)
        cur.execute("CREATE INDEX idx_tt_lemma_norm ON treebank_tokens(lemma_norm)")
        cur.execute("CREATE INDEX idx_tt_form_norm  ON treebank_tokens(form_norm)")
        cur.execute("CREATE INDEX idx_tt_work       ON treebank_tokens(textgroup, work)")
        cur.execute("CREATE INDEX idx_tt_upos       ON treebank_tokens(upos)")
        # Keep this non-unique for legacy reconstructed sentence rows.
        cur.execute("CREATE INDEX idx_tt_stable_id ON treebank_tokens(textgroup, work, version_short_id, stable_id)")

    select_sql = """
        SELECT id, textgroup, work, version_short_id, chapter, section, subdoc, book, sentence_json
        FROM treebank_sentences
    """
    params = []
    if partial:
        select_sql += " WHERE " + " OR ".join(
            "(textgroup=? AND work=?)" for _ in pairs)
        params = [value for pair in pairs for value in pair]
    rows = cur.execute(select_sql, params).fetchall()

    n_sent, n_tok, n_skipped = 0, 0, 0
    for sid, tg, wk, ver, chapter, section, subdoc, book, sjson in rows:
        n_sent += 1
        try:
            tokens = _json.loads(sjson)
        except (TypeError, ValueError):
            n_skipped += 1
            continue
        if not isinstance(tokens, list):
            n_skipped += 1
            continue
        for tok in tokens:
            form = tok.get('form')
            if not form:
                continue
            lemma = tok.get('lemma')
            cur.execute("""
                INSERT INTO treebank_tokens
                    (textgroup, work, version_short_id, sentence_id, chapter, section, subdoc, book,
                     tok_id, stable_id, form, form_norm, lemma, lemma_norm, upos, xpos, feats,
                     head, deprel, gloss, ref, translit, ltranslit)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                tg, wk, ver, sid, chapter, section, subdoc, book,
                tok.get('id'), tok.get('stable_id') or f'urn:perseus:treebank:{tg}.{wk}.{ver}:{subdoc}.{tok.get("id")}',
                form, norm_key(form), lemma, norm_key(lemma),
                tok.get('upos'), tok.get('xpos'), tok.get('feats'),
                tok.get('head'), tok.get('deprel'), tok.get('gloss'),
                tok.get('ref'), tok.get('translit'), tok.get('ltranslit'),
            ))
            n_tok += 1

    conn.commit()
    scope = f" for {len(pairs)} changed work(s)" if partial else ""
    print(f"\u2713 treebank_tokens{scope}: {n_tok} tokens from {n_sent} sentences "
          f"({n_skipped} sentences skipped/unparseable)")
    return n_tok
