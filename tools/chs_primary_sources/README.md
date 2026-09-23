# CHS Primary Sources converter

`convert.py` converts a Center for Hellenic Studies Primary Sources drama page
to CTS-compatible TEI for Perseus MVP. It preserves speaker and stage structure,
bold or plain-text source line markers, and italicized transliterated Greek as
`<term xml:lang="grc-Latn">`. A companion JSON concordance records every marked
term, its source passage, local context, and both a conservative bracket-gloss
and the fuller preceding English phrase when the page supplies one.

Example:

```sh
python3 tools/chs_primary_sources/convert.py \
  --url https://chs.harvard.edu/primary-source/aeschylus-eumenides-sb/ \
  --input-html /path/to/snapshot.html \
  --canonical /path/to/tlg0085.tlg007.perseus-grc2.xml \
  --urn urn:cts:greekLit:tlg0085.tlg007.chs-smyth-bannon-nagy-eng1 \
  --output /path/to/tlg0085.tlg007.chs-smyth-bannon-nagy-eng1.xml \
  --terms /path/to/tlg0085.tlg007.chs-smyth-bannon-nagy-eng1.terms.json
```

The canonical edition is used only to recover the opening line of a speech that
begins between printed line markers. The source HTML remains the authority for
the English wording and marked terms.

`convert_pausanias.py` handles the CHS *Pausanias Reader*. In addition to the
term concordance, it preserves the three-level book/chapter/section citations,
displayed quotations, source attributions, and notes. A displayed quotation
followed by the source site's `bibl` block becomes
`<cit type="block"><quote rend="blockquote">…</quote><bibl
rend="right">…</bibl></cit>`.

```sh
python3 tools/chs_primary_sources/convert_pausanias.py \
  --url https://chs.harvard.edu/primary-source/a-pausanias-reader-in-progress-description-of-greece-scrolls-1-10/ \
  --input-html /path/to/chs-pausanias-reader-2018.html \
  --urn urn:cts:greekLit:tlg0525.tlg001.chs-nagy2018-eng1 \
  --output /path/to/tlg0525.tlg001.chs-nagy2018-eng1.xml \
  --terms /path/to/tlg0525.tlg001.chs-nagy2018-eng1.terms.json
```
