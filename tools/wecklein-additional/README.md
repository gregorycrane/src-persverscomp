# Additional Wecklein-related Aeschylus commentaries

Prepared from the three user-supplied HathiTrust OCR exports. These are single-
witness drafts, not proofread transcriptions. Attribution follows the printed
source title pages, not filenames:

| Work | CTS work | Edition | Explanatory pages | Distinct entries |
| --- | --- | --- | --- | ---: |
| Persians | tlg0085.tlg002 | W. S. Teuffel, third edition revised by N. Wecklein, 1886 | 43–97 | 155 |
| Seven Against Thebes | tlg0085.tlg004 | N. Wecklein, 1902 | 15–100 | 691 |
| Suppliants | tlg0085.tlg001 | N. Wecklein, 1902 | 24–120 | 662 |

The original OCR exports are unchanged. `boundaries.json` records reviewed
page starts by original scan sequence and nonempty-line index. `editorial.json`
records false-heading exclusions and two heading repairs supported by local
sequence and Greek lemma; scan verification remains necessary. Each complete
audit retains original headings and raw lines with coordinates. There are
1,515 extracted source notes, combined into 1,508 distinct line/range entries.
Duplicate labels retain every note's content and provenance in separate paragraphs.

All entries visibly identify uncollated OCR. Detected mixed-script corruption
uses `sic`; flags are not exhaustive. Printed spelling and line-end hyphens
are retained. Layout problems remain: Suppliants p. 81 has interleaved column
fragments, and the detached word “Die” on p. 24 is displayed as an unplaced
fragment. Both are explicitly flagged. Further heading and layout review is
needed before scholarly use.

All reference placements are provisional. Existing 1885 correspondences are
used only when their Greek source-line content occurs on the commentary page
(77 Persians, 497 Seven, 438 Suppliants notes). Otherwise, exact substantial
Greek reference lines in the page's running text and nearby pages define a
local reference window (78, 199, 226 respectively). These windows locate notes
for review; they do not verify the full source scope. A source range label is
preserved even when placement anchors its beginning or a local window.
Agreement of Greek content is not full validation of printed source numbering.

Introductions, cast lists, hypothesis, running Greek and separate appendices
are excluded. Persians pp. 98 onward include metrical and critical material
outside this explanatory-note conversion. Greek script uses `mentioned`;
full citation/quotation/gloss tagging remains for scholarly review.

## Reproduce

With Python and lxml, from this directory:

```sh
python3 -B extract.py
python3 -B build.py --corpus /Users/gcrane/github/grcnewxml \
  --canonical /Users/gcrane/github/canonical-greekLit --out generated
PYTHONPATH=/Users/gcrane/github/src-persverscomp python3 -B validate.py generated \
  --canonical /Users/gcrane/github/canonical-greekLit
```

Fresh conversion reproduces all XML and audits byte for byte. The strict
validator checks metadata, namespace, unique entries/IDs, pages, reference
endpoints, local pointers and rendering of every entry/warning through the
existing line-commentary parser. The three new real-source regression fixtures
extend the existing suite to 37 passing tests.
