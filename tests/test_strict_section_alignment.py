"""A missing parallel section must not display the first section's text."""
import pytest

@pytest.mark.parametrize('strict,expected_count', [(True, 1), (False, 2)])
def test_missing_section_does_not_copy_unrelated_text(tmp_path, monkeypatch, strict, expected_count):
    from pipeline import ingest_work
    from pipeline.core.storage import init_storage_engine
    def source(name, sections):
        p = tmp_path / (name + '.xml')
        p.write_text('<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
                     '<div type="textpart" subtype="chapter" n="1">' +
                     ''.join('<div type="textpart" subtype="section" n="%s"><p>%s</p></div>' % (n, text)
                             for n, text in sections) + '</div></body></text></TEI>')
        return {'path': str(p), 'label': '(' + name + ', 1908)', 'class': 'edition'}
    registry = {'phi1348.abo011': {'textgroup': 'phi1348', 'work': 'abo011',
        'strict_section_alignment': strict,
        'editions': {'latin': source('latin', [('1','Latin first'), ('2','Latin second')])},
        'translations': {'english': source('english', [('1','English first')])}}}
    monkeypatch.setattr(ingest_work, 'WORK_REGISTRY', registry)
    conn = init_storage_engine(tmp_path / 'test.db')
    try:
        ingest_work.ingest_editions_and_structure(conn, list(registry))
        rows = dict(conn.execute("SELECT passage_urn,content_html FROM text_segments WHERE version_short_id='english'"))
        assert len(rows) == expected_count
        assert 'English first' in rows['urn:cts:latinLit:phi1348.abo011:1.1']
        if strict:
            assert 'urn:cts:latinLit:phi1348.abo011:1.2' not in rows
        assert conn.execute("SELECT count(*) FROM text_segments WHERE version_short_id='latin'").fetchone()[0] == 2
    finally:
        conn.close()
