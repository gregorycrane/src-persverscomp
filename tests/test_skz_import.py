import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "sources" / "skz" / "generated"
WORK_DIR = GENERATED / "data" / "skz" / "inscription"
NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def test_skz_generated_witnesses_have_all_51_lines():
    paths = sorted(WORK_DIR.glob("skz.inscription.*.xml"))
    assert len(paths) == 4
    for path in paths:
        root = ET.parse(path).getroot()
        sections = root.findall(".//tei:div[@subtype='section']", NS)
        assert [section.get("n") for section in sections] == [str(n) for n in range(1, 52)]
        assert all(section.find("tei:p", NS) is not None for section in sections)


def test_skz_alignments_and_map_data_are_populated():
    alignment_paths = sorted(WORK_DIR.glob("*.json"))
    assert len(alignment_paths) == 2
    for path in alignment_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert len(payload["segments"]) == 51
        assert sum(len(segment["alignments"])
                   for segment in payload["segments"].values()) > 500

    with (ROOT / "lodcache" / "citations_skz.csv").open(encoding="utf-8") as stream:
        places = list(csv.DictReader(stream))
    assert len(places) >= 190
    assert sum(bool(row["lat"] and row["lon"]) for row in places) >= 170
    assert {row["certainty"] for row in places} >= {"certain", "probable", "uncertain"}
    assert {row["coord_precision"] for row in places} >= {"point", "centroid", "approximate"}
    assert all("coord_source" in row and "place_note" in row for row in places)
