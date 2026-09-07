# Wecklein 1888 Agamemnon commentary

This is an OCR draft integrated into the existing Agamemnon work, under
`wecklein1888-com-ger1`. It is a commentary, not a replacement Greek edition.

The Iowa export (`iau.31858021876903`) is the base; Harvard `hvd.hw42j8`
is the second OCR witness. Original exports retain the HathiTrust public-domain
statements, digitization provenance and download timestamps. Michigan
`mdp.39015011872879` is Schneidewin/Hense and is deliberately excluded.

Only explanatory commentary from printed pp. 30–140 is extracted. The
introduction, running Greek and textual appendix (pp. 141–160) are excluded.
There are 899 source notes in 898 distinct line/range entries: the two notes
on 1406 share one CTS entry. Numbered cross-references within notes are not
separate commentary entries. Page boundaries remain milestones within notes.

## Reproduce

Run from this directory, using Python with lxml installed:

```sh
python3 extract_notes.py
python3 build_commentary.py \
  --edition /Users/gcrane/github/grcnewxml/data/tlg0085/tlg005/tlg0085.tlg005.wecklein1885-grc2.xml \
  --reference /Users/gcrane/github/canonical-greekLit/data/tlg0085/tlg005/tlg0085.tlg005.perseus-grc2.xml \
  --out generated
python3 validate.py generated/tlg0085.tlg005.wecklein1888-com-ger1.xml
```

The extraction writes intermediate `pages.json` and `notes.json`. The final
XML is installed in grcnewxml; the complete `collation.json` is retained here
under generated. The raw exports and reviewed JSON inputs are authoritative
conversion inputs; do not regenerate reviewed boundaries from fuzzy matches.

`boundaries.json` records the zero-based commentary start in each page's
nonempty OCR lines and its second-witness counterpart. Match diagnostics
from initial exploration are retained as evidence, not used to infer note
anchors. `editorial.json` identifies false headings and witnessed heading
repairs. A few explicit layout relocations are documented in extract_notes.py.
Original input text is never overwritten. Physical line-end hyphenation is
joined mechanically; spelling is not modernized.

## Limits and next review

- 2,186 OCR disagreement spans are retained in the collation audit, which
  contains both complete readings for every source note. Iowa disagreement
  spans and mixed Greek/Latin tokens are marked `sic`; second-witness-only
  text triggers an explicit possible-omission/layout warning. Agreement
  between OCR witnesses is not proof of correctness.
- The reference map reuses the existing 1885 Wecklein-to-Smyth correspondence;
  it does not assume equal source/reference numbers. 709 notes have matching
  Greek content in the 1888 page's running text. The other 190 notes carry a
  visible provisional-alignment warning. This corroborates reuse, not a
  comprehensive verification of printed 1888 line numbering.
- `alignment_supplement.json` supplies missing existing mappings using Greek
  content. Where a historical line spans reference lines or has an uncertain
  boundary, an explicit range is retained (e.g. 116 → 113–115). This does not
  modify the 1885 edition. Supplemented correspondences remain reviewable.
- Source `ff.` anchors its first line; it is never expanded to an invented end.
- Greek script is marked `mentioned`, familiar citations `bibl`. Full semantic
  quotation and gloss tagging remains for scholarly review. No unattested
  cross-work passage alignment is fabricated.
- Continue with scan proofreading of disagreements and provisional anchors.
  This release must remain labeled **OCR draft** until that is done.

Choephoroi and Eumenides are now integrated as OCR drafts. See
[oresteia/README.md](oresteia/README.md) for their conversion, sources,
comparison gaps and remaining editorial work.
