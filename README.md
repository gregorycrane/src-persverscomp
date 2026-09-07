# src-persverscomp

Build pipeline for the Perseus Multitext Viewer. Unpack this zip's contents
directly into your existing `src-persverscomp/` directory -- it does not
touch `web/` or `work_registry.json`, both of which stay exactly as they are.

## What's in this zip

```
pipeline/            the build pipeline, split out of the old notebook
Makefile              make / make work=<key> / make force / make index / make clean / make test
manifest.json          new, empty -- gets populated on first build
tests/                  a handful of smoke tests (see "Testing" below)
notebooks/archive/       the original notebook, kept runnable
README.md (this file)
```

Not included (left as-is in your existing directory): `web/`,
`work_registry.json`, `lodcache/`, and anything under `WORKSPACE_DIR`
(`persverscomp/`) or `BUILD_DIR` (`/tmp/persvers_build`).

## Building

```
make                    # build every work whose sources changed since the last build
make work=tlg0085.tlg007  # build just one work
make force               # ignore manifest.json, rebuild everything
make index                # rebuild index.html only, from the existing monolith + web/
make clean                 # delete the temp monolith
make test                   # run the test suite
```

If the monolith at `/tmp/persvers_build/corpus_alignment_grid.db` is
missing (fresh clone, or after `make clean`), the next build reconstitutes
it from `site/data/**/*.db` first -- no TEI/treebank re-parsing needed --
then runs the normal manifest-driven pass on top of that.

**Which one to run, by what changed:**

| You changed... | Run |
|---|---|
| a TEI/treebank/alignment source file | `make work=<key>` (or plain `make` to catch everything stale) |
| parser code (`pipeline/parsers/*.py`, `pipeline/treebank/*.py`, etc.) | plain `make` -- `dep_paths_for()` maps each work's own per-edition `parse_mode` to the parser file it actually uses, so a parser-code edit correctly marks every work that depends on it as stale |
| `web/app.js`, `web/styles.css`, or `web/index_shell.html` | `make index` -- these aren't TEI sources, so no work is ever "stale" from editing them; `make force` would only pick the change up by wastefully re-ingesting the entire corpus |
| you're not sure, or want a clean rebuild from scratch | `make force` |

## How this maps to the old notebook

Every cell's logic moved to a specific module; see the module docstrings
for exactly which cell it came from and what (if anything) changed in the
move. In short:

| Old cell | New home |
|---|---|
| Cell 0 (config) | `pipeline/config.py` |
| Cell 1 (WORK_REGISTRY) | `pipeline/registry.py` |
| Cell 4 (parsers + driver loop) | `pipeline/core/`, `pipeline/parsers/`, `pipeline/treebank/{conllu,agdt}.py`, `pipeline/ingest_work.py` |
| Cell 5 (treebank flatten) | `pipeline/treebank/flatten.py` |
| Cell 7 (place references) | `pipeline/places/topostext.py` |
| Cell 9 (sharding) | `pipeline/sharding.py` |
| Cell 10 (index.html builder) | `pipeline/index_builder.py` (WEB_SRC path fix -- see its docstring) |
| Cell 11 (shard loader JS) | not carried over as a Python generator -- see "What I deliberately didn't do" below |
| Cell 12 (lexicon parsers) | `pipeline/lexicon/parsers.py`, `pipeline/lexicon/ingest.py` |
| Cell 13 (lexicon sharding) | `pipeline/lexicon/shard.py` -- **not yet extracted, see below** |
| Cell 14 (treebank QA guard) | `pipeline/treebank/chunking_guard.py` |
| Cell 15 (cleanup) | `pipeline/cleanup.py` |
| *(new)* | `pipeline/manifest.py`, `pipeline/reconstitute.py`, `pipeline/build_all.py` |

The mechanical transform applied throughout Cell 4's driver tail (now
`ingest_work.py`) was: `for work_key, work_meta in WORK_REGISTRY.items():`
became `for work_key in target_keys: work_meta = WORK_REGISTRY[work_key]`.
Everything else in those loop bodies is unchanged from the notebook.

## What I deliberately didn't do

- **`pipeline/lexicon/shard.py` (Cell 13) was not extracted in this pass.**
  Everything else lexicon-related (`parsers.py`, `ingest.py`) is done; I ran
  out of turn budget before getting to the sharding step. It's a much
  smaller, more self-contained cell than Cell 4 or Cell 9 -- straightforward
  to pull over the same way the others were.
- **`sharding.py`'s `split_corpus_by_work` was moved verbatim, not made
  work-selective.** It still re-shards the entire monolith (and rebuilds
  `catalog.json`) on every call, even when `build_all.py` only just
  ingested one work. I didn't trace far enough into its ~400 lines to be
  confident a partial-shard filter wouldn't quietly break `catalog.json`'s
  cross-work aggregation, so `build_all.py` calls it unfiltered for now.
  Sharding a persistent monolith is still much cheaper than re-parsing TEI,
  so this is a real but bounded inefficiency, not a correctness risk.
- **Cell 11's `SHARD_LOADER_JS`** (a Python string constant that gets
  written out as `shard_loader.js`) wasn't ported into the package as-is.
  Since you asked not to touch `web/`, and the cleanest fix is to make
  `shard_loader.js` a real static file under `web/` rather than a generated
  string, I left this alone rather than either modifying `web/` or
  preserving an awkward string-constant generator. Worth a short follow-up
  once you're ready to touch `web/`.

## What's actually been verified, and what hasn't

This section has a real story worth being honest about, because it changed
twice during this split -- both times because something was actually run,
not because I re-reasoned about it harder.

**Round 1.** After the first `make` run hit a `NameError: WORK_REGISTRY`
(missing import in `ingest_work.py`), I wrote an AST-based checker that
flags any name a function uses but that's never defined anywhere in its
file, filtered to exclude closures. It found 54 real missing imports across
~14 files -- names that were kernel-globals in the notebook (`WORK_REGISTRY`,
`TEXTGROUP_NAMESPACE`, `build_poetry_canonical_intervals`, plain missing
`re`/`os`/`json`/`OrderedDict`) that I hadn't consistently re-imported when
writing each module's header, plus two real scoping bugs
(`global_sort_index` and `_pending_metrical`/`WORK_HAS_BOOKS` needed
explicit initialization as function-locals instead of relying on
notebook-kernel-global state). I fixed all 54, the checker reported clean,
and I claimed the package was "structurally solid."

**Round 2.** The very next real run (`make work=tlg0085.tlg007`) crashed
again -- same class of bug, `OrderedDict` undefined in `poetry_cards.py`,
a file my own checker had just cleared. The checker itself had a bug: it
treated `OrderedDict` inside `data.setdefault(bk, OrderedDict())[label] = …`
as a *binding* rather than a *use*, because it naively walked every AST node
inside an assignment target instead of checking whether each Name was
actually in a Store or Load context. That's a real category of Python
expression (a call nested inside a complex assignment target) that a naive
target-walk gets backwards. I rewrote the checker to use Python's own
Store/Load/Del context markers instead of hand-rolled target-walking, reran
it, and it found 2 more real instances of the exact same missing-import
pattern (`card_prose.py`, `line_commentary.py`) that round 1's checker had
also missed for the same reason. All fixed. The only thing the v2 checker
still flags is `chunking_guard.py`'s `WORK_HAS_BOOKS` -- a deliberate,
documented pattern (`run_chunking_guard` sets it via `global` before calling
`_chset_from_conllu`), not a bug.

More importantly: I'd claimed "structurally solid" after a synthetic
end-to-end test that used an *empty* fake work registry -- which meant it
never actually called a single parser, so it couldn't have caught this
class of bug no matter how clean the checker said things were. I've since
added `tests/test_ingest_work_e2e.py`, which runs a real (minimal) TEI
fixture (`tests/fixtures/poetry_cards_minimal.xml`) through the actual
`doc_type=poetry_cards` dispatch path -- the same path that crashed for
you -- and asserts on the real parsed output (card intervals, rendered
HTML). It passes, and it's now part of the permanent suite specifically so
this class of bug gets caught by `make test` next time, not by your next
real build.

**What that does and doesn't cover.** One parser (`poetry_cards`) now has
real fixture coverage; the other seven `doc_type`s
(`card_prose`, `milestone`, `reading_lines`, `hierarchical`,
`speech_collection`, `book_chapter_section`, `line_commentary`, plus the
treebank/lexicon/place-reference paths) still don't -- they compile and
pass the static checker, but nothing has actually called them with real
input. Given the round-1 → round-2 pattern, I'd treat "the checker is
clean" as necessary but not sufficient, and I'd genuinely expect other
`doc_type`s to surface their own version of this if you hit them before I
add fixtures for them. If a work with a different `doc_type` throws next,
that's the most likely shape of bug, and it's a fast fix once you show me
the traceback.

**Round 3.** You sent your real `work_registry.json` so I could suggest which
work_keys to try next -- and cross-referencing it against the code surfaced
a real gap that had nothing to do with a crash: `build_all.py`'s
`dep_paths_for()` (which decides whether editing a parser's *code* should
count as making a work stale) keyed off `meta.get("doc_type")`, a field that
doesn't exist anywhere in a real `work_registry.json` -- dispatch is
per-edition `parse_mode` (`poetry_cards`, `card_prose`, etc.), and one
work_key routinely mixes several across its editions/translations/
commentaries. So this always returned `None`, meaning a fix to, say,
`parse_poetry_cards_tei` would silently NOT invalidate any poetry_cards
work's manifest entry -- only `make force` would ever pick it up. Fixed:
`dep_paths_for()` now walks each entry's own `parse_mode` (and each
treebank's own `parse_mode`, `conllu` vs `agdt_xml`) and maps it to the
right parser file via a corrected `PARSE_MODE_PARSERS` registry (the old
`DOC_TYPE_PARSERS` had the wrong key strings too -- `"milestone"` where the
real data says `"milestones"`, `"speech_collection"` where it says
`"speech_collection_sentences"` -- dead code that never matched, though the
actual *ingestion* dispatch in `ingest_work.py` was always correct, since
that's a straight if/elif chain unrelated to this lookup table). Verified
against your real registry: `dep_paths_for()` now correctly resolves e.g.
`tlg0001.tlg001` → `{poetry_cards.py, card_prose.py, line_commentary.py,
conllu.py}` (it mixes all three edition parse_modes plus a treebank), and
`tlg0003.tlg001` (no `parse_mode` on its entries) → `{hierarchical.py}`,
matching the real fallback. Added `tests/test_dep_paths_for.py` to keep
this covered -- real `work_registry.json` isn't part of this repo (it's
your build-only data), so that test uses a synthetic-but-representative
multi-parse_mode work instead.

This doesn't affect the correctness of anything that's already run for
you -- it only affects whether a *future* parser-code edit gets picked up
by plain `make` (now: yes) or silently required `make force` (before: yes,
always). Worth knowing about if you've been assuming `make` alone would
catch a parser fix.

## Testing

```
make test          # needs pytest: pip install pytest --break-system-packages
```

`tests/test_norm_key.py` and `tests/test_storage_table_classification.py`
both caught real bugs during this split (a bad test assumption about
sigma-folding, and an unclassified internal SQLite table) -- worth keeping
this pattern going as more parsers get fixture-driven tests.