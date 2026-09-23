import json
from pathlib import Path

from pipeline.core.storage import init_storage_engine


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "work_registry.json"


def test_every_treebank_names_a_registered_edition():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    checked = 0
    for work_key, work in registry.items():
        editions = work.get("editions", {})
        for treebank_id, treebank in work.get("treebanks", {}).items():
            source_version = treebank.get("source_version")
            assert source_version in editions, (
                f"{work_key}.{treebank_id} does not name a registered source edition"
            )
            checked += 1
    assert checked > 0


def test_optional_provenance_links_name_registered_editions():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    checked = 0
    for work_key, work in registry.items():
        editions = work.get("editions", {})
        for category in ("translations", "commentaries", "appcrits", "scholia"):
            for resource_id, resource in work.get(category, {}).items():
                source_version = resource.get("source_version")
                if source_version is None:
                    continue
                assert source_version in editions, (
                    f"{work_key}.{resource_id} does not name a registered edition"
                )
                assert resource.get("source_certainty"), (
                    f"{work_key}.{resource_id} has a source without a certainty value"
                )
                checked += 1
    assert checked > 0


def test_commentary_translation_links_name_registered_resources():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    checked = 0
    for work_key, work in registry.items():
        registered = {
            resource_id
            for category in ("editions", "translations", "commentaries", "appcrits", "scholia")
            for resource_id in work.get(category, {})
        }
        for resource_id, resource in work.get("commentaries", {}).items():
            translation_of = resource.get("translation_of")
            if translation_of is None:
                continue
            assert translation_of in registered, (
                f"{work_key}.{resource_id} translates unknown resource {translation_of}"
            )
            checked += 1
    assert checked > 0


def test_text_units_can_store_optional_provenance(tmp_path):
    conn = init_storage_engine(tmp_path / "source-version.db")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(text_units)")}
    assert {"source_version", "source_certainty", "source_note", "translation_of"} <= columns
    conn.execute(
        "INSERT INTO text_units "
        "(canonical_id, urn, label, text_class, textgroup, work, short_id, "
        "doc_type, source_version, source_certainty, source_note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("translation", "urn:cts:greekLit:tlg1.tlg1.tr", "Translation",
         "english-text", "tlg1", "tlg1", "tr", "translation", "edition-1",
         "inferred_same_publication", "Matching creator and year."),
    )
    assert conn.execute(
        "SELECT source_version, source_certainty, source_note FROM text_units "
        "WHERE canonical_id='translation'"
    ).fetchone() == (
        "edition-1", "inferred_same_publication", "Matching creator and year."
    )
    conn.close()
