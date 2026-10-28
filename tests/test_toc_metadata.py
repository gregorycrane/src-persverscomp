from tools.build_toc_metadata import (
    add_author_word_totals,
    collection_metadata,
    count_fragment_html,
    edition_name,
    merge_catalog_fragments,
)


def test_author_total_uses_surviving_plays_and_largest_fragment_edition():
    authors = {
        "tlg0011": {
            "editions": [
                {"edition": "Dindorf", "word_count": 5365},
                {"edition": "Nauck", "word_count": 6534},
                {"edition": "Pearson", "word_count": 8513},
            ]
        }
    }
    complete_works = {
        "tlg0011.tlg001": {
            "surviving_play": True,
            "word_count": 120654,
        },
        # A fragmentary dramatic work represented in the normal work catalog
        # must not be folded into the surviving-play subtotal.
        "tlg0011.tlg008": {
            "surviving_play": False,
            "word_count": 1914,
        },
    }

    result = add_author_word_totals(authors, complete_works)["tlg0011"]

    assert result["surviving_word_count"] == 120654
    assert result["counted_fragment_edition"] == "Pearson"
    assert result["counted_fragment_word_count"] == 8513
    assert result["total_word_count"] == 129167


def test_kock_volume_one_collection_label():
    assert edition_name("kock1880-grc1") == "Kock"
    assert collection_metadata("kock1880-grc1")["collection_label"] == (
        "Kock, vol. 1"
    )


def test_kock_volume_two_collection_label():
    assert edition_name("kock1884-grc1") == "Kock"
    metadata = collection_metadata("kock1884-grc1")
    assert metadata["collection_label"] == "Kock, vol. 2"
    assert metadata["source_edition_year"] == 1884


def test_kock_volume_three_collection_label():
    assert edition_name("kock1888-grc1") == "Kock"
    metadata = collection_metadata("kock1888-grc1")
    assert metadata["collection_label"] == "Kock, vol. 3"
    assert metadata["source_edition_year"] == 1888


def test_meineke_volume_collection_labels():
    expected = {
        "meineke1839-grc1": ("Meineke, vol. 2", 1839),
        "meineke1840-grc1": ("Meineke, vol. 3", 1840),
        "meineke1841-grc1": ("Meineke, vol. 4", 1841),
    }
    for short_id, (label, year) in expected.items():
        assert edition_name(short_id) == "Meineke"
        metadata = collection_metadata(short_id)
        assert metadata["collection_label"] == label
        assert metadata["source_edition_year"] == year


def test_fragment_word_count_excludes_transmitting_context():
    html = (
        '<div class="pmv-fragment"><div class="fc-verse">'
        '<l n="1" lang="grc">δύο λέξεις</l></div>'
        '<details class="fc-context"><div>many Latin source words here</div>'
        '</details></div>'
    )
    assert count_fragment_html(html) == 2


def test_evidence_only_work_retains_collection_source(tmp_path):
    catalog = {
        "authors": {"tlg9999": "Evidence Author"},
        "works": {
            "tlg9999.lost_play": {
                "textgroup": "tlg9999",
                "work": "lost_play",
                "fragmentary": True,
                "parts": [],
                "versions": [
                    {
                        "short_id": "nauck1889-grc1",
                        "label": "Greek (Nauck, 1889)",
                        "doc_type": "edition",
                    }
                ],
            }
        },
    }

    works, authors = merge_catalog_fragments(tmp_path, catalog, {}, {})

    edition = works["tlg9999.lost_play"]["editions"][0]
    assert edition["fragment_count"] == 0
    assert edition.get("collection_label", edition["edition"]) == "Nauck"
    author_edition = authors["tlg9999"]["editions"][0]
    assert author_edition.get("collection_label", author_edition["edition"]) == "Nauck"


def test_author_source_summary_deduplicates_version_id_variants(tmp_path):
    versions = {
        "one": "nauck1889-grc1",
        "two": "nauck1889grc1",
    }
    catalog = {
        "authors": {"tlg9999": "Evidence Author"},
        "works": {
            f"tlg9999.{work}": {
                "textgroup": "tlg9999",
                "work": work,
                "fragmentary": True,
                "parts": [],
                "versions": [
                    {
                        "short_id": short_id,
                        "label": "Greek (Nauck, 1889)",
                        "doc_type": "edition",
                    }
                ],
            }
            for work, short_id in versions.items()
        },
    }

    _, authors = merge_catalog_fragments(tmp_path, catalog, {}, {})

    assert len(authors["tlg9999"]["editions"]) == 1
    assert authors["tlg9999"]["editions"][0]["edition"] == "Nauck"
