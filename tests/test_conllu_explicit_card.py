import pytest
from pipeline.treebank.conllu import parse_conllu_treebank


def test_explicit_card_preserves_lettered_line_and_translation(tmp_path):
    f=tmp_path/'lettered.conllu'
    f.write_text('# sent_id = source1\n# pmv_card = 1:531b-538\n# prose_translation = If that bothers you\n1\tεἰ\tεἰ\tSCONJ\t_\t_\t0\troot\t_\tRef=531b|gloss=if\n')
    iv=[dict(book='1',card_n='486',label='486-531',start_line=486,end_line=531),dict(book='1',card_n='531b',label='531b-538',start_line=531,end_line=538)]
    sentences,_=parse_conllu_treebank(str(f),'sanjaya','tlg0019','tlg007',iv,False)
    s=sentences[0]
    assert (s['book'],s['chapter'],s['section']) == (None,'531b-538','1')
    assert s['tokens'][0]['ref']=='531b'
    assert s['tokens'][0]['gloss']=='if'
    assert s['prose']=='If that bothers you'
    multi,_=parse_conllu_treebank(str(f),'sanjaya','tlg0019','tlg007',iv,True)
    assert multi[0]['book']=='1'
    f.write_text(f.read_text().replace('1:531b-538','1:999-1000'))
    with pytest.raises(ValueError,match='Unknown explicit PMV card'):
        parse_conllu_treebank(str(f),'sanjaya','tlg0019','tlg007',iv,False)
