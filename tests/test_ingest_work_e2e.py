"""End-to-end smoke test: a real (minimal) TEI file through the actual
ingest_editions_and_structure() dispatch path for doc_type=poetry_cards.

This is the test that WOULD have caught the OrderedDict-import bugs in
poetry_cards.py / card_prose.py / line_commentary.py before they shipped --
the earlier test suite only checked plumbing (schema, registries, norm_key),
never actually ran a parser. Keep this pattern: at least one fixture-driven
test per parser is worth more than any amount of import-checking.
"""
import json
import sqlite3
import tempfile
import shutil
import importlib
from pathlib import Path

import pipeline.config as config
from conftest import reset_pipeline_modules

FIXTURE = Path(__file__).parent / "fixtures" / "poetry_cards_minimal.xml"


def _make_env():
    """Builds an isolated fixture environment and returns the freshly
    (re-)imported build_all module wired to it.

    NOTE: pipeline.ingest_work, pipeline.sharding, and pipeline.build_all
    all do `from pipeline.registry import WORK_REGISTRY` at MODULE level --
    a reference frozen at first-import time. Simply reassigning
    `pipeline.registry.WORK_REGISTRY` after those modules are already
    imported does NOT propagate to them (Python's `from x import y` binds
    a value once, it isn't a live link). So instead of monkeypatching
    already-imported modules, write work_registry.json to disk FIRST, then
    import everything fresh -- the normal, non-fragile way this actually
    works in production (where work_registry.json exists before the
    process starts and is never swapped out mid-run).
    """
    tmp = Path(tempfile.mkdtemp())
    (tmp / "src" / "web").mkdir(parents=True)
    (tmp / "build").mkdir(parents=True)
    (tmp / "persverscomp").mkdir(parents=True)
    (tmp / "src" / "web" / "index_shell.html").write_text(
        "<html>%%PERSEUS_STYLES%%%%PERSEUS_APP_JS%%</html>")
    (tmp / "src" / "web" / "styles.css").write_text("body{}")
    (tmp / "src" / "web" / "app.js").write_text("console.log('x')")

    work_registry = {
        "tlg0085.tlg007": {
            "textgroup": "tlg0085", "work": "tlg007", "doc_type": "poetry_cards",
            "editions": {
                "perseus-grc2": {
                    "path": str(FIXTURE), "label": "(Storr, 1922) Test Edition",
                    "class": "edition", "parse_mode": "poetry_cards",
                }
            },
        }
    }
    (tmp / "src" / "work_registry.json").write_text(json.dumps(work_registry))
    (tmp / "src" / "manifest.json").write_text("{}")

    config.SRC_DIR = tmp / "src"
    config.BUILD_DIR = tmp / "build"
    config.DB_PATH = config.BUILD_DIR / "corpus_alignment_grid.db"
    config.WORKSPACE_DIR = tmp / "persverscomp"

    # Force every already-imported pipeline module that read SRC_DIR-derived
    # paths at ITS OWN import time to re-import against the now-patched
    # config -- see conftest.reset_pipeline_modules for why this needs to be
    # more than a plain sys.modules deletion.
    reset_pipeline_modules()

    build_all = importlib.import_module("pipeline.build_all")
    return tmp, build_all


def test_poetry_cards_fixture_end_to_end():
    tmp, build_all = _make_env()
    try:
        assert not config.DB_PATH.exists()
        build_all.main(["--work", "tlg0085.tlg007"])

        conn = sqlite3.connect(str(config.DB_PATH))
        units = conn.execute("SELECT canonical_id, doc_type FROM text_units").fetchall()
        grid = conn.execute(
            "SELECT passage_urn, chapter FROM alignment_grid ORDER BY sort_order"
        ).fetchall()
        segs = dict(conn.execute("SELECT passage_urn, content_html FROM text_segments").fetchall())
        conn.close()

        assert units == [("tlg0085_tlg007_storr_1922", "edition")]
        assert [ch for _, ch in grid] == ["1-2", "3-4"]
        assert "alpha" in segs[grid[0][0]]
        assert "beta" in segs[grid[0][0]]
        assert "gamma" in segs[grid[1][0]]
        assert (config.WORKSPACE_DIR / "index.html").exists()
    finally:
        shutil.rmtree(tmp)
