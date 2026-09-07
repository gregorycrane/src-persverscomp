"""Shared path/config constants. Relocated from notebook Cell 0, unchanged."""
import os
import json
import re
import sqlite3
from pathlib import Path
from collections import OrderedDict
import xml.etree.ElementTree as ET
try:
    import lxml.etree as LET
    _LXML = True
except ImportError:
    _LXML = False

WORKSPACE_DIR = Path("/Users/gcrane/github/persverscomp")
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Build-only SOURCE repo -- notebooks, registries, and any config that
# reveals local disk layout (absolute paths into canonical-greekLit etc.)
# live here, never under WORKSPACE_DIR. WORKSPACE_DIR is persverscomp itself,
# which is what gets pushed to GitHub Pages -- nothing in it should expose
# /Users/gcrane/... paths from this machine.
SRC_DIR = Path("/Users/gcrane/github/src-persverscomp")
SRC_DIR.mkdir(parents=True, exist_ok=True)

# Build-only monolith DB. It lives OUTSIDE the repo (in a temp dir) so it can
# never be staged or pushed to GitHub. It is a regenerable build artifact:
# ingest_work.py writes to it, sharding.py shards it into site/data/**, and
# index_builder.py reads it to build index.html. If it's missing (fresh
# clone, or cleanup.py ran), reconstitute.py rebuilds it FROM the shards
# without needing to re-parse any TEI/treebank source files.
BUILD_DIR = Path("/tmp/persvers_build")
BUILD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BUILD_DIR / "corpus_alignment_grid.db"
NS = {'tei': 'http://www.tei-c.org/ns/1.0'}
