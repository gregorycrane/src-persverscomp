#!/usr/bin/env python3
"""Move registry-declared fragment works into the grcnewfragments repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


RESOURCE_GROUPS = (
    "editions", "fragment_editions", "appcrits", "translations",
    "commentaries", "scholia", "treebanks", "metrics",
)


def is_fragment_record(record: dict) -> bool:
    return bool(record.get("fragmentary") or
                str(record.get("record_type", "")).startswith("fragment_"))


def iter_paths(record: dict):
    for group in RESOURCE_GROUPS:
        for resource in record.get(group, {}).values():
            value = resource.get("path")
            if isinstance(value, str):
                yield value
            elif isinstance(value, list):
                yield from (item for item in value if isinstance(item, str))


def work_root(source_file: Path, source_data: Path) -> Path:
    """Return the nearest CTS work directory containing __cts__.xml."""
    textgroup = source_data / source_file.relative_to(source_data).parts[0]
    current = source_file.parent
    while current != textgroup:
        if (current / "__cts__.xml").exists():
            return current
        current = current.parent
    raise ValueError(f"No work-level __cts__.xml found above {source_file}")


def replace_paths(value, old_root: str, new_root: str, moved_roots: set[Path]):
    if isinstance(value, dict):
        return {key: replace_paths(item, old_root, new_root, moved_roots)
                for key, item in value.items()}
    if isinstance(value, list):
        return [replace_paths(item, old_root, new_root, moved_roots) for item in value]
    if isinstance(value, str) and value.startswith(old_root + "/"):
        candidate = Path(value)
        if any(candidate == root or root in candidate.parents for root in moved_roots):
            return new_root + value[len(old_root):]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("source_repo", type=Path)
    parser.add_argument("destination_repo", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    source_data = args.source_repo / "data"
    destination_data = args.destination_repo / "data"
    source_root = str(args.source_repo.resolve())
    destination_root = str(args.destination_repo.resolve())

    declared = set()
    for record in registry.values():
        if not is_fragment_record(record):
            continue
        for value in iter_paths(record):
            if value.startswith(source_root + "/"):
                declared.add(Path(value))

    missing = sorted(str(path) for path in declared if not path.exists())
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} registry-declared fragment paths are missing; first: {missing[0]}")

    roots = sorted({work_root(path, source_data) for path in declared})
    collisions = []
    for root in roots:
        target = destination_data / root.relative_to(source_data)
        if target.exists():
            collisions.append(str(target))
    if collisions:
        raise FileExistsError(
            f"{len(collisions)} destination work directories already exist; first: {collisions[0]}")

    report = {
        "fragment_records": sum(is_fragment_record(r) for r in registry.values()),
        "declared_source_files": len(declared),
        "work_directories": len(roots),
        "textgroups": sorted({root.relative_to(source_data).parts[0] for root in roots}),
        "moves": [{"from": str(root),
                   "to": str(destination_data / root.relative_to(source_data))}
                  for root in roots],
        "applied": args.apply,
    }

    if args.apply:
        destination_data.mkdir(parents=True, exist_ok=True)
        textgroups = sorted({root.relative_to(source_data).parts[0] for root in roots})
        for root in roots:
            target = destination_data / root.relative_to(source_data)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root), str(target))

        copied_metadata, moved_metadata = [], []
        for textgroup_name in textgroups:
            source_group = source_data / textgroup_name
            target_group = destination_data / textgroup_name
            source_metadata = source_group / "__cts__.xml"
            target_metadata = target_group / "__cts__.xml"
            if not source_metadata.exists():
                raise FileNotFoundError(f"Missing textgroup metadata: {source_metadata}")
            target_group.mkdir(parents=True, exist_ok=True)
            remaining = [path for path in source_group.rglob("*")
                         if path.is_file() and path != source_metadata]
            if remaining:
                shutil.copy2(source_metadata, target_metadata)
                copied_metadata.append(textgroup_name)
            else:
                shutil.move(str(source_metadata), str(target_metadata))
                moved_metadata.append(textgroup_name)
                for directory in sorted(
                        (p for p in source_group.rglob("*") if p.is_dir()),
                        key=lambda p: len(p.parts), reverse=True):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
                try:
                    source_group.rmdir()
                except OSError:
                    pass

        updated = replace_paths(registry, source_root, destination_root, set(roots))
        args.registry.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["copied_textgroup_metadata"] = copied_metadata
        report["moved_textgroup_metadata"] = moved_metadata

        unresolved = []
        for key, record in updated.items():
            for value in iter_paths(record):
                if value.startswith(destination_root + "/") and not Path(value).exists():
                    unresolved.append({"record": key, "path": value})
        if unresolved:
            raise FileNotFoundError(
                f"{len(unresolved)} updated registry paths are missing; first: {unresolved[0]}")
        report["updated_paths_verified"] = True

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "fragment_records": report["fragment_records"],
        "work_directories": report["work_directories"],
        "textgroups": len(report["textgroups"]),
        "applied": report["applied"],
    }))


if __name__ == "__main__":
    main()
