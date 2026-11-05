"""Do not lose Suetonius Latin prose encoded as l instead of p."""
def test_section_with_lines_and_mixed_prose(tmp_path):
    from pipeline.parsers.hierarchical import parse_hierarchical_tei
    p = tmp_path / 'mixed.xml'
    p.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div type="textpart" subtype="chapter" n="53">
        <div type="textpart" subtype="section" n="1"><p>First.</p></div>
        <div type="textpart" subtype="section" n="2"><l>Second.</l></div>
        <div type="textpart" subtype="section" n="3"><p>Third start.</p>
          <quote><lg><l>Quoted verse.</l></lg></quote><ab>Third end.</ab></div>
      </div></body></text></TEI>''')
    data = parse_hierarchical_tei(str(p), include_nonparagraph_blocks=True)['1']['53']
    assert set(data) == {'1', '2', '3'}
    assert 'Second.' in data['2']
    html = data['3']
    assert html.count('Quoted verse.') == 1
    assert html.index('Third start.') < html.index('Quoted verse.') < html.index('Third end.')


def test_line_group_preserves_local_line_numbers_and_full_citations(tmp_path):
    from pipeline.parsers.hierarchical import parse_hierarchical_tei
    p = tmp_path / 'lineated.xml'
    p.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div type="chapter" n="13"><div type="section" n="17">
        <lg><l n="1">First line.</l><l n="2">Second line.</l></lg>
      </div></div>
    </body></text></TEI>''')
    html = parse_hierarchical_tei(
        str(p), include_nonparagraph_blocks=True,
        line_citation_scheme='chapter.section.line',
    )['1']['13']['17']
    assert html.count('class="line-num-cell"') == 2
    assert 'data-n="1" data-cite="13.17.1"' in html
    assert 'data-n="2" data-cite="13.17.2"' in html
    assert html.index('First line.') < html.index('Second line.')


def test_page_divisions_are_citable_and_keep_heads_and_notes(tmp_path):
    from pipeline.parsers.hierarchical import parse_hierarchical_tei
    p = tmp_path / 'pages.xml'
    p.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div type="edition"><div type="textpart" subtype="page" n="12">
        <pb n="12"/><head>B. FRAGMENTE.</head><p>Greek text.</p>
        <note type="footnote">Critical note.</note>
      </div></div>
    </body></text></TEI>''')
    data = parse_hierarchical_tei(str(p), include_nonparagraph_blocks=True)
    html = data['1']['12']['12']
    assert 'B. FRAGMENTE.' in html
    assert 'Greek text.' in html
    assert 'Critical note.' in html


def test_fragment_divisions_are_citable_and_page_breaks_are_not(tmp_path):
    from pipeline.parsers.hierarchical import parse_hierarchical_tei
    p = tmp_path / 'fragments.xml'
    p.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div type="edition"><div type="textpart" subtype="fragment" n="2A">
        <pb n="68" facs="https://example.test/scan/68"/><head>2A.</head>
        <lg><l>Greek fragment.</l></lg><note>Critical note.</note>
      </div></div>
    </body></text></TEI>''')
    data = parse_hierarchical_tei(str(p), include_nonparagraph_blocks=True)
    html = data['1']['2A']['2A']
    assert 'Greek fragment.' in html
    assert 'Critical note.' in html
    assert '68' not in data['1']
