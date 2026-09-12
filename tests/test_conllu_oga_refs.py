import pytest
from pipeline.treebank.conllu import parse_conllu_treebank


@pytest.mark.parametrize('ref,expected,book', [
    ('Cl._1214', '1214', None), ('Birds_1214', '1214', None),
    ('Wasps_1214b', '1214b', None), ('1214', '1214', None),
    ('Dionys._1.1214', '1.1214', '1'), ('1.1214', '1.1214', '1'),
])
def test_oga_reference_and_readable_translation(tmp_path, ref, expected, book):
    source = tmp_path / 'source.conllu'
    source.write_text('# sent_id = 1\n# readable_translation = A reading.\n'
                      '# literal_translation = A literal.\n'
                      f'1\tword\tlemma\tNOUN\t_\t_\t0\troot\t_\tref={ref}|gloss=word\n')
    intervals = [dict(book='1', card_n='1214', label='1214-1258')]
    ss, _ = parse_conllu_treebank(source, 'oga', 'tlg0019', 'tlg003', intervals, book is not None)
    assert len(ss) == 1
    s = ss[0]
    assert (s['chapter'], s['book']) == ('1214-1258', book)
    assert s['tokens'][0]['ref'] == expected
    assert s['prose'] == 'A reading.'
    assert s['literal'] == 'A literal.'
    assert s['tokens'][0]['gloss'] == 'word'


def test_lettered_card_and_damaged_first_reference(tmp_path):
    source = tmp_path / 'source.conllu'
    source.write_text(''.join(
        f'# sent_id = {i}\n1\tword\tlemma\tNOUN\t_\t_\t0\troot\t_\tref=Lys._{ref}\n\n'
        for i, ref in enumerate(['531', '531b', '536', '538'], 1)))
    intervals = [dict(book='1', card_n='486', label='486-531'),
                 dict(book='1', card_n='531b', label='531b-538')]
    ss, _ = parse_conllu_treebank(source, 'oga', 'tlg0019', 'tlg007', intervals, False)
    assert [s['chapter'] for s in ss] == ['486-531', '531b-538', '531b-538', '531b-538']
    source.write_text('# sent_id = 108\n'
                      '1\tword\tlemma\tNOUN\t_\t_\t0\troot\t_\tref=Pl._NaN\n'
                      '2\tword\tlemma\tNOUN\t_\t_\t1\tdep\t_\tref=Pl._129\n')
    ss, _ = parse_conllu_treebank(source, 'oga', 'tlg0019', 'tlg011',
                                [dict(book='1', card_n='100', label='100-150')], False)
    assert ss[0]['chapter'] == '100-150'
    assert ss[0]['book'] is None
    assert ss[0]['tokens'][0]['ref'] == 'Pl._NaN'
