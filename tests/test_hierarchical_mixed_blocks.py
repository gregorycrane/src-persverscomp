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
