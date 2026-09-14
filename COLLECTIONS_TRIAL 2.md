# Aeschylus collections trial

This branch adds an optional collection browser to the existing work picker.
The ordinary UI is the default. Enable with `?collections=1`; disable with
`?collections=off` or the visible **Turn off experiment** link. The switch
uses only the URL, not persistent storage.

## What is implemented

- A Fragments collection row alongside Aeschylus' surviving plays.
- A combined works view and two collection memberships for the same records.
- Individual work pages, fragment navigation, verse search, and separate
  transmitting/editorial context, sourced from regions of one XML document.
- Metadata-only display where the selected play has no encoded verses.
- An isolated preview builder that reads the existing monolith in read-only
  mode and writes only to an explicitly selected output directory.

This is an experimental collection reader, not yet a SQLite shard importer.
The new works do not participate in the existing global corpus search,
alignment grid, lexica or multi-edition comparison tools. Existing plays retain
their ordinary reading routes. The trial is not a production CTS registration.

## Editorial scope

75 play containers and their 281 directly contained numbered fragments are
included. The 185 numbered fragments outside those containers are excluded,
with the limitation shown in the UI. These are markup counts, not a settled
work inventory. Six containers have no encoded lines. The source is not
proofread or reattributed. Line references are derived by order within each
fragment. Only direct fragment/lg/l content is searched; contextual prose is
retained separately. Editorial authenticity requires further review.

## Local preview

Run tools/preview_collections.py with --source and --output. The existing
viewer assets and monolith are read only. The preview serves on 127.0.0.1:8001,
leaving the original viewer on port 8000 alone. Stop with Ctrl-C.

## Rollback

1. For the visible experiment, click **Turn off experiment**.
2. For the whole trial, close its page and stop its preview server with Ctrl-C.
3. Return to the original viewer. Its repository, sources and shards were not
   modified, so no restore or database rollback is necessary.
4. The isolated branch can simply be retained or discarded later. Do not reset
   or clean the user's original repositories to undo this trial.

## Validation

61 tests passed, including source-region identity, collection memberships,
context exclusion, metadata-only works and unchanged source bytes. Both
JavaScript files pass syntax checks. The complete preview index was built
using the existing read-only monolith. Browser visual and navigation checks
remain unverified: this session prohibited starting a listening server and
its browser prohibited file:// navigation.


## PMV integration update

The trial now materializes 69 per-work PMV shards with 281 fragment cards. Collection links open the standard PMV reader with cols=1. Text and context are stacked in one column; the navigation label is Fragments. Six metadata-only play headings retain their evidence pages. No translations, treebanks or metrical data were created. This supersedes the earlier statement that no shard importer exists. The shared XML and original monolith remain unchanged; the preview builds a temporary union view for index generation and writes new shards only below the preview directory. Search on the collection page still isolates the authorial verse layer; no production global search index has been rebuilt. Work identifiers remain experimental.

Browser-verified: Aigyptioi loads in PMV, Danaides navigates from fragment 43 to 44, and only the Focus column is visible with sources and notes beneath the Greek. The Fragments toolbar link returns to the collection.
