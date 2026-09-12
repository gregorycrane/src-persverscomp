from pipeline.parsers.poetry_cards import parse_poetry_cards_tei


def test_mixed_prose_retains_text_after_stage_and_note(tmp_path):
    p = tmp_path / 'mixed.xml'
    p.write_text('''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div type="translation"><milestone unit="card" n="1"/>
      <sp><speaker>Demosthenes</speaker><p><milestone unit="line" n="1"/>
      Begin. <stage>To Nicias</stage>There must be an end to it.
      <note>Source note.</note>Let us see what can be done.</p></sp>
      <milestone unit="card" n="40"/>
      <sp><speaker>Nicias</speaker><p>The next speech.</p></sp>
      </div></body></text></TEI>''')
    intervals = {'1': [dict(book='1', card_n='1', label='1-39', start_line=1, end_line=39),
                       dict(book='1', card_n='40', label='40-84', start_line=40, end_line=84)]}
    data = parse_poetry_cards_tei(str(p), intervals)['1']
    first, second = data['1-39']['1'], data['40-84']['1']
    for phrase in ('There must be an end to it.', 'Source note.', 'Let us see what can be done.'):
        assert first.count(phrase) == 1
        assert phrase not in second
    assert 'The next speech.' in second
    assert 'The next speech.' not in first
