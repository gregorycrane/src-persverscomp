"""`--index-only` (`make index`) exists because index.html is only rebuilt
as a side effect of at least one work being re-ingested -- so editing
web/app.js, web/styles.css, or web/index_shell.html (not TEI sources, so
never "stale" per the manifest) would otherwise need `make force` to show
up, at the cost of wastefully re-ingesting the entire corpus. This test
locks in all three behaviors: a plain rebuild embeds web/app.js as it was
at build time; a plain `make` afterward correctly leaves index.html alone
when only web/app.js changed; `--index-only` picks up that change cheaply,
without touching ingestion at all.
"""
import json
import shutil
import tempfile
import importlib
import sys
from pathlib import Path

import pipeline.config as config
from conftest import reset_pipeline_modules

FIXTURE = Path(__file__).parent / "fixtures" / "poetry_cards_minimal.xml"


def _make_env():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "src" / "web").mkdir(parents=True)
    (tmp / "build").mkdir(parents=True)
    (tmp / "persverscomp").mkdir(parents=True)
    (tmp / "src" / "web" / "index_shell.html").write_text(
        "<html>%%PERSEUS_STYLES%%%%PERSEUS_APP_JS%%</html>")
    (tmp / "src" / "web" / "styles.css").write_text("body{}")
    (tmp / "src" / "web" / "app.js").write_text("console.log('v1')")

    work_registry = {
        "tlg0085.tlg007": {
            "textgroup": "tlg0085", "work": "tlg007", "doc_type": "poetry_cards",
            "editions": {"perseus-grc2": {
                "path": str(FIXTURE), "label": "(Storr, 1922) Test",
                "class": "edition", "parse_mode": "poetry_cards"}},
        }
    }
    (tmp / "src" / "work_registry.json").write_text(json.dumps(work_registry))
    (tmp / "src" / "manifest.json").write_text("{}")

    config.SRC_DIR = tmp / "src"
    config.BUILD_DIR = tmp / "build"
    config.DB_PATH = config.BUILD_DIR / "corpus_alignment_grid.db"
    config.WORKSPACE_DIR = tmp / "persverscomp"

    reset_pipeline_modules()
    build_all = importlib.import_module("pipeline.build_all")
    return tmp, build_all


def test_index_only_picks_up_web_changes_without_reingesting():
    tmp, build_all = _make_env()
    try:
        build_all.main(["--work", "tlg0085.tlg007"])
        html = (tmp / "persverscomp" / "index.html").read_text()
        assert "console.log('v1')" in html

        (tmp / "src" / "web" / "app.js").write_text("console.log('v2')")

        build_all.main([])  # plain make: app.js isn't a manifest dependency
        html = (tmp / "persverscomp" / "index.html").read_text()
        assert "console.log('v1')" in html, "plain make should not have touched index.html"

        build_all.main(["--index-only"])
        html = (tmp / "persverscomp" / "index.html").read_text()
        assert "console.log('v2')" in html, "--index-only should have picked up the app.js edit"
    finally:
        shutil.rmtree(tmp)
