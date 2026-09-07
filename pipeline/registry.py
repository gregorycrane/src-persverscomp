"""WORK_REGISTRY loader. Relocated from notebook Cell 1, unchanged.

Edit work_registry.json directly to add a work, fix a path, or relabel an
edition -- no need to touch/re-run any pipeline code.
"""
import json
from pipeline.config import SRC_DIR

WORK_REGISTRY_PATH = SRC_DIR / "work_registry.json"

with open(WORK_REGISTRY_PATH, encoding="utf-8") as f:
    WORK_REGISTRY = json.load(f)
