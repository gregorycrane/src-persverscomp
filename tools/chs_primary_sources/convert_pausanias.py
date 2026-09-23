#!/usr/bin/env python3
"""Convert the CHS Pausanias Reader HTML to CTS-compatible TEI.

The CHS page marks canonical passages with ``{book.chapter.section}``, key
Greek terms with ``<em>``, displayed quotations with ``inlineCitation``, and
many attributions with ``bibl``.  The converter preserves those distinctions
and also handles the small number of passage boundaries printed inside a
quotation rather than at the start of a source paragraph.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
# Three source markers contain harmless punctuation typos: ``{8.7.1.}``,
# ``(8.25.1}``, and ``{9.4.1.}``.  Accept those variants without changing the
# published prose.
PASSAGE_RE = re.compile(r"[\{\(](\d+)\.(\d+)\.(\d+)\.?\}")


def q(local: str) -> str:
    return f"{{{TEI}}}{local}"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or " ")


def norm_term(value: str) -> str:
    value = unicodedata.normalize("NFC", clean(value).strip())
    return value.casefold().strip(" .,:;!?[](){}\"“”‘’")


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Perseus-MVP-CHS-import/1.0"})
    with urlopen(request, timeout=90) as response:
        return response.read()


def append_text(parent: etree._Element, value: str) -> None:
    value = clean(value)
    if not value.strip():
        return
    if len(parent):
        previous = parent[-1]
        existing = previous.tail or ""
        if (existing or "".join(previous.itertext()))[-1:].isalnum() and value[:1].isalnum():
            value = " " + value
        previous.tail = existing + value
    else:
        existing = parent.text or ""
        if existing[-1:].isalnum() and value[:1].isalnum():
            value = " " + value
        parent.text = existing + value


def local_gloss_context(prefix: str) -> str | None:
    if not re.search(r"\[\s*$", prefix):
        return None
    value = re.sub(r"\[\s*$", "", prefix).strip()
    value = re.split(r"[.;:!?—]", value)[-1].strip()
    words = value.split()
    return " ".join(words[-5:]) or None


class Writer:
    def __init__(self, work: etree._Element, urn: str):
        self.work = work
        self.urn = urn
        self.books: dict[str, etree._Element] = {}
        self.chapters: dict[tuple[str, str], etree._Element] = {}
        self.sections: dict[tuple[str, str, str], etree._Element] = {}
        self.current_ref: tuple[str, str, str] | None = None
        self.current_section: etree._Element | None = None
        self.current_p: etree._Element | None = None
        self.current_quote: etree._Element | None = None
        self.pending_cit: etree._Element | None = None
        self.mode = "normal"
        self.prefix = ""
        self.terms = defaultdict(lambda: {"forms": Counter(), "occurrences": []})

    def switch(self, ref: tuple[str, str, str]) -> None:
        book, chapter, section = ref
        if book not in self.books:
            self.books[book] = etree.SubElement(
                self.work, q("div"), type="textpart", subtype="book", n=book
            )
        if (book, chapter) not in self.chapters:
            self.chapters[(book, chapter)] = etree.SubElement(
                self.books[book], q("div"), type="textpart", subtype="chapter", n=chapter
            )
        if ref not in self.sections:
            self.sections[ref] = etree.SubElement(
                self.chapters[(book, chapter)], q("div"),
                type="textpart", subtype="section", n=section,
            )
        self.current_ref = ref
        self.current_section = self.sections[ref]
        self.current_p = None
        self.current_quote = None
        self.pending_cit = None
        self.prefix = ""

    def paragraph(self) -> etree._Element:
        if self.current_section is None:
            raise ValueError("Text appeared before the first CHS passage marker")
        if self.current_p is None:
            self.current_p = etree.SubElement(self.current_section, q("p"))
        return self.current_p

    def quote(self) -> etree._Element:
        if self.current_quote is None:
            cit = etree.SubElement(self.paragraph(), q("cit"), type="block")
            self.current_quote = etree.SubElement(cit, q("quote"), rend="blockquote")
            self.pending_cit = cit
        return self.current_quote

    def target(self) -> etree._Element:
        return self.quote() if self.mode == "quote" else self.paragraph()

    def add_bibl(self, text: str) -> None:
        text = clean(text).strip()
        if not text:
            return
        cit = self.pending_cit
        if cit is None:
            cit = etree.SubElement(self.paragraph(), q("cit"), type="block")
            etree.SubElement(cit, q("quote"), rend="blockquote")
        bibl = etree.SubElement(cit, q("bibl"), rend="right")
        bibl.text = text

    def add_text(self, value: str) -> None:
        pos = 0
        for match in PASSAGE_RE.finditer(value):
            before = value[pos:match.start()]
            if before.strip():
                append_text(self.target(), before)
            ref = match.groups()
            old_mode = self.mode
            self.switch(ref)
            self.mode = old_mode
            pos = match.end()
        after = value[pos:]
        if after.strip():
            append_text(self.target(), after)
        self.prefix += value

    def add_term(self, text: str, context: str) -> None:
        target = self.target()
        key = norm_term(text)
        term = etree.SubElement(target, q("term"), {
            f"{{{XML}}}lang": "grc-Latn", "key": key, "ana": "#chs-key-term"
        })
        term.text = text
        passage = ".".join(self.current_ref or ())
        gloss_context = local_gloss_context(self.prefix)
        gloss = gloss_context.split()[-1] if gloss_context else None
        self.terms[key]["forms"][text] += 1
        self.terms[key]["occurrences"].append({
            "passage": passage,
            "cts": f"{self.urn}:{passage}",
            "form": text,
            "bracketed": bool(re.search(r"\[\s*$", self.prefix)),
            "gloss": gloss,
            "gloss_context": gloss_context,
            "context": context,
        })
        self.prefix += text


def note_number(node: Tag) -> str | None:
    link = node.find("a", href=re.compile(r"^#n\."))
    if not link:
        return None
    href = link.get("href", "")
    return href[3:] if href.startswith("#n.") else href


def append_inline(writer: Writer, node, context: str) -> None:
    if isinstance(node, Comment):
        return
    if isinstance(node, NavigableString):
        writer.add_text(str(node))
        return
    if not isinstance(node, Tag):
        return
    classes = set(node.get("class") or [])
    if node.name == "span" and "noteref" in classes:
        number = note_number(node)
        if number and number != "*":
            ref = etree.SubElement(writer.target(), q("ref"),
                                   type="note", target=f"#chs-note-{number}")
            ref.text = number
        return
    if node.name == "a" and node.get("name"):
        return
    if node.name == "em":
        writer.add_term(clean(node.get_text(" ", strip=True)).strip(), context)
        return
    if node.name == "br":
        etree.SubElement(writer.target(), q("lb"))
        writer.prefix += " "
        return
    if node.name == "a" and node.get("href", "").startswith(("http://", "https://")):
        ref = etree.SubElement(writer.target(), q("ref"), target=node["href"])
        ref.text = clean(node.get_text(" ", strip=True)).strip() or node["href"]
        return
    if node.name == "strong":
        hi = etree.SubElement(writer.target(), q("hi"), rend="bold")
        hi.text = clean(node.get_text(" ", strip=True)).strip()
        return
    for child in node.children:
        append_inline(writer, child, context)


def append_quote(writer: Writer, node: Tag, context: str) -> None:
    old_mode = writer.mode
    writer.mode = "quote"
    writer.current_quote = None
    inner_bibls = []
    for child in node.children:
        if isinstance(child, Tag) and "bibl" in set(child.get("class") or []):
            inner_bibls.append(clean(child.get_text(" ", strip=True)).strip())
        elif isinstance(child, Tag) and "Paragraph" in set(child.get("class") or []):
            for grandchild in child.children:
                append_inline(writer, grandchild, context)
        else:
            append_inline(writer, child, context)
    # Force an empty source quotation to disappear rather than creating an
    # empty <cit>.  Quotes are otherwise created lazily by append_inline.
    writer.current_quote = None
    writer.mode = old_mode
    for bibl in inner_bibls:
        writer.add_bibl(bibl)


def append_section_block(writer: Writer, block: Tag) -> None:
    context = clean(block.get_text(" ", strip=True)).strip()
    children = list(block.children)
    index = 0
    while index < len(children):
        child = children[index]
        if isinstance(child, Tag):
            classes = set(child.get("class") or [])
            if "inlineCitation" in classes:
                append_quote(writer, child, context)
                index += 1
                continue
            if "bibl" in classes:
                writer.add_bibl(child.get_text(" ", strip=True))
                index += 1
                continue
            if child.name == "p":
                writer.current_p = None
                for grandchild in child.children:
                    if isinstance(grandchild, Tag) and "inlineCitation" in set(grandchild.get("class") or []):
                        append_quote(writer, grandchild, context)
                    else:
                        append_inline(writer, grandchild, context)
                writer.current_p = None
                index += 1
                continue
        append_inline(writer, child, context)
        index += 1
    writer.current_p = None
    writer.current_quote = None
    writer.pending_cit = None


def add_refs_decl(header: etree._Element) -> None:
    encoding = etree.SubElement(header, q("encodingDesc"))
    refs = etree.SubElement(encoding, q("refsDecl"), {f"{{{XML}}}id": "CTS"})
    level1 = etree.SubElement(refs, q("citeStructure"),
                              match="/TEI/text/body", use="@xml:base")
    level2 = etree.SubElement(level1, q("citeStructure"), unit="book", delim=":",
                              match="div/div[@subtype='book']", use="@n")
    level3 = etree.SubElement(level2, q("citeStructure"), unit="chapter", delim=".",
                              match="div[@subtype='chapter']", use="@n")
    etree.SubElement(level3, q("citeStructure"), unit="section", delim=".",
                     match="div[@subtype='section']", use="@n")
    paragraph = etree.SubElement(encoding, q("p"))
    paragraph.text = (
        "CHS passage markers supply book, chapter, and section. Italicized transliterated "
        "Greek is encoded as term @xml:lang='grc-Latn'; displayed quotations and their "
        "marked attributions are encoded as cit/quote/bibl."
    )


def convert(html: bytes, source_url: str, urn: str):
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("article .contentMain") or soup.select_one(".contentMain")
    if content is None:
        raise ValueError("CHS .contentMain was not found")

    root = etree.Element(q("TEI"), nsmap={None: TEI})
    header = etree.SubElement(root, q("teiHeader"))
    file_desc = etree.SubElement(header, q("fileDesc"))
    title_stmt = etree.SubElement(file_desc, q("titleStmt"))
    etree.SubElement(title_stmt, q("title")).text = "Description of Greece"
    etree.SubElement(title_stmt, q("author")).text = "Pausanias"
    for name, role in [("W. H. S. Jones", "base translator"),
                       ("H. A. Ormerod", "base translator, Scroll 2"),
                       ("Gregory Nagy", "retranslator")]:
        editor = etree.SubElement(title_stmt, q("editor"), role=role)
        editor.text = name
    resp = etree.SubElement(title_stmt, q("respStmt"))
    etree.SubElement(resp, q("resp")).text = "HTML-to-TEI conversion, citation preservation, and term tagging"
    etree.SubElement(resp, q("name")).text = "Perseus MVP"
    pub = etree.SubElement(file_desc, q("publicationStmt"))
    etree.SubElement(pub, q("publisher")).text = "Center for Hellenic Studies"
    etree.SubElement(pub, q("p")).text = "Converted from the CHS Primary Sources publication."
    source = etree.SubElement(file_desc, q("sourceDesc"))
    bibl = etree.SubElement(source, q("bibl"))
    bibl.text = "A Pausanias Reader in progress: Description of Greece, Scrolls 1–10. Gregory Nagy, 2018."
    ref = etree.SubElement(source, q("ref"), target=source_url)
    ref.text = "CHS source page"
    add_refs_decl(header)
    profile = etree.SubElement(header, q("profileDesc"))
    langs = etree.SubElement(profile, q("langUsage"))
    etree.SubElement(langs, q("language"), ident="eng").text = "English"
    etree.SubElement(langs, q("language"), ident="grc-Latn").text = "Ancient Greek transliterated into Latin script"
    revision = etree.SubElement(header, q("revisionDesc"))
    etree.SubElement(revision, q("change"), when="2026-09-21").text = "Converted from CHS HTML for Perseus MVP."

    text = etree.SubElement(root, q("text"), {f"{{{XML}}}lang": "eng"})
    body = etree.SubElement(text, q("body"), {f"{{{XML}}}base": urn})
    work = etree.SubElement(body, q("div"), type="translation", n=urn,
                            **{f"{{{XML}}}lang": "eng"})
    writer = Writer(work, urn)

    in_reader = False
    for child in content.children:
        if isinstance(child, Tag) and child.name == "h2":
            heading = clean(child.get_text(" ", strip=True)).strip()
            if heading.startswith("Scroll "):
                in_reader = True
            if heading in {"Inventory of terms and names", "Bibliography", "Footnotes"}:
                break
        if not in_reader or not (isinstance(child, Tag) and child.name == "div"
                and "Paragraph" in set(child.get("class") or [])):
            continue
        block_text = clean(child.get_text(" ", strip=True)).strip()
        # WordPress occasionally breaks one canonical section into several
        # top-level Paragraph divs.  Unnumbered blocks therefore continue the
        # preceding section.  Backlinks belong to the separate footnote list.
        if block_text == "[ back ]" or writer.current_section is None and not PASSAGE_RE.match(block_text):
            continue
        if block_text.isupper() and len(block_text.split()) <= 8:
            head = etree.SubElement(writer.current_section, q("head"))
            head.text = block_text.title()
            continue
        append_section_block(writer, child)

    notes_div = etree.SubElement(work, q("div"), type="notes")
    for footnote in content.select("div.ftNote"):
        paragraph = footnote.select_one("div.Paragraph")
        if paragraph is None:
            continue
        anchor = paragraph.find("a", attrs={"name": re.compile(r"^n\.")})
        if anchor is None:
            continue
        anchor_name = anchor.get("name", "")
        number = anchor_name[2:] if anchor_name.startswith("n.") else anchor_name
        if not number.isdigit():
            continue
        note = etree.SubElement(notes_div, q("note"), n=number,
                                **{f"{{{XML}}}id": f"chs-note-{number}"})
        clone = BeautifulSoup(str(paragraph), "html.parser").select_one("div.Paragraph")
        noteref = clone.select_one("span.noteref")
        if noteref:
            noteref.decompose()
        bold = clone.find("span", style=re.compile("font-weight"))
        if bold:
            bold.decompose()
        note.text = clean(clone.get_text(" ", strip=True)).strip()

    index = {
        "source_url": source_url,
        "work_urn": urn,
        "source_version": "perseus-grc2",
        "editors": ["W. H. S. Jones (base translator)",
                    "H. A. Ormerod (base translator, Scroll 2)",
                    "Gregory Nagy (retranslator)"],
        "term_count": sum(len(v["occurrences"]) for v in writer.terms.values()),
        "unique_term_count": len(writer.terms),
        "terms": [],
    }
    for key in sorted(writer.terms):
        value = writer.terms[key]
        index["terms"].append({
            "key": key,
            "forms": dict(value["forms"].most_common()),
            "occurrence_count": len(value["occurrences"]),
            "occurrences": value["occurrences"],
        })
    return etree.ElementTree(root), index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--terms", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--input-html", type=Path)
    parser.add_argument("--urn", required=True)
    args = parser.parse_args()
    raw = args.input_html.read_bytes() if args.input_html else download(args.url)
    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_bytes(raw)
    tree, index = convert(raw, args.url, args.urn)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(args.output), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    args.terms.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.terms}: {index['term_count']} occurrences, {index['unique_term_count']} keys")


if __name__ == "__main__":
    main()
