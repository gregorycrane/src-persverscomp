# Wecklein 1888: Choephoroi and Eumenides OCR drafts

These resources extend the Agamemnon conversion in the parent directory. Each
uses version `wecklein1888-com-ger1` within its existing work and is registered
as a German commentary. They are not proofread editions.

| Work | Printed explanatory pages | Entries | Witnesses |
| --- | --- | --- | --- |
| Choephoroi / Libation Bearers | 163–234 | 591 | HW42J8 only, as requested |
| Eumenides | 251–322 | 542 | HW42J8 base; HXJHA8 comparison |

The unchanged HathiTrust exports preserve digitization and rights statements.
HXJHA8 is a composite scan; its later Oresteia volume contains Eumenides.
Its export skips printed pages 294–295 (scan sequence 461 = p. 293, 462 =
p. 296). Twenty-two notes are wholly or partly affected. The base survives;
`gap reason="ocr-source-unavailable"` refers only to the comparison OCR.
Actual scan sequences are used, rather than an assumed constant offset.
Although the composite also contains Choephoroi, that play deliberately uses
only HW42J8 under the user's single-witness instruction.

Running Greek, title/cast lists, introductions and separate textual appendices
are excluded. Entries follow note line/range headings, not page boundaries.
`boundaries.json` records reviewed page starts in zero-based nonempty OCR
lines; `editorial.json` records explicit heading/layout interventions. Keep
these reviewed inputs. Original heading strings remain in the audit.
Mechanical line-end dehyphenation does not modernize historical spelling.

## Reproduce and validate

From this directory, with Python and lxml available:

```sh
python3 -B extract.py
python3 -B build.py --corpus /Users/gcrane/github/grcnewxml \
  --canonical /Users/gcrane/github/canonical-greekLit --out generated
python3 -B validate.py generated --canonical /Users/gcrane/github/canonical-greekLit
```

The extraction recreates pages.json, notes.json, excluded-layout.json and
unanchored-comparison.json. Generated XML is installed in grcnewxml; audits
are retained in generated/. Regression tests live in
`tests/test_wecklein1888_oresteia.py` in src-persverscomp.

## Remaining editorial work

Every Choephoroi entry visibly says single-witness, uncollated OCR. Detected
mixed-script corruption is marked `sic`; undetected errors remain possible.
Eumenides retains 1,189 disagreement spans in the audit, both note readings,
and visible `sic`/possible omission warnings. Neither agreement nor the
absence of an automatic flag proves that OCR is correct. Missing comparison
pages do not cause following continuation text to attach to the wrong note;
unanchored continuation is preserved separately if encountered.

Reference placement reuses the existing 1885 Wecklein-to-Smyth crosswalk.
Greek page content corroborates 434 Choephoroi and 428 Eumenides note anchors;
157 and 114 respectively have visible provisional warnings. Supplements are
documented in each audit; uncertain correspondences retain bounding ranges.
This is not full verification of 1888 printed lineation. Source `f.` spans two
lines, while `ff.` anchors only the starting line. Greek discussion is tagged
`mentioned`; recognized citation-following Greek passages use `cit/quote/bibl`.
Full semantic quotation/gloss tagging, scan proofreading, and provisional
anchor review remain necessary. No speculative prose correction is inserted
from the comparison OCR.
