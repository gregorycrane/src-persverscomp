from pathlib import Path

from pipeline.experimental_collections import _label_pearson_work_volume
from tools.sync_fragment_editions import label_with_volume, source_volume


def test_source_volume_is_added_to_fragment_edition_label(tmp_path: Path):
    source = tmp_path / "edition.xml"
    source.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>'
        '<sourceDesc><bibl><biblScope unit="volume">vol. ii</biblScope></bibl>'
        '</sourceDesc></fileDesc></teiHeader></TEI>',
        encoding="utf-8",
    )
    volume = source_volume(source)
    assert volume == "II"
    assert label_with_volume("Greek (Kock, 1884; OCR draft): ΑΙΓΕΣ", volume) == (
        "Greek (Kock, 1884, vol. II; OCR draft): ΑΙΓΕΣ"
    )


def test_pearson_work_label_identifies_its_volume():
    work = {
        "cards": [{"pearson": {"volume": "2"}}],
        "versions": [{
            "short_id": "pearson1917-grc1",
            "label": "Greek with commentary (A. C. Pearson, 1917) (OCR draft)",
        }],
    }
    _label_pearson_work_volume(work)
    assert work["versions"][0]["label"] == (
        "Greek with commentary (A. C. Pearson, 1917, vol. II) (OCR draft)"
    )
    assert work["versions"][0]["source_volume"] == "2"
