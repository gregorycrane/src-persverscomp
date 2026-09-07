# Perseus Multitext work: durable handoff

Last updated: 2026-09-06

This document is the durable context for continuing the Perseus Multitext
work from a different ChatGPT/Codex account or a new task. Read this file,
`README.md`, and `work_registry.json` before changing anything. When they
conflict, verify the running code: portions of `README.md` predate the latest
incremental-build work documented below.

## First prompt for a new Codex task

Use this as the opening request:

> Continue the Perseus Multitext work. First read
> `/Users/gcrane/github/src-persverscomp/PROJECT_HANDOFF.md`, then inspect the
> current Git status in every repository you need. Preserve all existing
> uncommitted work. Treat the XML sources and `work_registry.json` as the
> source of truth, and test targeted changes before rebuilding a whole
> textgroup.

## Project purpose and repositories

The project builds a browser-based Perseus Multitext Viewer in which a reader
can place multiple editions, translations, commentaries, scholia, apparatus
critici, treebanks, and bridge translations side by side over a common CTS
passage focus.

- `/Users/gcrane/github/src-persverscomp`
  - Build system, parsers, registry, tests, and web source.
  - `work_registry.json` declares every source file and its presentation class.
  - `pipeline/` is the maintained build implementation; the old notebook is
    historical and should not be the first place to fix a problem.
- `/Users/gcrane/github/persverscomp`
  - Running/deployable system produced by `src-persverscomp`.
  - Generated per-work SQLite shards live under `site/data/`.
- `/Users/gcrane/github/grcnewxml/data`
  - Primary XML corpus for newer Aeschylus, Euripides, Aristotle, Ariosto, and
    related additions.
- `/Users/gcrane/github/AntigonesPublic/data`
  - Sophocles editions, translations, commentaries, Homer bridge translations,
    and alignment data used by the viewer.
- `/Users/gcrane/github/canonical-greekLit/data`
  - Canonical reference Greek texts. These commonly supply the
    `perseus-grc2` reference citation sequence.
- `/Users/gcrane/scratch/aschol`
  - Sequestered Aeschylus scholia that were deliberately removed from the live
    registry pending further correction. Do not silently re-register them.
- `/tmp/persvers_build/corpus_alignment_grid.db`
  - Regenerable build-only monolithic database. It is not a source file and
    must never be committed.

## Critical working-tree warning

The `src-persverscomp` repository is not clean. At the time of this handoff it
contains tracked modifications and many untracked pipeline/test files. These
are active project work, not disposable build debris. Do not run destructive
Git commands, reset the repository, or replace it from a clean checkout.

The notable current status includes:

- modified: `README.md`, `web/app.js`, `web/styles.css`,
  `work_registry.json`, and the historical v99 notebook;
- untracked: `Makefile`, `manifest.json`, `pipeline/`, `tests/`, and supporting
  refactor materials;
- a deleted temporary Office lock file is also reported by Git and is unrelated
  to the corpus work.

Before making changes, run `git status --short` and preserve unrelated user
changes. A future cleanup/commit should be deliberate and reviewed rather than
performed as part of an XML conversion.

## Build commands

Run these from `/Users/gcrane/github/src-persverscomp`:

```sh
make work=tlg0085.tlg007  # one work
make work=tlg0085         # every registered work in a textgroup
make                       # every stale work
make index                 # web UI/index only
make test                  # parser/build tests
```

Use `make force` only when a full forced rebuild is genuinely intended. A
missing monolith is reconstructed from deployed shards when possible.

The current build is manifest-driven. Source XML, registry data, parser files,
and shared core files are dependencies. Editing `web/app.js` or
`web/styles.css` calls for `make index`, not corpus re-ingestion.

## Incremental build and sharding design

The sharding design was optimized on 2026-09-06:

- `pipeline/build_all.py` passes only changed work keys to the sharder.
- `pipeline/sharding.py::split_corpus_by_work(..., only_work_keys=...)`
  rewrites only the selected work directories and merges refreshed entries
  into the existing `catalog.json`.
- If there is no usable existing catalog, a partial request safely falls back
  to a full sharding pass rather than publishing an incomplete catalog.
- `pipeline/treebank/flatten.py` now deletes and regenerates flattened tokens
  only for changed works. Reconstituting a monolith still performs the required
  full flatten.
- A forced Eumenides-only build completed in approximately 3.2 seconds with
  `--skip-index`; the adjacent Libation Bearers shard retained the same hash
  and modification time.
- `tests/test_incremental_sharding.py` and
  `tests/test_incremental_treebank_flatten.py` protect these guarantees.

The old `README.md` statements saying that sharding is always corpus-wide and
that lexicon sharding is unimplemented are stale. Inspect the current modules
before relying on those sections.

## TEI and CTS conventions

### General document requirements

- Use TEI XML in the TEI namespace: `http://www.tei-c.org/ns/1.0`.
- Include a modern `<citeStructure>` and retain the older `<refsDecl>` for
  backward compatibility.
- The project no longer requires strict EpiDoc conformance. Normal TEI
  structures such as `<castList>` are welcome when they represent the source.
- Preserve bibliographic and responsibility metadata, OCR provenance, source
  scan identifiers, licenses, and facsimile/page links.
- Update both author-level and work-level `__cts__.xml` files when installing a
  new work or version. Verify that the version URN, label, language, and type
  agree with `work_registry.json`.
- Introductions may be captured as XML, but do not add them to the live work
  registry as commentaries. They cannot be usefully focused by passage.

### Reference edition and `corresp`

- For the Greek dramatic texts, `perseus-grc2` is normally the reference
  edition (often Smyth for Aeschylus and Storr for Sophocles).
- Every numbered `<l>` in a Greek edition should carry a `corresp` pointer to
  the corresponding reference line or range.
- A translation must at minimum carry alignment on each `<sp>`; use finer
  line/paragraph alignment where the evidence supports it.
- Commentary entries should carry their own source lemma/line number and a
  `corresp` pointer to the reference edition. The UI should show both, e.g.
  “H. 1306 → Smyth 1346,” because silently displaying only the source number
  caused serious confusion.
- Alignment must be based on the source and Greek content, not merely equal
  numerical labels. Historical translations often diverge substantially from
  modern Greek lineation.
- Card milestones must align content to the reference card intervals. They are
  navigation/display units, not a substitute for real line correspondence.

### Drama and card boundaries

Some XML serializes the opening of a card as:

```xml
<sp>
  <speaker>...</speaker>
  <milestone unit="card" .../>
  ...
</sp>
```

The parser now recognizes this tightly scoped leading pattern and moves the
speaker into the new card. A milestone after authored speech content remains a
real mid-speech boundary. The regression coverage is in
`tests/test_speaker_card_boundaries.py`.

### OCR uncertainty

- Correct only errors that are obvious from context or a second scan.
- Preserve uncertain, unresolved OCR readings with `<sic>`.
- Missing or unreadable scan/OCR content must be marked as an OCR gap, not as
  an intentional editorial lacuna in the ancient text.
- Do not modernize or silently rewrite a contributor's translation. In
  particular, Amelia Parrish's bridge translations must remain verbatim; their
  structure and alignment may be improved without changing the English.

## Commentary encoding conventions

Passage-addressable notes should be independent entries, not page-sized blobs.
A typical entry is:

```xml
<div type="textpart" subtype="commline" n="1181"
     corresp="urn:cts:greekLit:TEXTGROUP.WORK.perseus-grc2:REFERENCE">
  <p><mentioned xml:lang="grc">Greek lemma</mentioned>: commentary...</p>
</div>
```

- Preserve `<pb n="..." facs="..."/>` milestones and stable links back to
  HathiTrust or another source scan. Page boundaries must not become the
  commentary's semantic divisions.
- Wrap discussed Greek words or phrases in `<mentioned xml:lang="grc">`.
- Use `<gloss>` for an actual gloss/translation, including a long gloss when
  that is what the passage is doing. Length alone does not make `<gloss>`
  improper.
- Reserve `<emph>` for rhetorical emphasis. The viewer has styling for
  `<mentioned>`, `<gloss>`, and `<emph>`; do not use them interchangeably.
- Encode textual quotations and their references as:

```xml
<cit>
  <quote xml:lang="grc">γυναικὸς ὢν δούλευμα</quote>
  <bibl n="Soph. Ant. 756"
        corresp="urn:cts:greekLit:tlg0011.tlg002:756">Ant. 756</bibl>
</cit>
```

- Add `<bibl>` even for familiar abbreviated references that omit authors,
  such as `Ag.`, `O. T.`, `Prom. 1023`, or references to digitized works such
  as `S. Ddf. Lex`.
- Patterns such as `τευχέων l. 742` normally represent a quotation of the
  current play and should become `<cit><quote>...</quote><bibl>...</bibl></cit>`.
- In commentary OCR, apparent `1. NUMBER` is very often `l. NUMBER`, a
  cross-reference to the current play. Normalize only when the context
  confirms it.
- Normalize compact ranges such as `ll. 358, 9` to the reference range
  `358-359` while preserving the displayed source wording when useful.
- Validate XML after every structural tagging pass. Earlier bulk citation
  insertion produced malformed XML; parseability is a hard gate.

The reusable citation and commentary behavior is exercised by
`tests/test_xml_utils_citations.py`, `tests/test_line_commentary_app_lemma.py`,
and `tests/test_line_commentary_multiple_pairs.py`.

## Critical apparatus conventions

- Inline apparatus belongs in the edition when it represents the editor's
  reading and immediate variants:

```xml
<app loc="298" corresp="#l.298">
  <lem>τῶνδ᾽ ἐμοὶ</lem>
  <rdg wit="#h">τῶνδέ μοι</rdg>
</app>
```

- A stand-off `<app>` with `@loc`, `@corresp`, or `@from`/`@to` must be linked
  to the covered line(s). The parser leaves the lemma in the running text and
  exposes variants through the apparatus UI rather than stacking every
  reading as visible running text.
- Retain original `@loc` while adding explicit line pointers. Abbreviated
  ranges such as `413-15` expand to `413-415`; `487sqq` is anchored at 487
  unless a defensible end point can be established.
- Non-line locations such as `castlist` or `end` must not be fabricated into
  line links. Truly unlocated apparatus is preserved once at the end.
- Apparatus and commentary entries should show both the editor's source line
  and the mapped reference line.
- Keep separately authored/full apparatus resources separate when embedding
  them would overwhelm the reading edition, but provide explicit alignment to
  the reference cards.

See `pipeline/core/xml_utils.py`, `pipeline/parsers/poetry_cards.py`, and
`tests/test_standoff_apparatus.py`.

## Registry categories and identifiers

The registry deliberately separates:

- `editions`
- `translations`
- `commentaries`
- `scholia`
- `appcrits`
- `treebanks`
- token `alignments`
- `edition_alignments`

Do not reuse a short ID across categories within one work. A previous Campbell
collision caused a commentary to appear as a Greek edition and disappear from
the commentary menu. Labels and `class` values must agree with the category.
Scholia should appear in their own UI category rather than under ordinary
commentaries.

The project uses TLG identifiers in CTS URNs, but source-facing prose and
metadata should not claim dependence on or reproduce proprietary TLG content.

## Bridge translations

The Amelia Parrish/Gregory Crane bridge translations are intentionally close
to Greek syntax and may sound strange in English. That strangeness is a
pedagogical feature.

- Iliad bridge: `tlg0012.tlg001.parrish2021-eng1`
- Odyssey bridge: `tlg0012.tlg002.parrish2023-eng1`
- Preserve every English translation string exactly.
- Their fundamental alignment is to Homer treebank sentences/tokens rather
  than simply poetic lines. Phrases may draw words from more than one sentence
  and may reorder them.
- The viewer supports word/phrase highlighting and flashcard data. POS and
  morphology can be supplied from the treebank instead of being duplicated in
  the translation.
- Alignment JSON belongs under each work and is registered under `alignments`.

Relevant code and tests include `pipeline/bridge/flashcards.py`,
`tests/test_bridge_flashcards.py`, and `tests/test_conllu_bridge_segments.py`.

## Recent corpus work and present state

### Wecklein Aeschylus

All seven Wecklein Greek editions under
`/Users/gcrane/github/grcnewxml/data/tlg0085` were normalized and rebuilt.

- The files now use the correct default TEI namespace.
- Numeric stand-off apparatus entries have explicit line correspondence.
- Missing Agamemnon line IDs 1449-1470 were added so commentary targets resolve.
- Two deliberately non-line locations remain: Prometheus `loc="end"` and
  Seven `loc="castlist"`.
- Registry line-number sigils now display `Weck.`, not the incorrect `Wil.`.
- The 2026-09-06 production rebuild succeeded for all seven works.

Validation from that build:

| Work | Wecklein segments | Cards containing apparatus | Cards containing targeted notes |
|---|---:|---:|---:|
| `tlg0085.tlg001` | 106 | 104 | 99 |
| `tlg0085.tlg002` | 91 | 36 | 33 |
| `tlg0085.tlg003` | 59 | 56 | 59 |
| `tlg0085.tlg004` | 71 | 71 | 71 |
| `tlg0085.tlg005` | 99 | 97 | 74 |
| `tlg0085.tlg006` | 86 | 86 | 83 |
| `tlg0085.tlg007` | 71 | 69 | 57 |

No rebuilt Wecklein segment retained the erroneous visible sigil `Wil.`.

### Wecklein 1888 Agamemnon commentary: OCR draft integration

The existing Agamemnon work now registers `wecklein1888-com-ger1` as a German
commentary using `line_commentary`, `anchor_axis=corresp`, and Weck./Smyth
source/reference badges. The 1885 Greek edition and apparatus are unchanged.

- Source XML: grcnewxml/data/tlg0085/tlg005/tlg0085.tlg005.wecklein1888-com-ger1.xml.
- Reproducible conversion, raw OCR and collation audit:
  src-persverscomp/tools/wecklein1888/ (read its README before editing).
- Base witness: Iowa 31858021876903; comparison: Harvard HW42J8.
  Michigan 39015011872879 is Schneidewin/Hense and is excluded.
- 899 source notes, 898 distinct line/range entries, printed pp. 30–140.
  Introduction, running Greek and separate textual appendix are excluded.
- The audit retains 2,186 OCR disagreement spans. Unresolved base readings use
  sic; possible omissions/layout disagreement are visibly flagged.
- 709 notes have Greek-page content corroboration for the inherited 1885
  reference mapping; 190 retain visible provisional-alignment warnings.
  Do not describe this as a fully verified 1888 crosswalk or proofread edition.
- Work-level CTS metadata is updated; existing author-level CTS identity was
  verified and kept in its existing groupname-only format.
- Regression fixture: tests/fixtures/wecklein1888_commentary.xml; tests cover
  beginning/middle/end rendering, reference-card placement, OCR uncertainty,
  scan links and local pointers. validate.py performs whole-resource strict QA.

### Wecklein 1888 Choephoroi and Eumenides integration (2026-09-07)

Both later plays now register `wecklein1888-com-ger1` as German OCR-draft
commentary, with the same source/reference badge conventions as Agamemnon.
Conversion inputs, scripts, README and complete audits are retained under
`tools/wecklein1888/oresteia/`.

- Choephoroi: printed pp. 163–234, 591 entries, HW42J8 alone as requested.
  Every entry visibly identifies single-witness, uncollated OCR. 434 anchors
  have page-content corroboration; 157 retain provisional warnings.
- Eumenides: printed pp. 251–322, 542 entries, HW42J8 base and HXJHA8 comparison.
  HXJHA8 is a verified later Oresteia section within a composite scan. Its
  export lacks pp. 294–295: 22 notes are wholly or partly affected and visibly
  distinguish this comparison-source gap from an ancient lacuna. 1,189
  disagreement spans remain in the audit. 428 anchors have page-content
  corroboration; 114 retain provisional warnings.
- Running Greek and separate textual appendices are excluded. Source note
  headings and page milestones survive; uncertain OCR is retained and flagged.
- Strict whole-resource QA and reproducible conversion checks pass. New
  regression fixtures cover both plays, reference placement, visible warnings,
  and continuation handling across missing comparison pages.

Next: scan proofreading and provisional reference-map verification across all
three plays; further semantic quotation/gloss tagging. All three must remain
labeled OCR drafts. Page-content matches are not fully verified 1888 lineation.

### Other important additions

- Sophocles: Campbell editions and commentaries, Campbell/Potter/Francklin
  translations, and edition crosswalks are registered under `tlg0011`.
  Storr (`perseus-grc2`) is the reference for line correspondence.
- Euripides: Potter translations are registered across the plays; Ion also has
  Bayfield, Verrall, and Wilamowitz materials. Speaker/card boundary handling
  was repaired in the parser. Historical translation alignment remains a
  scholarly judgment and should be spot-checked semantically.
- Aeschylus: Sidgwick, Paley, Blass, Hermann apparatus, and Wecklein materials
  have received substantial commentary/apparatus work. Some scholia remain
  sequestered in `/Users/gcrane/scratch/aschol`.
- Aristotle Poetics: Pye, Buckley, Ritter, and other materials are registered.
  Poetics uses finer section/subsection citations; avoid generating duplicate
  chapter-like sections such as `11.1`, `11.2`, etc. as top-level chapters.
- Ariosto: Italian `debenedetti1928-ita1`, English `rose1823-eng1`, and the
  Sanjaya treebank are registered. Citation labels are Canto/Stanza/Line.

## Viewer presentation decisions

- Editions, translations, notes, commentaries, and scholia are distinct menu
  categories and should be visually distinguishable.
- Commentary lemmas in `<mentioned>` should be bold and colored; `<emph>` must
  also have visible emphasis, while `<gloss>` should have its own treatment.
- Apparatus variants should use a popover/tooltip rather than appearing as a
  vertical stack in the running text.
- Commentary badges must remain legible and show source-to-reference mapping.
- Introductions should not appear as passage commentaries.
- A support/funding panel on the separate Perseus homepage work is non-sticky;
  that design work is not part of the viewer build pipeline.

## Validation checklist

For every new or modified XML resource:

1. Parse it strictly with an XML parser; recovery parsing in the build is not
   evidence that the file is valid.
2. Confirm the TEI namespace, `<citeStructure>`, and legacy `<refsDecl>`.
3. Confirm all CTS URNs, `xml:id` targets, `corresp`, `target`, and facsimile
   links resolve as intended.
4. Check card counts and sample cards at the beginning, middle, and end.
5. For Greek editions, check every numbered line for reference correspondence.
6. For translations, inspect semantic alignment rather than trusting equal
   numbers.
7. For commentary, ensure entries are lemma/line units rather than page blobs.
8. Update author/work `__cts__.xml` and `work_registry.json` without ID
   collisions.
9. Run `make test`.
10. Run a targeted build first and inspect the generated work shard.
11. Search generated HTML for wrong sigils, missing categories, malformed tags,
    and obvious OCR debris.

At handoff creation, the complete automated suite passed: **29 tests passed**.

## Maintenance priorities

1. Commit the refactored pipeline and tests after a deliberate review; leaving
   the central build system untracked is the greatest continuity risk.
2. Update `README.md` to remove now-obsolete limitations and document the
   incremental sharder/token refresh accurately.
3. Add real fixtures for parser modes that still have less coverage than
   `poetry_cards`.
4. Keep source transformations reproducible: where a conversion requires a
   substantial script, retain the script or a transformation report rather
   than only the generated XML.
5. Continue developing a comprehensive apparatus that can represent readings
   chosen by each edition plus every reading recorded by their individual
   apparatus critici. Do not collapse source-specific claims prematurely.

## Additional Wecklein-related commentaries installed 2026-09-07

Persians (Teuffel, revised by Wecklein, 1886), Seven Against Thebes (Wecklein,
1902), and Suppliants (Wecklein, 1902) have single-witness OCR drafts installed
in the original corpus and local viewer. Source/metadata identity is verified:
Persians tlg002, Seven tlg004, Suppliants tlg001; tlg003 is Prometheus.
There are 155, 691, and 662 distinct commentary entries respectively.
All reference placements remain provisional and all entries carry OCR warnings.
Read tools/wecklein-additional/README.md for reconstruction and editorial limits.
Installation succeeded after scoped folder permissions were granted. All 28
prepared files matched their reviewed hashes. The original repository suite
passes all 37 tests; targeted builds of tlg001, tlg002 and tlg004 succeeded.
Generated shards contain every new label and OCR/alignment warning across
51 Persians, 71 Seven and 96 Suppliants cards; database integrity checks pass.
The full local viewer was rebuilt. No commit, push or remote publication occurred.
Next: scan proofreading, heading/layout and reference-window refinement;
Suppliants p. 81 especially needs column-order reconstruction.

## 2026-09-07: English Wecklein–Allen Prometheus installed locally

- Work **tlg0085.tlg003**, Prometheus Bound; version `wecklein-allen1893-com-eng1`. It is registered as an English `line_commentary` with `anchor_axis: corresp`, separate from the 1885 Greek edition and Hermann apparatus.
- Supplied Oxford witnesses: `oxu1.601566764` (1893 plain-text OCR) and `oxu1.601623131` (1891 PDF text layer). Both credit N. Wecklein, translated by F. D. Allen, Ginn & Company. Allen describes the German second edition (1878) as his starting point.
- Printed commentary pp. 31–144 only: 688 source-heading units, 52 generated viewer cards. Excludes introduction, hypothesis, separate handwritten interleaves, Unbound fragments, metres and appendix. Some marginalia may remain within OCR and require review.
- Base 1893 text is compared by page-local normalized word occurrence counts against reconstructed 1891 PDF columns. This is a conservative OCR comparison, **not an ordered critical collation**. 699 unmatched tokens are visibly bracketed; punctuation, accents, omissions, order and true printing variants remain unresolved. Agreement is not proof of correctness.
- Printed p. 120 uses the 1891 OCR because the 1893 OCR interleaves columns; this substitution is explicitly visible. Both page texts remain in the audit. Three excluded marginal intrusions are documented separately. All reference windows and source-note segmentation remain provisional.
- Reproducible tools, source export, PDF bbox derivative, page boundaries, editorial decisions, hashes and full audit: `tools/wecklein-allen/`. The PDF remains at the supplied Downloads path identified in `sources.json`.
- Validation confirms all 114 pages, extraction-to-TEI content equality, reference endpoints, witness/translator metadata, unique IDs, and all flags. New parser fixture covers beginning, p. 120 substitution and final note. Full suite: **38 passed**. Targeted `python3 -B -m pipeline.build_all --work tlg0085.tlg003` succeeded. Generated shard checked for all 688 entries and 699 flags, correct commentary classification, and 52 cards.
- Existing registry entries preserved. Earlier Oresteia and three German commentary integrations remain intact. Installed and rebuilt locally only; no commit, push or remote publication.
