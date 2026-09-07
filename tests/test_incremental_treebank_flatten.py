import json
import sqlite3

from pipeline.treebank.flatten import flatten_treebank_tokens


def test_partial_flatten_preserves_unrelated_work():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE treebank_sentences (
            id INTEGER PRIMARY KEY,
            textgroup TEXT, work TEXT, version_short_id TEXT,
            chapter TEXT, section TEXT, subdoc TEXT, book TEXT,
            sentence_json TEXT
        )
    """)
    flatten_treebank_tokens(conn)

    token = lambda form: json.dumps([{"id": 1, "form": form, "lemma": form}])
    conn.executemany(
        "INSERT INTO treebank_sentences VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (1, "tlg1", "wk1", "ed1", "1", "1", "s1", None, token("new")),
            (2, "tlg1", "wk2", "ed1", "1", "1", "s2", None, token("keep")),
        ],
    )
    # This simulates an existing flattened table.  The unrelated row should
    # survive byte-for-byte while wk1 is refreshed from sentence_json.
    conn.execute("""
        INSERT INTO treebank_tokens
          (textgroup, work, version_short_id, sentence_id, chapter, section,
           subdoc, book, tok_id, stable_id, form, form_norm)
        VALUES ('tlg1','wk2','ed1',2,'1','1','s2',NULL,1,'sentinel','old','old')
    """)

    flatten_treebank_tokens(conn, ["tlg1.wk1"])

    assert conn.execute(
        "SELECT stable_id, form FROM treebank_tokens WHERE work='wk2'"
    ).fetchall() == [("sentinel", "old")]
    assert conn.execute(
        "SELECT form FROM treebank_tokens WHERE work='wk1'"
    ).fetchall() == [("new",)]

