# persverscomp: Technology Summary for Migration to Tufts Infrastructure

## The big picture

This is a **100% static, "serverless" application** by explicit design (stated directly
in the build notebook's Cell 2 architecture note):

> *No server, no Range requests, no per-file header tuning — so it runs identically
> on GitHub Pages, on Tufts nginx, or on a laptop behind any static file server.
> Moving hosts is a copy + (optional) header config.*

All the "computation" — SQL queries, treebank rendering, lexicon lookups, diff/alignment
logic — happens **in the browser**, via a WebAssembly build of SQLite (sql.js) querying
per-work SQLite files fetched whole over plain HTTP. There is no database server, no
application server, and no server-side code anywhere in this stack. So the migration to
Tufts infrastructure is fundamentally a file-copy job, not a re-architecture — *unless*
you also want the one capability the design notes explicitly flag as unsolved
(corpus-wide search).

---

## (1) What Tufts needs to provide

### Minimum (to replicate what GitHub Pages does today)

- **A static file server** (nginx, Apache, or Tufts' existing web hosting) that can
  serve a directory tree of files as-is: `.html`, `.css`, `.js`, `.json`, `.db`, `.png`.
  - Only needs to serve whole files — no Range-request/byte-serving support required.
    That's a deliberate design choice: sharding keeps every file small enough to fetch
    in full (`resp.arrayBuffer()`), specifically to avoid the complexity (and GitHub
    Pages' gzip-on-HEAD quirk) that a partial-fetch approach like `sql.js-httpvfs`
    would need.
  - No particular MIME-type configuration is required for `.db` files — `fetch()`
    doesn't care about `Content-Type`; browsers just read bytes. Correct types for
    `.html`/`.css`/`.js`/`.json` are good hygiene but not load-bearing.
- **HTTPS.** Two libraries are pulled from third-party CDNs at runtime
  (`cdnjs.cloudflare.com` for sql.js/WASM, `cdn.jsdelivr.net` for `marked.js`, though
  the latter looks currently unused in `app.js` — worth double-checking whether it's
  dead weight). If the Tufts-hosted page itself is HTTPS, those CDN pulls need to stay
  HTTPS too, or the browser will block them as mixed content.
- **Storage capacity** for the full corpus of shard files. Sharding currently targets
  GitHub's 100MB-per-file hard cap (splitting works book-wise to stay under ~95MB);
  that ceiling is GitHub-specific and could be relaxed on Tufts' own server (fewer,
  larger shards), though there's no requirement to change it.
- **No database server, no app server, no auth layer** — none of that exists today and
  none is needed for parity with the current GitHub Pages deployment.
- **Same-origin serving** (app + data shards from the same host) avoids any CORS
  configuration. If Tufts ever splits data (e.g., `.db` shards) onto a separate
  host/subdomain from the app itself, `Access-Control-Allow-Origin` headers would need
  to be added — not needed if it's all one static tree.

### Worth deciding on, not strictly required

- **Self-hosting the two CDN dependencies** (sql-wasm.js + its `.wasm` binary, and
  `marked.min.js`) on Tufts' own infrastructure instead of `cdnjs`/`jsdelivr`. This buys
  independence from third-party CDN uptime and sidesteps any campus network policy that
  blocks external CDNs — currently the single external dependency for an otherwise
  self-contained app.
- **A build environment** (Python 3 + `sqlite3` + `xml.etree.ElementTree`, run via the
  Jupyter notebook) to regenerate `site/` from the TEI/CoNLL-U sources whenever content
  changes. This can run anywhere — it doesn't need to live on the serving
  infrastructure — but if Tufts wants to own recurring rebuilds rather than Gregory
  running them locally, they'd need this environment plus access to the source XML
  files. Note: some source paths are currently hardcoded absolute paths on Gregory's
  own machine (e.g. the Bétant lexicon source), so centralizing the build on Tufts
  infrastructure would mean relocating those sources too.
- **If/when corpus-wide search across all ~2,700 works is wanted:** the notebook's own
  design doc flags this as the one thing the static-shard architecture *can't* do (you
  can't fan a query across thousands of separate shard files client-side). That would
  need a precomputed inverted index and, per the notebook's own words, "may reintroduce
  a backend and a security surface" — i.e., an actual server-side service, a genuinely
  different infrastructure ask than static hosting. Not needed today; worth flagging now
  since it's the one seam in the "just copy files" story.

---

## (2) Dependencies on the user's side (browser)

Everything below is required in the visitor's browser, not on Tufts' servers:

- **WebAssembly support** — required, to run sql.js (SQLite compiled to WASM).
  Universal in any browser from the last several years.
- **Fetch API** — used throughout for loading `catalog.json`, `lexica.json`, and every
  shard (`resp.arrayBuffer()`), no fallback to older XHR patterns.
- **Modern JavaScript (ES2017+)** — `async`/`await` is used pervasively, plus optional
  chaining (`?.`), template literals, `Map`/`Set`, arrow functions, destructuring. This
  rules out IE11 and very old mobile browsers, but is fine on any current Chrome/
  Firefox/Safari/Edge, including recent mobile versions.
- **CSS3, including CSS Grid and Flexbox** — the poetry line-number layout, the token
  detail panel, and the multi-column reading grid all use `display: grid`; column
  layout elsewhere uses flexbox.
- **Inline SVG rendering** — the treebank's dependency-tree diagrams are generated as
  raw `<svg>` markup and injected into the DOM directly.
- **`localStorage`** — used for a handful of small persisted preferences (layout mode,
  expanded author lists in the splash screen, the Hide-Latin toggle). Not
  critical-path: if a browser has it disabled, the app still works, it just won't
  remember those preferences between visits.
- **No login, no cookies, no plugins** — it's a fully anonymous, static read path today.
- **System fonts for polytonic Greek / Perso-Arabic script** — worth flagging as a gap
  rather than a strength: the CSS references `"Gentium Plus"`, `"GFS Didot"`,
  `"Scheherazade New"`, `"Noto Naskh Arabic"` by name, but there's no `@font-face`
  declaration or webfont CDN link anywhere in the stylesheet or shell. Rendering
  quality (correct polytonic diacritic placement, proper Arabic/Persian shaping)
  depends entirely on whatever's installed on the visitor's OS; without those fonts,
  browsers fall back to generic serif/sans-serif, which is still legible but loses
  some of the intended typographic precision. This would be a natural thing to fix as
  part of a Tufts migration — bundling proper web fonts (self-hosted or via a font CDN)
  rather than leaving it to chance.
- **Reachability of the two external CDNs** (`cdnjs.cloudflare.com`, `cdn.jsdelivr.net`)
  from the visitor's network — a campus firewall or ad-blocker that blocks either would
  break the app for that user, which is the flip side of the "self-host these"
  suggestion above.
- **Device memory/CPU headroom** — since all querying happens client-side via
  in-memory WASM SQLite, opening a work loads its shard (up to ~95MB by current design)
  fully into browser memory; the parallel-grid view can have up to 7 columns open
  simultaneously, each potentially a different work/shard. Not a blocker on typical
  desktop/laptop hardware, but worth keeping in mind for lower-end or mobile devices if
  usage patterns lean that way.
