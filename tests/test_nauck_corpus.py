import json
import re
from pathlib import Path

from lxml import etree

from pipeline.nauck_corpus import AUTHORS, NS, load_source, publication_model


DATA = Path("/Users/gcrane/github/grcnewfragments/data")
SOURCE = Path("/Users/gcrane/github/GRC_misc/nauck.tragfrag-2.xml")
CORPUS = DATA / "nauck1889"
REGISTRY = Path(__file__).parents[1] / "work_registry.json"


def test_complete_nauck_source_and_manifest_are_tei():
    master = etree.parse(str(CORPUS / "source/nauck1889.tragicorum-graecorum-fragmenta.xml"))
    assert len(master.xpath("//tei:l", namespaces=NS)) == 7195
    assert len(master.xpath("//tei:pb", namespaces=NS)) == 976
    assert master.xpath("//tei:revisionDesc/tei:change[contains(., 'malformed TEI namespace')]", namespaces=NS)

    manifest = etree.parse(str(CORPUS / "corpus.xml"))
    includes = manifest.xpath("//*[local-name()='include']/@href")
    aeschylus = [href for href in includes if "/tlg0085/" in href]
    sophocles = [href for href in includes if "/tlg0011/" in href]
    euripides = [href for href in includes if "/tlg0006/" in href]
    assert len(aeschylus) == 71  # one include for each non-empty Nauck work
    assert len(sophocles) == 104
    assert len(euripides) == 57
    assert len(includes) == len(aeschylus) + len(sophocles) + len(euripides) + len(AUTHORS) - 2
    assert all((CORPUS / href).resolve().exists() for href in includes)
    authority = etree.parse(str(CORPUS / "authority.xml"))
    assert len(authority.xpath("//tei:person", namespaces=NS)) == 56
    assert len(authority.xpath("//tei:idno[@type='PerseusAuthor']", namespaces=NS)) == 39
    assert len(authority.xpath("//tei:idno[@type='TLGCanonKey']", namespaces=NS)) == 14
    assert authority.xpath(
        "//tei:person[@xml:id='tlg0315']/tei:idno[@type='TLGCanonKey'][.='0315']",
        namespaces={**NS, "xml": "http://www.w3.org/XML/1998/namespace"},
    )
    assert authority.xpath(
        "//tei:person[starts-with(@xml:id, 'tragfrag')]/@xml:id", namespaces=NS
    ) == ["tragfragadesp"]


def test_every_non_aeschylean_line_and_fragment_marker_is_preserved():
    source = load_source(SOURCE)
    chapters = source.xpath("//tei:div[@type='edition']/tei:div[@type='textpart']", namespaces=NS)
    non_aeschylus = [chapter for chapter in chapters if int(chapter.get("n")) >= 4]
    source_lines = sum(len(chapter.xpath(".//tei:l", namespaces=NS)) for chapter in non_aeschylus)
    source_fragments = sum(
        1
        for chapter in non_aeschylus
        for paragraph in chapter.xpath("./tei:p", namespaces=NS)
        if re.fullmatch(r"\d+(?:[a-z])?", " ".join(paragraph.itertext()).strip(), re.I)
    )
    report = json.loads((CORPUS / "build-report.json").read_text())["authors"]
    assert len(report) == 56
    # Thirty-eight self-contained Greek quotation paragraphs are normalized
    # into numbered TEI lines in addition to the source's existing <l> nodes.
    assert source_lines == 6487
    assert sum(author["lines"] for author in report.values()) == source_lines + 38
    assert source_fragments == 3144
    assert sum(author["fragments"] for author in report.values()) == 3143

    euripides = etree.parse(str(DATA / "tlg0006/phaethon/tlg0006.phaethon.nauck1889grc1.xml"))
    assert euripides.xpath("count(//tei:milestone[@unit='sourceLine'][@n='40'])", namespaces=NS) == 1
    for spec in AUTHORS:
        if spec.textgroup in {"tlg0011", "tlg0006"}:
            paths = sorted((DATA / spec.textgroup).glob(
                f"*/{spec.textgroup}.*.nauck1889grc1.xml"))
            numbers = []
            for path in paths:
                local = etree.parse(str(path)).xpath(
                    "//tei:div[@subtype='fragment']/@n", namespaces=NS)
                assert len(local) == len(set(local)), (spec.name, path)
            continue
        path = DATA / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.nauck1889grc1.xml"
        numbers = etree.parse(str(path)).xpath("//tei:div[@subtype='fragment']/@n", namespaces=NS)
        assert len(numbers) == len(set(numbers)), spec.name


def test_generated_author_tei_and_registry_agree():
    registry = json.loads(REGISTRY.read_text())
    for spec in AUTHORS:
        if spec.textgroup in {"tlg0011", "tlg0006"}:
            paths = sorted((DATA / spec.textgroup).glob(
                f"*/{spec.textgroup}.*.nauck1889grc1.xml"))
            assert paths
            for path in paths:
                slug = path.name.split(".")[1]
                record = registry[f"{spec.textgroup}.{slug}"]
                version = record["fragment_editions"]["nauck1889grc1"]
                assert version["path"] == str(path)
                assert version["format"] == "tei_fragment_work"
            continue
        path = DATA / spec.textgroup / "fragments/source" / f"{spec.textgroup}.fragmenta.nauck1889grc1.xml"
        tree = etree.parse(str(path))
        edition_urn = f"urn:cts:greekLit:{spec.textgroup}.fragmenta.nauck1889grc1"
        assert tree.xpath("string(//tei:div[@type='edition']/@n)", namespaces=NS) == edition_urn
        assert tree.xpath("//tei:div[@subtype='fragment']", namespaces=NS) or spec.textgroup in {
            "tlg0331", "tlg1848", "tlg0216", "tlg0604"
        }
        record = registry[f"{spec.textgroup}.fragmenta"]
        version = record["fragment_editions"]["nauck1889grc1"]
        assert version["path"] == str(path)
        assert version["urn"] == edition_urn
        assert version["format"] == "tei_fragment_collection"
        assert record["source_edition"] == (
            "multiple-fragment-editions"
            if spec.textgroup in {"tlg0011", "tlg0006"} else "nauck1889"
        )

        containers = tree.xpath(
            "//tei:div[@subtype='play' or @subtype='section']", namespaces=NS
        )
        for container in containers:
            work = container.get("n")
            assert re.fullmatch(r"[a-z0-9_]+", work)
            assert not re.fullmatch(r"(?:play|section)\d+", work)
            assert container.get("{http://www.w3.org/XML/1998/namespace}id") == (
                f"{spec.textgroup}-{work.replace('_', '-')}"
            )
            play_record = registry[f"{spec.textgroup}.{work}"]
            assert play_record["work"] == work
            assert play_record["title"] == container.xpath(
                "string(tei:head[1])", namespaces=NS
            )
            assert play_record["object_urn"] == container.get("corresp")


def test_play_names_drive_work_ids_and_publication_views():
    source = DATA / "tlg0006/melanippe_e_sophe/tlg0006.melanippe_e_sophe.nauck1889grc1.xml"
    tree = etree.parse(str(source))
    medeia = tree.xpath("//tei:div[@type='edition']", namespaces=NS)
    assert medeia  # Greek title transliterates instead of collapsing to `untitled`.
    assert medeia[0].xpath("string(tei:head)", namespaces=NS) == "ΜΕΛΑΝΙΠΠΗ Η ΣΟΦΗ"

    from pipeline.play_level_fragments import build as build_play_level
    model = build_play_level(DATA / "tlg0006", "tlg0006", "nauck1889grc1",
                             "Euripides", "Nauck", "August Nauck")
    assert any(work["work"] == "melanippe_e_sophe" for work in model["works"].values())
    assert model["attributions"]
    melanippe_fragment = next(fragment for fragment in model["fragments"]
                              if fragment.get("play_work") == "melanippe_e_sophe")
    assert melanippe_fragment["play_title"] == "ΜΕΛΑΝΙΠΠΗ Η ΣΟΦΗ"
    assert all(item["play_urn"].startswith((
        "urn:cite2:perseus:fragmentaryplays.v1:tlg0006_",
        "urn:cite2:perseus:fragmentarycollections.v1:tlg0006_",
    )) for item in model["attributions"])


def test_standalone_greek_quotation_is_promoted_to_numbered_line():
    source = DATA / "tlg0011/aichmalotides/tlg0011.aichmalotides.nauck1889grc1.xml"
    tree = etree.parse(str(source))
    line = tree.xpath(
        "//tei:div[@subtype='fragment'][@n='31']/tei:lg/tei:l[@n='1']",
        namespaces=NS,
    )
    assert len(line) == 1
    assert "".join(line[0].itertext()).strip() == "στρατοῦ καθαρτὴς κἀπομαγμάτων ἴδρις"
