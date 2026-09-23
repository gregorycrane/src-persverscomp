#!/usr/bin/env python3
"""Convert a CHS Primary Sources dramatic translation from HTML to CTS TEI.

The CHS pages use bold line numbers (normally every fifth line), italicized
transliterated Greek, and bold speaker names.  Some dialogue passages instead
print every line number as plain text.  This converter preserves those signals,
uses a canonical TEI edition to recover speech-opening line numbers, and emits
a companion JSON concordance of the marked Greek terms.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import copy
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI}


SPEAKER_MAP = {
    "pythia": "Πυθιάς",
    "apollo": "Ἀπόλλων",
    "orestes": "Ὀρέστης",
    "ghost of clytemnestra": "Κλυταιμήστρας Εἴδωλον",
    "chorus": "Χορός",
    "athena": "Ἀθηνᾶ",
    "chorus of the processional escort": "Προπομποί",
}


def q(local: str) -> str:
    return f"{{{TEI}}}{local}"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or " ")


def norm_term(value: str) -> str:
    value = unicodedata.normalize("NFC", clean(value).strip())
    return value.casefold().strip(" .,:;!?[](){}\"“”‘’")


def download(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Perseus-MVP-CHS-import/1.0"})
    with urlopen(req, timeout=60) as response:
        return response.read()


def canonical_speeches(path: Path) -> list[dict[str, str]]:
    tree = etree.parse(str(path))
    out = []
    for sp in tree.xpath("//tei:sp[.//tei:l[@n]]", namespaces=NS):
        speaker = clean("".join(sp.xpath("./tei:speaker//text()", namespaces=NS))).strip()
        lines = sp.xpath(".//tei:l/@n", namespaces=NS)
        out.append({"speaker": speaker, "start": lines[0], "end": lines[-1]})
    return out


def is_line_strong(node: Tag) -> bool:
    text = node.get_text(" ", strip=True)
    return (
        node.name == "strong"
        and text.isdigit()
        and node.find_parent("small") is None
        and node.find_parent("a") is None
    )


def speaker_from(node: Tag) -> str | None:
    for strong in node.find_all("strong", recursive=False):
        text = clean(strong.get_text(" ", strip=True)).strip()
        if text and not text.isdigit():
            return text
    return None


def is_lyric_label(text: str) -> bool:
    return bool(re.fullmatch(r"(?:anti)?strophe\s+\d+|anapests?", text.strip(), re.I))


def iter_events(content: Tag):
    """Yield speaker/head/stage/content events before the Notes section."""
    children = [x for x in content.children if isinstance(x, Tag)]
    # h1 and the credits paragraph precede the actual play.
    for child in children:
        text = clean(child.get_text(" ", strip=True)).strip()
        if child.name == "h1" or text.startswith("By Aeschylus Translated by"):
            continue
        if text == "Notes" or (child.get("class") == ["Paragraph"] and text == "Notes"):
            break
        if child.name in {"hr", "br"} or not text:
            continue

        if child.name == "div" and child.get("align") == "right" and is_lyric_label(text):
            yield "head", text, child
            continue

        if child.name == "div" and "Paragraph" in (child.get("class") or []):
            pending_inline = []
            for item in child.children:
                if isinstance(item, NavigableString):
                    if item.strip():
                        pending_inline.append(item)
                    continue
                if not isinstance(item, Tag):
                    continue
                if item.name == "strong" and not is_line_strong(item):
                    if pending_inline:
                        wrapper = BeautifulSoup("<p></p>", "html.parser").p
                        for part in pending_inline:
                            wrapper.append(copy(part))
                        yield "content", None, wrapper
                        pending_inline = []
                    yield "speaker", clean(item.get_text(" ", strip=True)).strip(), item
                elif item.name == "div" and item.get("align") == "right":
                    if pending_inline:
                        wrapper = BeautifulSoup("<p></p>", "html.parser").p
                        for part in pending_inline:
                            wrapper.append(copy(part))
                        yield "content", None, wrapper
                        pending_inline = []
                    yield "head", clean(item.get_text(" ", strip=True)).strip(), item
                elif item.name == "p":
                    if pending_inline:
                        wrapper = BeautifulSoup("<p></p>", "html.parser").p
                        for part in pending_inline:
                            wrapper.append(copy(part))
                        yield "content", None, wrapper
                        pending_inline = []
                    yield "content", None, item
                elif item.name not in {"br", "a"} or item.get_text(strip=True):
                    pending_inline.append(item)
            if pending_inline:
                wrapper = BeautifulSoup("<p></p>", "html.parser").p
                for part in pending_inline:
                    wrapper.append(copy(part))
                yield "content", None, wrapper
            continue

        if child.name == "p":
            spk = speaker_from(child)
            # A paragraph consisting solely of an italic direction is a stage event.
            meaningful = [x for x in child.children if not (isinstance(x, NavigableString) and not x.strip())]
            if len(meaningful) == 1 and isinstance(meaningful[0], Tag) and meaningful[0].name == "em":
                if is_lyric_label(text):
                    yield "head", text, child
                else:
                    yield "stage", text, child
                continue
            if spk:
                yield "speaker", spk, child
                clone = BeautifulSoup(str(child), "html.parser").p
                first = next((x for x in clone.find_all("strong", recursive=False)
                              if not is_line_strong(x)), None)
                if first:
                    first.extract()
                if clone.get_text(" ", strip=True):
                    yield "content", None, clone
            elif text:
                yield "content", None, child
            continue


def tokens_for(node: Tag):
    """Turn one source block into text/term/line/note tokens."""
    def walk(item):
        if isinstance(item, Comment):
            return
        if isinstance(item, NavigableString):
            value = str(item)
            pos = 0
            # A few dense exchanges print every source line number as plain text.
            for match in re.finditer(r"(?<![\w])([1-9]\d{2,3})(?=\s)", value):
                n = int(match.group(1))
                if n > 1047:
                    continue
                if match.start() > pos:
                    yield "text", value[pos:match.start()]
                yield "line", str(n)
                pos = match.end()
            if pos < len(value):
                yield "text", value[pos:]
            return
        if not isinstance(item, Tag):
            return
        if is_line_strong(item):
            yield "line", item.get_text(strip=True)
            return
        if item.name == "small":
            sub = item.find("sub")
            if sub and sub.get_text(strip=True).isdigit():
                yield "line", sub.get_text(strip=True)
                return
            link = item.find("a", href=re.compile(r"^#fn\d+$"))
            if link:
                yield "note", re.sub(r"\D", "", link.get_text())
            return
        if item.name == "a" and not item.get_text(strip=True):
            return
        if item.name == "em":
            emphasized = clean(item.get_text(" ", strip=True)).strip()
            parent_text = clean(item.parent.get_text(" ", strip=True)).strip()
            is_direction = (
                emphasized in {"Muttering", "Moaning", "Sharp moaning twice"}
                or emphasized.startswith(("To ", "Turning ", "She ", "He ", "They ",
                                           "The Chorus ", "Enter ", "Exit "))
                or (parent_text.startswith("(") and parent_text.endswith(")"))
            )
            yield ("stage-inline" if is_direction else "term"), emphasized
            return
        if item.name == "br":
            yield "break", None
            return
        for child in item.children:
            yield from walk(child)

    yield from walk(node)


def append_text(parent, value: str):
    value = clean(value)
    if not value.strip():
        return
    if len(parent):
        previous = parent[-1]
        prior = (previous.tail or "") or (previous.text or "")
        if prior and prior[-1:].isalnum() and value[:1].isalnum():
            value = " " + value
        previous.tail = (previous.tail or "") + value
    else:
        parent.text = (parent.text or "") + value


def local_gloss_context(prefix: str) -> str | None:
    """Return the short English phrase immediately before ``[term]``."""
    if not re.search(r"\[\s*$", prefix):
        return None
    value = re.sub(r"\[\s*$", "", prefix).strip()
    value = re.split(r"[.;:!?—]", value)[-1].strip()
    words = value.split()
    if not words:
        return None
    value = " ".join(words[-4:])
    value = re.sub(r"^(?:a|an|the|to|of|for|with|in|on|by|from)\s+", "", value, flags=re.I)
    return value or None


def local_gloss(prefix: str) -> str | None:
    """Return a conservative one-word gloss from the bracket context."""
    context = local_gloss_context(prefix)
    if not context:
        return None
    match = re.search(r"([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ’'\-]*)\W*$", context)
    return match.group(1) if match else context


def convert(html: bytes, canonical: Path, source_url: str, urn: str):
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("article .contentMain") or soup.select_one(".contentMain")
    if content is None:
        raise ValueError("CHS .contentMain was not found")
    speeches = canonical_speeches(canonical)
    speech_cursor = -1

    root = etree.Element(q("TEI"), nsmap={None: TEI})
    header = etree.SubElement(root, q("teiHeader"))
    file_desc = etree.SubElement(header, q("fileDesc"))
    title_stmt = etree.SubElement(file_desc, q("titleStmt"))
    etree.SubElement(title_stmt, q("title")).text = "Eumenides"
    etree.SubElement(title_stmt, q("author")).text = "Aeschylus"
    for name, role in [("Herbert Weir Smyth", "translator"),
                       ("Cynthia Bannon", "reviser"),
                       ("Gregory Nagy", "reviser")]:
        el = etree.SubElement(title_stmt, q("editor"), role=role)
        el.text = name
    resp = etree.SubElement(title_stmt, q("respStmt"))
    etree.SubElement(resp, q("resp")).text = "HTML-to-TEI conversion and term tagging"
    etree.SubElement(resp, q("name")).text = "Perseus MVP"
    pub = etree.SubElement(file_desc, q("publicationStmt"))
    etree.SubElement(pub, q("publisher")).text = "Center for Hellenic Studies"
    etree.SubElement(pub, q("availability")).append(
        etree.Element(q("p")))
    pub.find(q("availability"))[0].text = "Converted from the CHS Primary Sources publication."
    source = etree.SubElement(file_desc, q("sourceDesc"))
    bibl = etree.SubElement(source, q("bibl"))
    bibl.text = "Aeschylus, Eumenides, translated by Herbert Weir Smyth, revised by Cynthia Bannon, further revised by Gregory Nagy."
    ref = etree.SubElement(source, q("ref"), target=source_url)
    ref.text = "CHS source page"
    encoding = etree.SubElement(header, q("encodingDesc"))
    etree.SubElement(encoding, q("p")).text = (
        "Italicized transliterated Greek in the source HTML is encoded as term @xml:lang='grc-Latn'. "
        "Line divisions follow the printed Smyth line markers and speech openings are aligned to perseus-grc2."
    )
    profile = etree.SubElement(header, q("profileDesc"))
    langs = etree.SubElement(profile, q("langUsage"))
    etree.SubElement(langs, q("language"), ident="eng").text = "English"
    etree.SubElement(langs, q("language"), ident="grc-Latn").text = "Ancient Greek transliterated into Latin script"
    rev = etree.SubElement(header, q("revisionDesc"))
    etree.SubElement(rev, q("change"), when="2026-09-21").text = "Converted from CHS HTML for Perseus MVP."

    text = etree.SubElement(root, q("text"), {f"{{{XML}}}lang": "eng"})
    body = etree.SubElement(text, q("body"), {f"{{{XML}}}base": urn})
    div = etree.SubElement(body, q("div"), type="translation", n=urn)

    terms = defaultdict(lambda: {"forms": Counter(), "occurrences": []})
    footnote_refs = set()
    current_speaker = None
    current_sp = None
    current_line = None
    pending_start = "1"
    pending_boundary = True
    seen_markers = set()
    last_source_marker = None
    lyric_mode = False
    lyric_block_count = 0

    def next_speech(display: str):
        nonlocal speech_cursor
        target = SPEAKER_MAP.get(display.casefold())
        if not target:
            return None
        for idx in range(speech_cursor + 1, len(speeches)):
            start_digits = re.match(r"\d+", speeches[idx]["start"] or "")
            start_number = int(start_digits.group()) if start_digits else None
            after_marker = (
                last_source_marker is None
                or start_number is None
                or start_number >= last_source_marker
            )
            if speeches[idx]["speaker"] == target and after_marker:
                speech_cursor = idx
                return speeches[idx]
        return None

    def open_speech(display: str, force_advance=True):
        nonlocal current_speaker, current_sp, current_line, pending_start, pending_boundary
        current_speaker = display
        speech = next_speech(display) if force_advance else None
        pending_start = speech["start"] if speech else pending_start
        current_sp = etree.SubElement(div, q("sp"))
        etree.SubElement(current_sp, q("speaker")).text = display
        current_line = None
        pending_boundary = False

    def ensure_line(number: str | None = None):
        nonlocal current_sp, current_line, pending_start, pending_boundary
        if current_sp is None:
            open_speech(current_speaker or "Narrative", force_advance=pending_boundary)
        n = number or pending_start or "1"
        if current_line is None or current_line.get("n") != n:
            current_line = etree.SubElement(current_sp, q("l"), n=n,
                corresp=f"urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:{n}")
        pending_start = n
        return current_line

    for kind, value, node in iter_events(content):
        if kind == "speaker":
            lyric_mode = False
            lyric_block_count = 0
            open_speech(value)
            continue
        if kind == "stage":
            major_break = bool(re.search(
                r"\b(?:enters?|exits?|disappears?|returns?)\b|scene changes",
                value.casefold(),
            ))
            stage_parent = div if major_break or current_line is None else current_line
            stage = etree.SubElement(stage_parent, q("stage"))
            stage.text = value
            # Only this direction interrupts one unlabelled Pythia speech and
            # begins another. Most directions ("To Athena", "Turning to the
            # judges", entrances, exits) sit within or between explicitly
            # labelled speeches and must not advance the canonical sequence.
            if major_break:
                current_sp = None
                current_line = None
                pending_boundary = True
            continue
        if kind == "head":
            if current_sp is not None and current_line is not None:
                # A lyric division with existing content begins the next canonical speech.
                open_speech(current_speaker or "Chorus")
            elif current_sp is None:
                open_speech(current_speaker or "Chorus", force_advance=True)
            label = etree.SubElement(current_sp, q("stage"), type="lyric-structure")
            label.text = value
            lyric_mode = True
            lyric_block_count = 0
            continue

        block_plain = clean(node.get_text(" ", strip=True)).strip()
        block_prefix = ""
        if lyric_mode and lyric_block_count:
            open_speech(current_speaker or "Chorus")
        if current_sp is None:
            open_speech(current_speaker or "Narrative", force_advance=pending_boundary)
        elif current_line is not None:
            etree.SubElement(current_line, q("lb"), type="paragraph")

        for token_kind, token_value in tokens_for(node):
            if token_kind == "line":
                if token_value in seen_markers and token_value in {"180", "295"}:
                    continue
                seen_markers.add(token_value)
                last_source_marker = int(token_value)
                if current_line is None or current_line.get("n") != token_value:
                    current_line = etree.SubElement(current_sp, q("l"), n=token_value,
                        corresp=f"urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:{token_value}")
                pending_start = token_value
                block_prefix += f" {token_value} "
            elif token_kind == "text":
                if not clean(token_value).strip():
                    continue
                line = ensure_line()
                append_text(line, token_value)
                block_prefix += token_value
            elif token_kind == "break":
                if current_line is not None:
                    etree.SubElement(current_line, q("lb"))
                block_prefix += " "
            elif token_kind == "note":
                footnote_refs.add(token_value)
                ref_el = etree.SubElement(ensure_line(), q("ref"), type="note", target=f"#chs-note-{token_value}")
                ref_el.text = token_value
                block_prefix += f" {token_value} "
            elif token_kind == "term":
                line = ensure_line()
                key = norm_term(token_value)
                term = etree.SubElement(line, q("term"), {
                    f"{{{XML}}}lang": "grc-Latn", "key": key, "ana": "#chs-key-term"
                })
                term.text = token_value
                bracketed = bool(re.search(r"\[\s*$", block_prefix))
                gloss = local_gloss(block_prefix)
                occurrence = {
                    "passage": current_line.get("n"),
                    "cts": current_line.get("corresp"),
                    "form": token_value,
                    "bracketed": bracketed,
                    "gloss": gloss,
                    "gloss_context": local_gloss_context(block_prefix),
                    "context": block_plain,
                }
                terms[key]["forms"][token_value] += 1
                terms[key]["occurrences"].append(occurrence)
                block_prefix += token_value
            elif token_kind == "stage-inline":
                stage = etree.SubElement(ensure_line(), q("stage"), type="inline")
                stage.text = token_value
                block_prefix += token_value
        if lyric_mode:
            lyric_block_count += 1

    # Notes are kept as stand-off source notes and remain linkable from the text.
    notes_div = etree.SubElement(div, q("div"), type="notes")
    notes_heading = next((x for x in content.find_all("div", class_="Paragraph")
                          if clean(x.get_text(" ", strip=True)).strip() == "Notes"), None)
    if notes_heading:
        sibling = notes_heading.find_next_sibling()
        while sibling is not None:
            txt = clean(sibling.get_text(" ", strip=True)).strip()
            if not txt or not txt.startswith("[ back ]"):
                sibling = sibling.find_next_sibling()
                continue
            match = re.match(r"\[ back \]\s*(\d+)\.\s*(.*)", txt, re.S)
            if match:
                note = etree.SubElement(notes_div, q("note"), n=match.group(1),
                                        **{f"{{{XML}}}id": f"chs-note-{match.group(1)}"})
                note.text = match.group(2)
            sibling = sibling.find_next_sibling()

    index = {
        "source_url": source_url,
        "work_urn": urn,
        "source_version": "perseus-grc2",
        "editors": ["Herbert Weir Smyth (translator)", "Cynthia Bannon (reviser)",
                    "Gregory Nagy (further reviser)"],
        "term_count": sum(len(v["occurrences"]) for v in terms.values()),
        "unique_term_count": len(terms),
        "terms": [],
    }
    for key in sorted(terms):
        value = terms[key]
        index["terms"].append({
            "key": key,
            "forms": dict(value["forms"].most_common()),
            "occurrence_count": len(value["occurrences"]),
            "occurrences": value["occurrences"],
        })
    return etree.ElementTree(root), index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--canonical", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--terms", type=Path, required=True)
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--input-html", type=Path)
    ap.add_argument("--urn", required=True)
    args = ap.parse_args()
    raw = args.input_html.read_bytes() if args.input_html else download(args.url)
    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_bytes(raw)
    tree, index = convert(raw, args.canonical, args.url, args.urn)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(args.output), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    args.terms.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.terms}: {index['term_count']} occurrences, {index['unique_term_count']} keys")


if __name__ == "__main__":
    main()
