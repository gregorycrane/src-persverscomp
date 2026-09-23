from xml.etree import ElementTree as ET

from pipeline.core.xml_utils import extract_text_recursive


def test_choice_displays_expansion_and_preserves_abbreviation_as_metadata():
    line = ET.fromstring(
        '<l>amplúſ<choice><abbr>q;</abbr><expan>que</expan></choice></l>'
    )

    html = extract_text_recursive(line)

    assert '>que</span>' in html
    assert 'data-original="q;"' in html
    assert 'title="Original: q;"' in html
    assert 'amplúſq;que' not in html


def test_choice_prefers_correction_over_sic():
    paragraph = ET.fromstring(
        '<p><choice><sic>peccavit</sic><corr>peccârit</corr></choice></p>'
    )

    html = extract_text_recursive(paragraph)

    assert '>peccârit</span>' in html
    assert 'data-original="peccavit"' in html
