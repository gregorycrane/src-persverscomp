"""Makes `pipeline` importable from tests/ without installing the package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def reset_pipeline_modules():
    """Any test that patches pipeline.config (SRC_DIR, DB_PATH, etc.) and
    then needs OTHER already-imported pipeline modules to pick up the new
    values must force those modules to be re-imported fresh -- `from
    pipeline.registry import WORK_REGISTRY`-style imports elsewhere in the
    package freeze a reference at first-import time, not a live link.

    Deleting a submodule from sys.modules alone is NOT enough to force
    that: Python's `from pipeline import index_builder` (used inside
    build_all.py) first checks whether `index_builder` is already an
    ATTRIBUTE of the `pipeline` package object, and that attribute survives
    a sys.modules deletion -- so it silently returns the stale module
    instead of re-importing. This was a real bug in this exact helper
    (caught by test_index_only.py failing with a stale tmp-dir path from
    a PREVIOUS test's fixture, not its own) -- fixed by also clearing the
    matching attribute off the `pipeline` package object itself, which
    forces a genuine re-import on the next `from pipeline import ...`.

    Always call this AFTER patching pipeline.config, before importing
    anything else from the package.
    """
    pipeline_pkg = sys.modules.get("pipeline")
    for modname in list(sys.modules):
        if modname.startswith("pipeline.") and modname != "pipeline.config":
            del sys.modules[modname]
            attr = modname.split(".", 1)[1].split(".")[0]  # e.g. "index_builder" or "core"
            if pipeline_pkg is not None and hasattr(pipeline_pkg, attr):
                delattr(pipeline_pkg, attr)
