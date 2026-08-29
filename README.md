# Perseus Version Comparison — Build Source

This repository contains the source data registry, browser application source, and notebook-based build pipeline for the [Perseus Version Comparison runtime](https://github.com/gregorycrane/persverscomp).

The two repositories have different roles:

| Repository | Role |
| --- | --- |
| `src-persverscomp` (this repository) | Source configuration and build logic. Edit and run the build here. |
| `persverscomp` | Generated, runnable static site. Serve or deploy that repository. |

## What the build produces

The pipeline combines CTS-addressable texts and annotations into a browser-based comparison environment with:

- editions, translations, and commentaries displayed in parallel;
- structural, line, and token alignment data;
- treebank sentences, tokens, speakers, and metrical annotations;
- place references and map data;
- work-specific and general lexica;
- per-work SQLite shards queried in the browser through WebAssembly; and
- generated catalogs and a self-contained front-end entry page.

The deployed system has no application server or database daemon. Its generated SQLite databases are read-only static assets.

## Important files and directories

| Path | Purpose |
| --- | --- |
| `perseus-urn-cts-scalable-5col-v97.ipynb` | Current build notebook and canonical pipeline entry point. |
| `work_registry.json` | Registry of works, versions, annotations, parsing modes, and local source paths. |
| `web/index_shell.html` | HTML shell used to generate the runtime `index.html`. |
| `web/styles.css` | Reader styling embedded into the generated page. |
| `web/app.js` | Reader application code embedded into the generated page. |
| `lodcache/` | Cached and supporting data used to ingest place references. |
| `OldMaterials/` | Historical notebooks and documentation; not the current build source. |

## Requirements

- Python 3 with the standard `sqlite3` module
- JupyterLab or Jupyter Notebook
- [`lxml`](https://lxml.de/) for XML processing
- Enough free disk space for the temporary monolithic database and generated shards
- Local copies of every source file named in `work_registry.json` and the notebook's lexicon registry
- A writable checkout of `persverscomp`

The build currently expects these local paths:

```text
/Users/gcrane/github/src-persverscomp
/Users/gcrane/github/persverscomp
/tmp/persvers_build
```

To use different checkouts, update `SRC_DIR`, `WORKSPACE_DIR`, and `BUILD_DIR` in the notebook before running the pipeline.

## Configure the corpus

`work_registry.json` is the main corpus manifest. Each work identifies its CTS textgroup and work IDs, then lists the available editions, translations, commentaries, treebanks, metrics, alignments, and related resources. Entries also specify how a source should be parsed.

Current parsing modes include:

- `agdt_xml`
- `book_chapter_section`
- `card_prose`
- `conllu`
- `line_commentary`
- `milestones`
- `poetry_cards`
- `reading_lines`
- `speech_collection_sentences`

Paths in the registry are local build inputs, often absolute paths. The registry therefore belongs in this source repository and is not a deployable runtime asset.

Lexicon sources are currently registered in the notebook rather than in `work_registry.json`. Verify those paths as well before rebuilding.

## Build the runtime

1. Update `work_registry.json`, the source documents, or the files under `web/`.
2. Open `perseus-urn-cts-scalable-5col-v97.ipynb` from this repository.
3. Confirm the source, runtime, temporary-build, lexicon, and place-data paths.
4. Run the populated cells from top to bottom. Cell order matters.
5. Review the validation and row-count output for missing versions, malformed citations, oversized shards, or incomplete annotations.
6. Inspect the changes in the sibling `persverscomp` repository before committing or deploying them.

The important pipeline order is:

1. create and populate the temporary monolithic database;
2. flatten treebank sentences into token rows;
3. ingest place references and other supplemental data;
4. split the corpus into work- and book-aware shards and write `catalog.json`;
5. build the runtime `index.html` from the three files under `web/`;
6. generate the shard loader;
7. ingest and shard the lexica, writing `lexica.json`; and
8. run final guards before deleting the temporary monolith.

Do not run the cleanup cell until all corpus and lexicon shards have been written. If the monolith is deleted too early, rerun the preceding build and ingestion cells before sharding again.

## Generated output

The notebook writes into the sibling `persverscomp` checkout:

| Output | Description |
| --- | --- |
| `index.html` | Compiled reader containing the HTML shell, CSS, JavaScript, and generated registry data. |
| `.nojekyll` | Prevents GitHub Pages from processing the static output with Jekyll. |
| `site/catalog.json` | Work, author, version, annotation, book, and shard metadata. |
| `site/data/**/*.db` | Read-only SQLite corpus shards. |
| `site/data/lexica/*.db` | Read-only lexicon shards. |
| `site/lexica.json` | Lexicon metadata and textgroup-to-lexicon mappings. |
| `site/shard_loader.js` | Browser loader for catalogs and SQLite shards. |

The intermediate monolithic database is created at `/tmp/persvers_build/corpus_alignment_grid.db`. It is a build artifact, not part of the deployed site, and the notebook can remove it after all dependent stages have completed.

Large works may be divided at ancient book boundaries. The browser downloads all parts required for the selected work and combines their query results in memory. The build aims to keep individual files comfortably below GitHub's 100 MB file limit.

## Editing guidance

- Make front-end changes in `web/index_shell.html`, `web/styles.css`, or `web/app.js`, then rebuild. Do not treat the generated runtime `index.html` as the source of truth.
- Keep local source paths and parsing instructions in `work_registry.json`; do not copy that file into the public runtime.
- Treat `OldMaterials/` and notebook checkpoint directories as reference material only.
- The notebook currently regenerates the runtime repository's `README.md`. If that embedded README text is not updated at the same time, a full rebuild can replace later manual README edits.

## Testing a generated build

Because the application fetches JSON, SQLite, and WebAssembly assets, test it through an HTTP server rather than by opening `index.html` as a `file://` URL:

```bash
cd /Users/gcrane/github/persverscomp
python3 -m http.server 8000
```

Then open `http://localhost:8000/` and verify several works, including a multipart work and works with commentary, treebank, place, and lexicon data.

## Troubleshooting

- **A source file is missing:** check the absolute paths in `work_registry.json` and the lexicon registry in the notebook.
- **The build uses stale state:** restart the notebook kernel and rerun the populated cells from top to bottom.
- **A work is absent from the catalog:** confirm that its registry entry is enabled, its input parsed successfully, and the sharding cell completed.
- **The site fails when opened directly:** use a local HTTP server; browser security rules commonly block `fetch` and WebAssembly from `file://` pages.
- **A shard is too large:** review the work's citation hierarchy and book boundaries so the sharding stage can split it safely.

## Licensing

No repository-level license file is currently present. Add or identify the applicable code and data licenses before redistributing material outside the project's existing terms.
