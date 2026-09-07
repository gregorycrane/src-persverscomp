"""Delete the temp build monolith. Relocated from Cell 15, unchanged.

NOTE from the original design (still true): the monolith is now a
PERSISTENT, incrementally-updated build artifact (see ingest_work.py) --
run this only when you actually want to force the next build to
reconstitute from shards rather than continue mutating an existing
monolith in place. It's still always safe: reconstitute.py can rebuild it
from site/data/**/*.db with no TEI re-parsing needed.
"""
from pathlib import Path
import shutil
from pipeline.config import BUILD_DIR


def clean():
    if BUILD_DIR.exists():
        n = sum(1 for _ in BUILD_DIR.rglob("*"))
        shutil.rmtree(BUILD_DIR)
        print(f"Removed {BUILD_DIR} ({n} item(s)).")
    else:
        print(f"Nothing to clean - {BUILD_DIR} does not exist.")


if __name__ == "__main__":
    clean()
