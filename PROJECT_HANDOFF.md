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


### Donner Sophocles: seven installed OCR review translations (2026-09-08)

All seven `tlg0011` works now include `donner1875-deu1`, installed alongside
existing Sophocles material in `AntigonesPublic/data/tlg0011`, with work CTS
entries and registry metadata. Existing author/work titles were already present.
The PMV was rebuilt for all seven works and its index regenerated.

- Copy text: Cornell OCR of the 1875 eighth edition. Corroborating witness:
  California OCR of the 1889 eleventh edition. The supplied Illinois files are
  volumes I and II of the 1850 third, newly revised edition, preserved separately
  in each review; they are not interchangeable copies of the later edition.
- 476 Storr card milestones, reviewed at speech/stanza/clause openings, with
  containing-card `corresp` on verses and speeches. This is not exact word or
  line equivalence. The Jebb OCR numbering anomaly around OC 1014–1098 was
  bypassed by checking the Greek reference directly.
- Donner has native `<l n>` citations. Shared parts retain citations; 52
  unresolved verse-division intervals use explicitly editorial `u` suffixes.
  Do not turn these into numeric printed citations without checking scans.
- 388 note entries have corroborating printed labels and native citation
  targets. 82 extracted entries remain unattributed. All note wording and
  extraction boundaries still need proofreading. Complete appendix OCR from
  both later witnesses is preserved in each notes JSON; page-split notes join
  across page references. These counts are extraction counts, not a claim that
  every printed note has been independently verified.
- 285 structural repair records, one facsimile-verified reconstruction batch
  for OT displaced replies and ending, and 88 corroborated token repairs.
  Original OCR, page comparisons, changes and remaining numbering are retained.
- All 32 metrical pages are local PNGs under
  `persverscomp/site/data/tlg0011/donner1875/facsimiles/`, described by TEI
  surfaces, linked from the translations, and shown in `Metrical-facsimiles.html`.
  Source: Internet Archive `sophoklesdeutsc02donngoog`, an independent 1875 scan.
- Antigone pp.254–255 reprint the 1839 Bacchus hymn. This is kept in a separate
  TEI back appendix and linked from the relevant passage, not added to the
  running translation. Detailed earlier-edition variant collation is unfinished.
- `make test`: 46 passed. Strict XML, IDs, target resolution, source text
  retention, reference endpoints, ordered card coverage and graphic checks pass.
  All 476 installed cards have text; all 32 images respond locally. Live PMV
  check confirms Donner numbering, notes, Greek correspondence and gallery link.

Review landing page:
`http://localhost:8000/site/data/tlg0011/donner1875/Review-inventory.html`

Workspace scripts and staged data:
`/Users/gcrane/Documents/Codex/2026-09-06/referenced-chatgpt-conversation-this-is-an/work/donner-sophocles/`
Outputs, downloaded PDFs and inventories: sibling `outputs/Donner-Sophocles/`.
Next scholarly work: proofread residual OCR, resolve `u` intervals from printed
pages, verify note boundaries and missing/corrupt labels, and collate earlier
variants more fully. Keep the OCR-review label meanwhile.

## Donner Euripides — installed OCR review editions (2026-09-08)

Installed all eighteen translations in `/Users/gcrane/github/grcnewxml/data/tlg0006/tlg001` through `tlg018`, with per-work `__cts__.xml` and work_registry.json entries. Rhesus is not part of the supplied set. Versions follow the source volume: `donner1841-deu1` (Hecuba, Phoenician Women, Orestes, Medea, Hippolytus, Alcestis); `donner1845-deu1` (Iphigenia at Aulis, Iphigenia among Taurians, Bacchae, Cyclops, Helen, Andromache); `donner1852-deu1` (Trojan Women, Ion, Electra, Heracles, Suppliant Women, Children of Heracles). Existing Euripides author/work tables already covered these plays and were retained.

Sources: Harvard supplied OCR `eur-donner1-hvd-hw2j3v-1788883331.txt` contains volumes I AND II (1841, 1845); `eur-donner2-hvd-hw2j3w-1788883389.txt` contains III (1852). Independent BSB copies were found for all three: bsb10232928, bsb10232929, bsb10232930. All 1,164 BSB hOCR pages and coordinates are preserved in the working directory, with source hashes. Harvard remains running-text copy text; the BSB note transcription is expressly identified, not silently represented as unchanged Harvard OCR.

Installed assets: `persverscomp/site/data/tlg0006/donner1841-1852/`. Start with `Review-inventory.html`, `EDITORIAL_STATE.md`, `Editorial-inventory.json`, `Edition-inventory.json`, and `Metrical-facsimiles.html`. There are 40 metrical-chart pages and 78 note-page facsimiles. Later volumes discuss metre in the notes, not separate chart appendices. Source-page hash links expand the appropriate image panel. Original pagewise OCR, repair audits, final card mappings, all extracted notes and unattributed notes are retained for review.

Citation and alignment: 994 Murray reference cards, reviewed at speech/stanza/clause openings. Native Donner l/@n citations; shared verses retain I/F parts. corresp means containing Murray card, not exact one-to-one verse correspondence. Iphigenia at Aulis preserves Donner's opening order, whereas Murray moves Greek 49–114 before 1–48: milestones occur 1, 0, 80, 115 in Donner order. Card 0 corresp excludes empty Greek placeholder 0. Exact installed database rows for 1–48 and 0–79 were checked for correct, separate text. The reference English IT typo n=188 between 1187 and 1189 was normalized to 1188 locally for alignment only; canonical sources were not changed.

Notes: 1,224 entries attached where a label resolves; 152 candidates remain unattributed with reasons. Hecuba's complete two-page appendix was visually checked for all 34 note divisions, recovering five entries previously merged by OCR. Other attachments require explicit labels at line openings in both OCR copies and a matching native citation. This is not a claim that every note's wording or every extraction boundary has been exhaustively proofread. The full appendix OCR remains available for finding further missed entries.

Remaining editorial work: 479 numbering intervals remain unresolved, with u suffixes rather than guessed printed numbers. Some wrapping, speaker debris and word OCR remain. Preserve historical language; never globally substitute å with ä (it can also represent ü). Printed errata are preserved in Printed-errata.json but not comprehensively integrated. Do not describe this as a fully clean critical edition or complete word-level collation.

Validation: strict XML, unique IDs, valid local targets and Murray endpoints, verse retention, shared-part-only duplicate citations, complete card rendering, 18 installed XML files matching staged files, and all 118 installed facsimiles checked. All 18 targeted builds succeeded; PMV was recompiled. All 49 pipeline tests passed (including three new source-reference tests). Live viewer check showed Donner's Hecuba and native line numbers next to Murray. A renderer issue discovered during live checking was fixed: HTTP(S) and /site/ TEI ref targets now become clickable links; CTS and non-web references retain non-navigating span behavior. Existing xml_utils.py modifications were preserved.

Working files: `/Users/gcrane/Documents/Codex/2026-09-06/referenced-chatgpt-conversation-this-is-an/work/donner-euripides/`; deliverables in sibling `outputs/Donner-Euripides/`. Manual card maps contain stable record IDs; after any structural reparse they must be checked again. Do not blindly regenerate automatic alignment proposals over reviewed mappings. The numbering routine distinguishes shared-group identifiers from ordinary record identifiers: a collision discovered during verification was fixed before installation. A mistaken preliminary Trojan Women 350→330 repair was explicitly rejected and reverted; its audit records the rejection. Installation backups and exact pre-change hashes are in work/donner-euripides/install/.


Final Euripides navigation check: an exact requested IA card `1-48` was being resolved to overlapping card `0-79`. Updated `web/app.js` to prefer exact flat-card labels before raw-line containment. Five JavaScript checks passed (both overlapping cards, a normal card, a within-card range, and a single line). This preserves Donner's native text order and the existing Murray card mapping.
Live browser verification after compilation: IA `1-48` now opens Donner “Komm, Alter” alongside Murray Greek line 1, with native Donner citations and clickable source-note links. The 49-test suite passes after the navigation change.

## Aristophanes translations (2026-09-08)

All ten XML translation sources in the supplied OldMacintoshHD Aristophanes/copyright directory are migrated to grcnewxml/data/tlg0019, with group/work __cts__.xml. Clouds is absent from that directory and uses canonical perseus-eng2; canonical Birds perseus-eng2 is retained alongside the expressly requested legacy Birds perseus-eng1. All eleven Greek references and twelve English versions are registered. Canonical XML and tracking JSON fingerprints are unchanged.

Ten new TEI files pass the local TEI P5 schema. Exact normalized source wording and note order are preserved except one unmarked Beta Code speaker *mnhsi/loxos → Μνησίλοχος. All original parentheses are retained and counted. All 120 source notes retained; note locations were not independently verified against print. Card mapping adjustments, source defects and attribution limitations are in grcnewxml/data/tlg0019/migration-review/EDITORIAL_STATE.md and Migration-inventory.json. Verse-only editorial ordinals in Lindsay/Dillon are translation-specific (tr.), not Greek line numbers. All substantive cards render; Frogs 0-0 is an empty reference-only placeholder.

Poetry parser now retains XML tails following stage/verse/p/note leaf elements; the prior behavior omitted spoken text after inline stages in mixed prose. Regression tests/test_poetry_mixed_tails.py and all 50 tests pass. Rendered body word sequences of all ten migrations match the XML. All eleven works compiled and deployed shards verified. Review index: http://localhost:8000/site/data/tlg0019/migration-review/Review-inventory.html . Workspace scripts: work/aristophanes (install.py and add_birds.py are one-shot).

Aristophanes also added to web/app.js isPoetryWork display classification (11 new-work checks plus two existing-work checks passed). Without this entry, the correct shard contents displayed in prose layout. Viewer index recompiled after the addition.

## Aristophanes Sanjaya annotations (2026-09-08)

Installed all eleven plays from local aristophanes-sanjaya commit c319590c139e5603e71f0699caa0663d823af8ad. Registry versions: sanjaya-tb-grc1 (CoNLL-U), sanjaya-eng1 (TEI translation), sanjaya-com-eng1 (TEI commentary). Sources/CTS under grcnewxml/data/tlg0019; audits under sanjaya-review. 92,682 glossed tokens, 15,591 dependency segments, 13,915 source line rows, 854 commentary notes. Coverage is partial; 13 rows lack linguistic annotation, 17 lack translation, eight dangling heads are preserved and reported. No Greek change; canonical hashes verified.

Existing gloss/translation/linguistic display code is reused. A small importer extension accepts # pmv_card = BOOK:CARD-LABEL, validated against master intervals. This corrects 163 misrouted segments at lettered/anomalous Greek line labels, without altering token Ref values. Flat plays must keep sent.book=None even when pmv_card says book 1, because alignment_grid.book is null; otherwise every treebank row silently misses deployed shards. Regression tests cover flat and multi-book handling and invalid-card rejection. All 51 tests pass; 22 TEI files validate; rendered translation/commentary words match XML. All 15,591 segments and 92,682 tokens counted in actual deployed shards. All eleven works and viewer index rebuilt.

Review: http://localhost:8000/site/data/tlg0019/sanjaya-review/Review-inventory.html . Opens each play at an annotated passage with Greek, treebank and Sanjaya translation. Commentary is an additional edition choice. Source-manifest.json pins hashes; Line-map.json records exact text mapping. Workspace scripts work/aristophanes-sanjaya reproduce conversion; install.py is one-shot. No UI code changed during this import.
