import json
from pathlib import Path

from lxml import etree

from pipeline.sophocles_dindorf_concordance import build_dindorf


SOURCE = Path(
    "/Users/gcrane/github/grcnewxml/data/tlg0011/fragments/source/"
    "tlg0011.fragmenta.dindorf1893-grc1.xml"
)
NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def test_dindorf_sophocles_is_normalized_tei_with_stable_citations():
    source = build_dindorf(SOURCE)
    assert len(source["works"]) == 104
    assert len(source["fragments"]) == 963
    assert source["versions"][0]["short_id"] == "dindorf1893-grc1"
    assert not any(work["source_title"].upper() in {"ΣΟΦΟΚΛΕΟΥΣ", "ΑΠΟΣΠΑΣΜΑΤΑ"}
                   for work in source["works"].values())
    assert all(fragment["source_fragment_urn"].count(":") == 4
               for fragment in source["fragments"])

    tree = etree.parse(str(SOURCE))
    assert not tree.xpath("//tei:div[@subtype='fragment']//tei:l[not(@n)]", namespaces=NS)
    assert not tree.xpath("//tei:l[not(@xml:id)]", namespaces=NS)
    assert tree.xpath("count(//tei:citeStructure)", namespaces=NS) == 4


def test_registry_orders_dindorf_nauck_pearson_as_independent_editions():
    registry = json.loads(
        (Path(__file__).parents[1] / "work_registry.json").read_text(encoding="utf-8")
    )
    for key in ("tlg0011.fragmenta", "tlg0011.aigeys", "tlg0011.aichmalotides"):
        editions = registry[key]["fragment_editions"]
        assert "dindorf1893-grc1" in editions
        assert editions["dindorf1893-grc1"]["format"] == "tei_fragment_collection"
