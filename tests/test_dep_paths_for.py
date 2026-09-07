"""dep_paths_for() maps each work's *own* per-edition parse_mode to the
right parser module, so editing parser code correctly invalidates the
manifest for every work that uses it. This used to key off a work-level
`doc_type` field that doesn't exist in any real work_registry.json (dispatch
is per edition/translation/commentary entry, and one work can mix several
parse_modes) -- meaning parser-code changes silently never triggered a
rebuild. This is a synthetic-but-representative regression test for that:
real work_registry.json entries aren't available in this repo (they're
build-only data, not tracked here -- see build_all.py's docstring), so this
mirrors the shape of a real multi-parse_mode work instead.
"""
from pipeline.build_all import dep_paths_for


def test_dep_paths_includes_the_parser_file_each_entry_actually_uses():
    meta = {
        "textgroup": "tlg0085", "work": "tlg007",
        "editions": {"a": {"path": "/tmp/a.xml", "parse_mode": "poetry_cards"}},
        "translations": {"b": {"path": "/tmp/b.xml", "parse_mode": "card_prose"}},
        "commentaries": {"c": {"path": "/tmp/c.xml", "parse_mode": "line_commentary"}},
        "scholia": {"s": {"path": "/tmp/s.xml", "parse_mode": "line_commentary"}},
        "appcrits": {},
        "treebanks": {"d": {"path": "/tmp/d.conllu", "parse_mode": "conllu"}},
    }
    deps = dep_paths_for("tlg0085.tlg007", meta)
    names = {p.name for p in deps}
    assert "poetry_cards.py" in names
    assert "card_prose.py" in names
    assert "line_commentary.py" in names
    assert "conllu.py" in names
    # source files themselves are still tracked too
    assert any(str(p) == "/tmp/a.xml" for p in deps)
    assert any(str(p) == "/tmp/s.xml" for p in deps)


def test_dep_paths_falls_back_to_hierarchical_when_parse_mode_omitted():
    meta = {
        "textgroup": "tlg0003", "work": "tlg001",
        "editions": {"a": {"path": "/tmp/a.xml"}},  # no parse_mode -- matches ~half of real entries
        "translations": {}, "commentaries": {}, "scholia": {}, "appcrits": {}, "treebanks": {},
    }
    deps = dep_paths_for("tlg0003.tlg001", meta)
    names = {p.name for p in deps}
    assert "hierarchical.py" in names
