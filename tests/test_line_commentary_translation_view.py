from pipeline.parsers.line_commentary import parse_line_commentary_tei


def test_translation_view_renders_complete_translation_and_marks_missing(tmp_path):
    source = tmp_path / "commentary.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div subtype="commline" n="1" corresp="urn:cts:greekLit:x:1">
          <p><seg type="comment" xml:id="c1"><mentioned>λέξις</mentioned> deutscher Text</seg>
          <seg type="translation" xml:lang="eng" corresp="#c1-comment1">English note</seg></p>
          <p><seg type="comment" xml:id="c2">Nur Deutsch</seg></p>
        </div>
        </body></text></TEI>""",
        encoding="utf-8",
    )
    intervals = {"": [{"book": "", "label": "1", "start_line": 1, "end_line": 10}]}

    parsed = parse_line_commentary_tei(
        str(source), intervals, content_view="translation"
    )
    html = parsed[""]["1"]["1"]

    assert "English note" in html
    assert "deutscher Text" not in html
    assert "English translation unavailable" in html
    assert "Nur Deutsch" in html


def test_translation_view_accepts_in_place_translated_comments(tmp_path):
    source = tmp_path / "translated-commentary.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div subtype="commline" n="800-801" corresp="urn:cts:greekLit:x:800">
          <p><seg type="comment" xml:id="c1"><mentioned xml:lang="grc"
          corresp="urn:cts:greekLit:tlg0085.tlg007.perseus-grc2:392">ἔχειν</mentioned>
          <mentioned type="translation" xml:lang="eng">to have</mentioned>:
          so that no punishment befell Orestes.</seg></p>
          <p><seg type="comment" xml:id="c2">The corrupt words have been healed.</seg></p>
        </div>
        </body></text></TEI>""",
        encoding="utf-8",
    )
    intervals = {"": [{"book": "", "label": "1", "start_line": 1, "end_line": 900}]}

    parsed = parse_line_commentary_tei(
        str(source), intervals, content_view="translation",
        translation_storage="in_place",
    )
    html = parsed[""]["1"]["1"]

    assert "English translation unavailable" not in html
    assert "so that no punishment befell Orestes" in html
    assert "The corrupt words have been healed" in html
    assert ">[to have]</span>" in html
    assert '<div class="comm-entry-reference">→ reference 392</div>' in html


def test_commentary_page_break_links_to_source_scan_once(tmp_path):
    source = tmp_path / "commentary-with-pages.xml"
    source.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
        <div subtype="commline" n="1">
          <pb n="68" facs="https://hdl.handle.net/2027/example?urlappend=%3Bseq=76"/>
          <p><seg type="comment">First comment.</seg></p>
        </div>
        <div subtype="commline" n="2">
          <pb n="68" facs="https://hdl.handle.net/2027/example?urlappend=%3Bseq=76"/>
          <p><seg type="comment">Same printed page.</seg></p>
        </div>
        <div subtype="commline" n="3">
          <pb n="69" facs="javascript:alert(1)"/>
          <p><seg type="comment">Unsafe page link.</seg></p>
        </div>
        </body></text></TEI>""",
        encoding="utf-8",
    )
    intervals = {"": [{"book": "", "label": "1", "start_line": 1, "end_line": 10}]}

    parsed = parse_line_commentary_tei(str(source), intervals)
    html = parsed[""]["1"]["1"]

    assert html.count("Source page 68") == 2  # visible text and title
    assert html.count('class="comm-source-page"') == 1
    assert 'href="https://hdl.handle.net/2027/example?urlappend=%3Bseq=76"' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert "javascript:" not in html
