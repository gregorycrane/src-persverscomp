"""Per-work staleness tracking for incremental builds.

manifest.json lives in SRC_DIR (next to work_registry.json), NOT in
BUILD_DIR -- unlike the monolith, it must survive `make clean` and a fresh
clone, because it's what lets a rebuild after monolith reconstitution know
which works are already reflected in the shards vs. actually changed.
"""
import hashlib
import json
from pathlib import Path
from pipeline.config import SRC_DIR

MANIFEST_PATH = SRC_DIR / "manifest.json"
PIPELINE_VERSION = "v99"  # bump whenever shared parser/core code changes meaning


def _fingerprint(paths: list) -> str:
    h = hashlib.sha256()
    h.update(PIPELINE_VERSION.encode())
    for p in sorted(paths, key=str):
        p = Path(p)
        if p.exists():
            st = p.stat()
            h.update(f"{p}:{st.st_mtime_ns}:{st.st_size}".encode())
        else:
            h.update(f"{p}:MISSING".encode())
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def save_manifest(m: dict):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")


def is_stale(work_key: str, dep_paths: list, manifest: dict) -> bool:
    return manifest.get(work_key) != _fingerprint(dep_paths)


def record(work_key: str, dep_paths: list, manifest: dict) -> None:
    manifest[work_key] = _fingerprint(dep_paths)
