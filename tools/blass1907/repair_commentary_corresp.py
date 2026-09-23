#!/usr/bin/env python3
"""Audit and repair displaced Blass Eumenides commentary anchors.

The commentary's @n is Blass's line range.  The companion Blass Greek edition
maps those line numbers to the Smyth reference text with l/@corresp.  This
script reports gross disagreements and can repair the small set of verified
bad anchors without reserializing the XML.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from lxml import etree

TEI = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
URN_PREFIX = "urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:"

# These seven blocks were checked against both their commentary text and the
# line mapping in tlg0085.tlg007.blass1907-grc1.xml.
FIXES = {
    "blass-note-72": ("299-306", "299"),
    "blass-pass4-cont-28": ("299-306", "299-cont2"),
    "blass-pass4-cont-29": ("299-306", "299-cont3"),
    "blass-pass4-cont-30": ("299-306", "299-cont4"),
    "blass-note-78": ("334-346", "334"),
    "blass-note-84": ("377-380", "377"),
    "blass-note-112": ("566-573", "566"),
}


def first_number(value: str) -> int | None:
    match = re.match(r"\s*(\d+)", value or "")
    return int(match.group(1)) if match else None


def line_map(greek_path: Path) -> dict[str, str]:
    tree = etree.parse(str(greek_path))
    result = {}
    for line in tree.xpath("//tei:l[@n][@corresp]", namespaces=TEI):
        result[line.get("n")] = line.get("corresp").rsplit(":", 1)[-1]
    return result


def audit(path: Path, mapping: dict[str, str], tolerance: int = 5) -> list[str]:
    tree = etree.parse(str(path))
    errors = []
    for div in tree.xpath("//tei:div[@subtype='commline'][@n][@corresp]", namespaces=TEI):
        native_start = re.match(r"(\d+)", div.get("n", ""))
        if not native_start:
            continue
        expected = mapping.get(native_start.group(1))
        if not expected:
            continue
        actual = div.get("corresp", "").rsplit(":", 1)[-1]
        expected_num = first_number(expected)
        actual_num = first_number(actual)
        if (
            expected_num is not None
            and actual_num is not None
            and abs(expected_num - actual_num) > tolerance
        ):
            errors.append(
                f"{div.get(XML_ID)}: Blass {div.get('n')} maps to Smyth "
                f"{expected}, but @corresp is {actual}"
            )
    return errors


def repair(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    changed = 0
    for xml_id, (passage, milestone) in FIXES.items():
        div_re = re.compile(
            r'(<div\b(?=[^>]*\bxml:id="' + re.escape(xml_id) + r'")[^>]*\bcorresp=")'
            + re.escape(URN_PREFIX)
            + r'[^"]+(".*?>)(.*?)(</div>)',
            re.DOTALL,
        )
        match = div_re.search(text)
        if not match:
            raise RuntimeError(f"{path.name}: missing {xml_id}")
        block = match.group(0)
        fixed = div_re.sub(
            lambda m: m.group(1) + URN_PREFIX + passage + m.group(2) + m.group(3) + m.group(4),
            block,
            count=1,
        )
        fixed, count = re.subn(
            r'(<milestone\b[^>]*\bn=")[^"]+("[^>]*/>)',
            rf"\g<1>{milestone}\2",
            fixed,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"{path.name}: missing milestone in {xml_id}")
        if fixed != block:
            text = text[: match.start()] + fixed + text[match.end() :]
            changed += 1
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    directory = args.directory
    greek = directory / "tlg0085.tlg007.blass1907-grc1.xml"
    mapping = line_map(greek)
    files = sorted(directory.glob("tlg0085.tlg007.blass1907-com-deu1*.xml"))
    if not files:
        raise SystemExit("No Blass commentary XML files found")

    if args.apply:
        for path in files:
            print(f"{path.name}: repaired {repair(path)} verified anchors")

    problems = 0
    for path in files:
        errors = audit(path, mapping)
        problems += len(errors)
        print(f"{path.name}: {len(errors)} gross anchor mismatch(es)")
        for error in errors:
            print(f"  {error}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
