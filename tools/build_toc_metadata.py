#!/usr/bin/env python3
"""Build compact, edition-aware metadata for the PMV table of contents.

The reader catalog deliberately stays focused on routing and version metadata.
This companion file records the information needed only by the contents page:
word counts for complete works and, for fragmentary works, the native fragment
numbers and word count of every edition.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


WORD_RE = re.compile(r"[^\W\d_]+(?:[’'][^\W\d_]+)*", re.UNICODE)
COLLECTION_METADATA = {
    # Collection chronology and source-edition bibliography are deliberately
    # separate. The encoded Dindorf text comes from the eighth edition of
    # 1893, but the collection itself was first published in 1830 and
    # therefore precedes Nauck's collection.
    "dindorf": {
        "collection_year": 1830,
        "collection_order": 1,
        "source_edition_number": 8,
        "source_edition_year": 1893,
        "source_edition_statement": "8th ed., 1893",
    },
    "nauck": {
        "collection_year": 1889,
        "collection_order": 2,
        "source_edition_year": 1889,
        "source_edition_statement": "1889 ed.",
    },
    "pearson": {
        "collection_year": 1917,
        "collection_order": 3,
        "source_edition_year": 1917,
        "source_edition_statement": "1917 ed.",
    },
}
EXTANT_DRAMA = {
    *(f"tlg0085.tlg{i:03d}" for i in range(1, 8)),
    *(f"tlg0011.tlg{i:03d}" for i in range(1, 8)),
    *(f"tlg0006.tlg{i:03d}" for i in range(1, 20)),
    *(f"tlg0019.tlg{i:03d}" for i in range(1, 12)),
}


class VisibleText(HTMLParser):
    """Extract text while excluding line numbers, notes, and apparatus."""

    ignored_classes = {
        "line-num-cell",
        "note",
        "tei-note",
        "apparatus",
        "appcrit",
        "speaker",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[bool, bool]] = []
        self.all_text: list[str] = []
        self.line_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())
        parent_ignored = self.stack[-1][0] if self.stack else False
        parent_line = self.stack[-1][1] if self.stack else False
        ignored = parent_ignored or bool(classes & self.ignored_classes)
        in_line = parent_line or "line-text-cell" in classes
        self.stack.append((ignored, in_line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        ignored, in_line = self.stack[-1] if self.stack else (False, False)
        if ignored:
            return
        self.all_text.append(data)
        if in_line:
            self.line_text.append(data)

    def text(self) -> str:
        # Verse/drama segments often repeat a speaker label outside the line
        # grid. Counting only line cells avoids treating that label as text.
        return " ".join(self.line_text or self.all_text)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def count_html(html: str) -> int:
    parser = VisibleText()
    parser.feed(html)
    return count_words(parser.text())


def edition_name(short_id: str, label: str = "") -> str:
    known = {
        "dindorf": "Dindorf",
        "nauck": "Nauck",
        "pearson": "Pearson",
        "jebb": "Jebb",
    }
    lowered = short_id.lower()
    for prefix, name in known.items():
        if lowered.startswith(prefix):
            return name
    match = re.search(r"\(([^,;)]+)", label)
    return match.group(1).strip() if match else short_id


def collection_metadata(short_id: str) -> dict:
    lowered = short_id.lower()
    for prefix, metadata in COLLECTION_METADATA.items():
        if lowered.startswith(prefix):
            return metadata.copy()
    return {}


def natural_fragment_key(value: str) -> tuple:
    pieces = re.split(r"(\d+)", str(value))
    return tuple(int(piece) if piece.isdigit() else piece.casefold() for piece in pieces)


def fragment_metadata(site: Path) -> tuple[dict, dict]:
    works: dict[str, dict] = {}
    authors: dict[str, dict] = {}
    for path in sorted(site.glob("*-fragment-collections.json")):
        # fragment-collections.json is the historical alias of the tlg0085 file.
        if path.name == "fragment-collections.json":
            continue
        collection = json.loads(path.read_text(encoding="utf-8"))
        textgroup = collection.get("textgroup")
        if not textgroup:
            continue
        versions = {
            version.get("short_id", ""): version
            for version in collection.get("versions", [])
        }
        author_editions: dict[str, dict] = {}
        play_count = 0
        evidence_only = 0
        for work in collection.get("works", {}).values():
            play_count += 1
            if not work.get("fragments"):
                evidence_only += 1
            grouped: dict[str, list[dict]] = {}
            for fragment in work.get("fragments", []):
                grouped.setdefault(fragment.get("edition", "unknown"), []).append(fragment)
            edition_rows = []
            for short_id, fragments in grouped.items():
                version = versions.get(short_id, {})
                numbers = sorted(
                    {str(fragment.get("number", "")) for fragment in fragments if fragment.get("number") is not None},
                    key=natural_fragment_key,
                )
                words = sum(
                    count_words(line.get("text", ""))
                    for fragment in fragments
                    for line in fragment.get("lines", [])
                )
                row = {
                    "short_id": short_id,
                    "edition": edition_name(short_id, version.get("label", "")),
                    "numbers": numbers,
                    "fragment_count": len(fragments),
                    "word_count": words,
                }
                row.update(collection_metadata(short_id))
                edition_rows.append(row)
                summary = author_editions.setdefault(
                    short_id,
                    {
                        "short_id": short_id,
                        "edition": row["edition"],
                        "fragment_count": 0,
                        "word_count": 0,
                    },
                )
                summary.update(collection_metadata(short_id))
                summary["fragment_count"] += len(fragments)
                summary["word_count"] += words
            work_key = f"{textgroup}.{work.get('work')}"
            works[work_key] = {
                "record_type": "fragmentary_play",
                "editions": edition_rows,
                "evidence_only": not bool(work.get("fragments")),
            }
        authors[textgroup] = {
            "author": collection.get("author", textgroup),
            "fragmentary_play_count": play_count,
            "evidence_only_play_count": evidence_only,
            "editions": list(author_editions.values()),
        }
    return works, authors


def has_table(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def count_version_in_parts(site: Path, work: dict, version: dict) -> tuple[int, str]:
    version_id = version.get("short_id", "")
    treebanks = [
        candidate
        for candidate in work.get("versions", [])
        if candidate.get("doc_type") == "treebank"
        and candidate.get("source_version") == version_id
    ]
    treebank_count = 0
    html_count = 0
    saw_treebank = False
    for part in work.get("parts", []):
        db_path = site / "data" / work["textgroup"] / work["work"] / part["file"]
        if not db_path.exists():
            continue
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            if treebanks and has_table(connection, "treebank_tokens"):
                for treebank in treebanks:
                    rows = connection.execute(
                        "SELECT form, upos FROM treebank_tokens WHERE version_short_id=?",
                        (treebank.get("short_id"),),
                    )
                    for form, upos in rows:
                        saw_treebank = True
                        if upos != "PUNCT" and form and any(char.isalpha() for char in form):
                            treebank_count += 1
            if not saw_treebank and has_table(connection, "text_segments"):
                rows = connection.execute(
                    "SELECT content_html FROM text_segments WHERE version_short_id=?",
                    (version_id,),
                )
                html_count += sum(count_html(row[0]) for row in rows)
        finally:
            connection.close()
    if saw_treebank:
        return treebank_count, "treebank tokens excluding punctuation"
    return html_count, "visible text"


def complete_work_metadata(site: Path, catalog: dict) -> tuple[dict, dict]:
    works: dict[str, dict] = {}
    surviving_by_author: dict[str, int] = {}
    for work_key, work in catalog.get("works", {}).items():
        if work.get("experimental_fragment"):
            continue
        editions = [
            version
            for version in work.get("versions", [])
            if version.get("doc_type") == "edition"
        ]
        if not editions:
            editions = [
                version
                for version in work.get("versions", [])
                if version.get("doc_type") == "translation"
            ]
        result = None
        for edition in editions:
            count, method = count_version_in_parts(site, work, edition)
            if count:
                result = {
                    "record_type": "complete_work",
                    "surviving_play": work_key in EXTANT_DRAMA,
                    "word_count": count,
                    "counted_version": edition.get("short_id"),
                    "counted_edition": edition_name(
                        edition.get("short_id", ""), edition.get("label", "")
                    ),
                    "count_method": method,
                }
                break
        if result:
            works[work_key] = result
        if work_key in EXTANT_DRAMA:
            textgroup = work.get("textgroup")
            surviving_by_author[textgroup] = surviving_by_author.get(textgroup, 0) + 1
    return works, surviving_by_author


def build(site: Path, output: Optional[Path] = None) -> dict:
    """Build TOC metadata for an already-published PMV site."""
    site = site.resolve()
    output = output or site / "toc-metadata.json"
    catalog = json.loads((site / "catalog.json").read_text(encoding="utf-8"))
    fragment_works, authors = fragment_metadata(site)
    complete_works, surviving = complete_work_metadata(site, catalog)
    for textgroup, count in surviving.items():
        authors.setdefault(
            textgroup,
            {
                "author": catalog.get("authors", {}).get(textgroup, textgroup),
                "fragmentary_play_count": 0,
                "evidence_only_play_count": 0,
                "editions": [],
            },
        )["surviving_play_count"] = count
    payload = {
        "schema_version": 1,
        "counting_note": (
            "Complete-work counts use the first available text version, preferring source-edition treebank "
            "tokens with punctuation excluded. Fragment counts include quoted authorial text only; "
            "transmitting sources, notes, and punctuation-only tokens are excluded."
        ),
        "authors": authors,
        "works": {**complete_works, **fragment_works},
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}: {len(payload['works'])} works, {len(authors)} fragment authors")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.site is None:
        from pipeline.config import WORKSPACE_DIR

        args.site = WORKSPACE_DIR / "site"
    build(args.site, args.output)


if __name__ == "__main__":
    main()
