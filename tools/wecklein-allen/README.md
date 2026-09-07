# Wecklein–Allen English Prometheus commentary

Version `tlg0085.tlg003.wecklein-allen1893-com-eng1` is a conservative OCR draft of the printed commentary on Prometheus Bound, pp. 31–144. The supplied title pages identify N. Wecklein and translator F. D. Allen, Ginn & Company, 1893 and 1891. Allen's prefatory note describes adaptation from Wecklein's second German edition (1878). The Prometheus Unbound fragments, introduction, hypothesis, metre section and appendix are outside this integration.

The 1893 export supplies the base. Its printed pages alternate with handwritten interleaves: `boundaries.json` selects the printed pages and the commentary within them. It records zero-based nonempty OCR line indices, with an exclusive end. `editorial.json` records three excluded marginal intrusions; the complete original OCR remains in `oxford-1893.txt`. Remaining marginalia may survive and require review.

The 1891 PDF text layer supplies the comparison. `bbox.html` preserves Poppler word coordinates for PDF pages 44–157; `secondary-columns.json` reconstructs two columns using word coordinates. The extraction bounds use English word positions and can omit Greek-only fragments near column edges. This is an OCR comparison aid, not a complete diplomatic transcription of the PDF.

Comparison uses normalized **page-local word occurrence counts**, not an ordered critical collation. Unmatched tokens in the displayed witness receive `sic`; punctuation, accents, ordering, missing words and printing variants are not resolved by this test. Matching tokens can still be incorrect. No lexical substitutions are made. On printed p. 120 only, the reconstructed 1891 OCR replaces the interleaved 1893 OCR, explicitly labeled in the viewer. The audit preserves both page texts.

688 source-heading units are placed provisionally using exact normalized Greek running-text matches to nearby Smyth reference lines. Reference windows are placement aids, not verified whole-note scope. All entries display OCR and alignment status. Source heading detection is constrained by local reference evidence and increasing source numbers; note division still needs scholarly review. Empty marginal numerals do not create headings.

## Reproduce and validate

Python 3 with lxml and Poppler's pdftotext are required. `sources.json` records supplied input filenames and SHA-256 hashes. The PDF itself remains in the user's supplied Downloads location; all extracted comparison data are archived here.

```sh
python3 -B extract.py --text /path/to/aesch-pb-weckcommeng-oxu1-601566764-1788784655.txt --pdf /path/to/aech-pb-weckcommeng-oxu1-601623131-1788753294.pdf
python3 -B build.py --canonical /path/to/canonical-greekLit/data/tlg0085/tlg003/tlg0085.tlg003.perseus-grc2.xml --out /tmp/wecklein-allen
python3 -B validate.py /tmp/wecklein-allen/tlg0085.tlg003.wecklein-allen1893-com-eng1.xml /tmp/wecklein-allen/audit.json /path/to/canonical-greekLit/data/tlg0085/tlg003/tlg0085.tlg003.perseus-grc2.xml
```

`validate.py` checks exact extraction-to-TEI content preservation, complete page coverage, unique IDs, both witness dates, translator attribution, flags, and valid reference endpoints. `tests/test_wecklein_allen.py` checks parser rendering including the 1891 page substitution, witness links, uncertainty, and the last note.
