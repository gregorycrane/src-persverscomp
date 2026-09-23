from tools.blass1907.tag_bibls import TEI_NS, tag_bibls


def test_regex_rules_tag_spacing_and_number_variants(tmp_path):
    source = tmp_path / "blass.xml"
    source.write_text(
        f'''<TEI xmlns="{TEI_NS}"><text><body><seg type="comment" xml:id="c1">'''
        "Pausanias IX, 12, 3; Herodot 7, 109; Euripides I. T. 1301 ff.; "
        "Apollonios Rhod. III, 44; Pindar N. 4, 18."
        "</seg></body></text></TEI>", encoding="utf-8")
    tree, changes = tag_bibls(source)
    bibls = tree.xpath("//tei:bibl", namespaces={"tei": TEI_NS})
    assert len(changes) == 5
    assert [b.get("n") for b in bibls] == [
        "Paus. IX, 12, 3", "Hdt. 7, 109", "Eur. Iph. T. 1301 ff.",
        "Apoll. Rhod. Argon. III, 44", "Pind. Nem. 4, 18",
    ]


def test_inherited_book_ranges_and_fragment_editions(tmp_path):
    source = tmp_path / "blass.xml"
    source.write_text(
        f'''<TEI xmlns="{TEI_NS}"><text><body><seg type="comment" xml:id="c2">'''
        "Pausan. IX, 2, 1. 7, 4; Apollon. 3, 41. 46; Ar. Βάτρ. 10. 14; "
        "Frg. 120 Ddf. 124 N."
        "</seg></body></text></TEI>", encoding="utf-8")
    tree, _ = tag_bibls(source)
    bibls = tree.xpath("//tei:bibl", namespaces={"tei": TEI_NS})
    assert [b.get("n") for b in bibls] == [
        "Pausan. IX, 2, 1", "Paus. IX, 7, 4", "Apoll. Rhod. Argon. 3, 41-46",
        "Ar. Ran. 10-14", "Aesch. Frg. 120 Dindorf", "Aesch. Frg. 124 Nauck",
    ]


def test_existing_bibl_is_not_nested_or_retagged(tmp_path):
    source = tmp_path / "blass.xml"
    source.write_text(
        f'''<TEI xmlns="{TEI_NS}"><text><body><seg type="comment">'''
        '<bibl n="Hdt. 8, 37">Herodot 8, 37</bibl> Hdt. II, 170'
        "</seg></body></text></TEI>", encoding="utf-8")
    tree, changes = tag_bibls(source)
    bibls = tree.xpath("//tei:bibl", namespaces={"tei": TEI_NS})
    assert len(changes) == 1
    assert len(bibls) == 2
    assert not tree.xpath("//tei:bibl/tei:bibl", namespaces={"tei": TEI_NS})


def test_two_passages_are_separate_bibls_and_aristotle_variants_match(tmp_path):
    source = tmp_path / "blass.xml"
    source.write_text(
        f'''<TEI xmlns="{TEI_NS}"><text><body><seg type="comment">'''
        "Ar. Ach. 101. 205; Aristot. Πολ. Αθ. 3, 5; Aristoteles Πολ. Αθ. Col. 35"
        "</seg></body></text></TEI>", encoding="utf-8")
    tree, changes = tag_bibls(source)
    bibls = tree.xpath("//tei:bibl", namespaces={"tei": TEI_NS})
    assert len(changes) == 3
    assert [b.get("n") for b in bibls] == [
        "Ar. Ach. 101", "Ar. Ach. 205", "Arist. Ath. Pol. 3, 5",
        "Arist. Ath. Pol. Col. 35",
    ]
