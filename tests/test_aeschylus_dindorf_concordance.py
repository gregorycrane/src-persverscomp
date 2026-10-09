from pathlib import Path

from pipeline.aeschylus_fragment_concordance import (
    DINDORF, NAUCK, build_play_level, merge_work_views,
)


SOURCE_DIR = Path("/Users/gcrane/github/grcnewxml/data/tlg0085")


def test_dindorf_tei_has_stable_work_scoped_fragment_citations():
    source = build_play_level(SOURCE_DIR, DINDORF)
    assert len(source["works"]) == 66
    assert len(source["fragments"]) == 429
    assert all(fragment["source_fragment_urn"].count(":") == 4
               for fragment in source["fragments"])
    assert "aeschylus-dindorf1893-grc1-athamas" in source["works"]
    athamas_one = next(fragment for fragment in source["fragments"]
                       if fragment["source_fragment_urn"].endswith(".athamas.dindorf1893-grc1:1"))
    assert athamas_one["same_as"] == [
        "urn:cts:greekLit:tlg0085.athamas.nauck1889-grc1:1"
    ]
    assert not any(work["source_title"] in {"ΑΙΣΧΥΛΟΥ", "ΑΠΟΣΠΑΣΜΑΤΙΑ", "ΑΠΟΣΠΑΣΜΑΤΑ"}
                   for work in source["works"].values())


def test_dindorf_and_nauck_align_by_quoted_greek_not_fragment_number():
    works, concordance = merge_work_views(
        build_play_level(SOURCE_DIR, DINDORF),
        build_play_level(SOURCE_DIR, NAUCK))
    assert len(works) == 75
    assert len(concordance) == 193
    pairs = {(match["work"], match["card"]) for match in concordance}
    assert ("athamas", "D1=N1") in pairs
    assert ("athamas", "D2=N3") in pairs
    assert all(match["method"] in {
        "exact-normalized-greek", "mutual-best-normalized-greek",
        "quoted-text-in-source-context", "fuzzy-quoted-text-in-source-context",
    } for match in concordance)
