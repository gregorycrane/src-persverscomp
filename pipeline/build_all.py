"""Build orchestrator -- the `make` entry point. NEW module.

Flow: if the monolith is missing (fresh clone, or cleanup.py ran),
reconstitute it from the deployed shards first (no TEI re-parsing needed).
Then run the normal manifest-driven staleness pass: only works whose
declared source files (or the parser/core code that reads them) actually
changed get re-ingested. Sharding and index.html only get rebuilt if
something changed.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import DB_PATH, WORKSPACE_DIR
from pipeline.registry import WORK_REGISTRY, WORK_REGISTRY_PATH
from pipeline.manifest import load_manifest, save_manifest, is_stale, record
from pipeline.parsers import PARSE_MODE_PARSERS
from pipeline.treebank.conllu import parse_conllu_treebank
from pipeline.treebank.agdt import parse_agdt_treebank
from pipeline.ingest_work import ingest_works
from pipeline.core.storage import init_storage_engine
from pipeline.reconstitute import reconstitute_monolith
from pipeline import sharding, index_builder, experimental_collections

_CORE_DIR = Path(__file__).parent / "core"
_CORE_FILES = [_CORE_DIR / "xml_utils.py", _CORE_DIR / "storage.py",
               _CORE_DIR / "canonical_intervals.py", _CORE_DIR / "alignment.py"]

# Keyed by each treebank entry's own `parse_mode` (ingest_work.py's
# treebank dispatch, not the edition-level PARSE_MODE_PARSERS above).
_TREEBANK_PARSE_MODE_PARSERS = {
    "conllu": parse_conllu_treebank,
    "agdt_xml": parse_agdt_treebank,
}


def _quick_check(db_path: Path):
    """Return (healthy, diagnostic) without modifying the database."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
        diagnostic = row[0] if row else "PRAGMA quick_check returned no result"
        # SQLite can return hundreds of page errors in one string.  The first
        # line identifies the failure without flooding normal build output.
        display = diagnostic if diagnostic == "ok" else diagnostic.splitlines()[0]
        return diagnostic == "ok", display
    except sqlite3.DatabaseError as exc:
        return False, str(exc)


def _ensure_monolith(db_path: Path, shard_root: Path, *, index_only=False):
    """Ensure the build monolith exists and passes SQLite's quick check.

    The monolith is a disposable build artifact; published shards are its
    recovery source.  A damaged copy is retained with a timestamped name so
    diagnosis remains possible, and the replacement is built separately and
    installed atomically only after its own integrity check succeeds.
    """
    db_path = Path(db_path)
    shard_root = Path(shard_root)
    quarantine = None

    if db_path.exists():
        healthy, diagnostic = _quick_check(db_path)
        if healthy:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine = db_path.with_name(f"{db_path.stem}.malformed-{stamp}{db_path.suffix}")
        db_path.replace(quarantine)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db_path) + suffix)
            if sidecar.exists():
                sidecar.replace(Path(str(quarantine) + suffix))
        print(f"[monolith] integrity check failed: {diagnostic}")
        print(f"[monolith] retained damaged database as {quarantine}")

    shards_exist = shard_root.exists() and any(shard_root.rglob("*.db"))
    if shards_exist:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        rebuilding = db_path.with_name(f".{db_path.name}.rebuilding")
        rebuilding.unlink(missing_ok=True)
        try:
            conn = reconstitute_monolith(rebuilding, shard_root)
            row = conn.execute("PRAGMA quick_check").fetchone()
            conn.close()
            if not row or row[0] != "ok":
                raise sqlite3.DatabaseError(
                    row[0] if row else "reconstructed database returned no integrity result")
            rebuilding.replace(db_path)
            print(f"[monolith] installed verified reconstruction at {db_path}")
            return
        except Exception:
            rebuilding.unlink(missing_ok=True)
            if quarantine is not None and not db_path.exists():
                quarantine.replace(db_path)
            raise

    if quarantine is not None:
        quarantine.replace(db_path)
        raise SystemExit(
            f"The build monolith is malformed and no recovery shards exist under {shard_root}."
        )
    if index_only:
        raise SystemExit(
            "--index-only: no monolith and no shards found under "
            f"{shard_root} -- nothing to build index.html from. "
            "Run a normal `make` (or `make force`) at least once first."
        )
    print(f"[monolith] not present and no shards found under {shard_root} "
          f"-- initializing an empty monolith (every work is stale).")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_storage_engine(db_path).close()


def dep_paths_for(work_key: str, meta: dict) -> list:
    """Every file whose change should invalidate this work's manifest
    fingerprint: its own declared source files, the shared core modules,
    the registry itself (a hand-edited path/config fix should also trigger
    a rebuild) -- and, per edition/translation/commentary/treebank entry,
    whichever parser module ITS OWN `parse_mode` dispatches to (a work can
    mix several parse_modes across its entries; there is no single
    work-level "doc_type" to key off of -- see parsers/__init__.py's
    docstring for why the previous version of this function using
    meta.get("doc_type") never matched anything real).
    """
    paths = [WORK_REGISTRY_PATH, *_CORE_FILES]
    parser_files = set()

    def _add_path(value):
        # A treebank entry's `path` may be a single string or a list of
        # shard files (e.g. the Iliad conllu split into book ranges).
        for p in ([value] if isinstance(value, str) else value):
            paths.append(Path(p))

    for group in ("editions", "appcrits", "translations", "commentaries", "scholia", "metrics"):
        for entry in meta.get(group, {}).values():
            if "path" in entry:
                _add_path(entry["path"])
            parser_fn = PARSE_MODE_PARSERS.get(entry.get("parse_mode"))
            if parser_fn is not None:
                parser_files.add(Path(parser_fn.__globals__["__file__"]))
    # Fragment editions are published by experimental_collections rather than
    # the ordinary TEI parsers, but their shared source still participates in
    # manifest invalidation for every registered fragmentary play.
    for entry in meta.get("fragment_editions", {}).values():
        if "path" in entry:
            _add_path(entry["path"])
    for tb in meta.get("treebanks", {}).values():
        if "path" in tb:
            _add_path(tb["path"])
        tb_parser_fn = _TREEBANK_PARSE_MODE_PARSERS.get(tb.get("parse_mode"))
        if tb_parser_fn is not None:
            parser_files.add(Path(tb_parser_fn.__globals__["__file__"]))
    for aln in meta.get("alignments", {}).values():
        if "path" in aln:
            paths.append(Path(aln["path"]))
    for tsv in meta.get("edition_alignments", []):
        paths.append(Path(tsv))
    if meta.get("speakers_csv"):
        paths.append(Path(meta["speakers_csv"]))
    # A work's ToposText CSV is an input just like its TEI. Without this,
    # correcting or refreshing place data would leave the manifest green
    # and silently skip the map rebuild.
    from pipeline.places.topostext import (
        PLACE_REFERENCE_WORKS, TOPOTEXT_CSV_DIR, ingest_place_references,
    )
    for label, pair in PLACE_REFERENCE_WORKS.items():
        if work_key == f"{pair[0]}.{pair[1]}":
            paths.append(TOPOTEXT_CSV_DIR / f"citations_{label}.csv")
            paths.append(Path(ingest_place_references.__globals__["__file__"]))
    paths.extend(sorted(parser_files, key=str))
    return paths


def _resolve_targets(requested: list) -> list:
    """Map each --work argument to concrete registry keys. An exact
    work_key passes through; anything else is treated as a textgroup /
    prefix and expanded to every work_key that equals it or starts with
    it followed by a '.' (so 'tlg001' never sucks in 'tlg0012').
    Order is preserved and duplicates dropped. Unknown values abort.
    """
    all_keys = list(WORK_REGISTRY.keys())
    if not requested:
        return all_keys
    resolved, seen = [], set()
    for token in requested:
        if token in WORK_REGISTRY:
            matches = [token]
        else:
            matches = [k for k in all_keys
                       if k == token or k.startswith(token + ".")]
        if not matches:
            raise SystemExit(
                f"--work {token!r}: no matching work in the registry "
                f"(expected a work_key like 'tlg0012.tlg001' or a textgroup "
                f"prefix like 'tlg0012')."
            )
        for m in matches:
            if m not in seen:
                seen.add(m)
                resolved.append(m)
    return resolved


def main(argv=None):
    ap = argparse.ArgumentParser(description="Perseus Multitext Viewer build orchestrator")
    ap.add_argument("--work", action="append", dest="works",
                     help="only build this work (repeatable). Accepts a full "
                          "work_key (tlg0012.tlg001), or a textgroup / prefix "
                          "(tlg0012) which expands to every matching work_key "
                          "(tlg0012.tlg001, tlg0012.tlg002, ...).")
    ap.add_argument("--force", action="store_true",
                     help="ignore the manifest, rebuild every targeted work")
    ap.add_argument("--skip-index", action="store_true",
                     help="rebuild shards but don't regenerate index.html")
    ap.add_argument("--index-only", action="store_true",
                     help="skip ingestion entirely -- just rebuild index.html from "
                          "the existing monolith + web/. Use this after editing "
                          "web/app.js, web/styles.css, or web/index_shell.html: "
                          "none of those are TEI source files, so no work is ever "
                          "'stale' from a plain make, and `make force` would only "
                          "pick the change up by wastefully re-ingesting everything.")
    args = ap.parse_args(argv)

    shard_root = WORKSPACE_DIR / "site" / "data"
    _ensure_monolith(DB_PATH, shard_root, index_only=args.index_only)

    if args.index_only:
        experimental_collections.publish()
        conn = sqlite3.connect(str(DB_PATH))
        index_builder.rebuild(conn)
        conn.close()
        print("\nindex.html rebuilt from the existing monolith + web/ (no ingestion).")
        return

    manifest = {} if args.force else load_manifest()
    target_keys = _resolve_targets(args.works)

    conn = sqlite3.connect(str(DB_PATH))
    changed = []
    for work_key in target_keys:
        meta = WORK_REGISTRY[work_key]
        deps = dep_paths_for(work_key, meta)
        if args.force or is_stale(work_key, deps, manifest):
            print(f"[build] {work_key} -- stale, ingesting")
            ingest_works(conn, work_keys=[work_key])
            record(work_key, deps, manifest)
            changed.append(work_key)
        else:
            print(f"[skip]  {work_key} -- unchanged")
    conn.close()

    if changed:
        sharding.split_corpus_by_work(
            str(DB_PATH), str(WORKSPACE_DIR / "site"), only_work_keys=changed)

        experimental_collections.publish()

        # Special case (not a general lexicon pipeline): the Orlando Furioso
        # Italian glossary. Ingest just that lexicon into the monolith and
        # shard only its .db, merging into the existing lexica.json.
        if "ariosto.orlandofurioso" in changed:
            from pipeline.lexicon.ingest import ingest_lexica
            from pipeline.lexicon.shard import shard_lexica
            conn = sqlite3.connect(str(DB_PATH))
            ingest_lexica(conn, lexicon_ids=["orlando-furioso-ita"])
            conn.close()
            shard_lexica(DB_PATH, WORKSPACE_DIR / "site" / "data" / "lexica",
                         WORKSPACE_DIR / "site", only_shard_files=["lexica_ariosto.db"])

        if not args.skip_index:
            conn = sqlite3.connect(str(DB_PATH))
            index_builder.rebuild(conn)
            conn.close()

    save_manifest(manifest)
    print(f"\n{len(changed)}/{len(target_keys)} work(s) rebuilt.")


if __name__ == "__main__":
    main()
