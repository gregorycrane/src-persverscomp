# ŠKZ source bridge

This directory vendors the text datasets needed to build the trilingual
inscription of Šābuhr I at the Kaʿba-ye Zartošt in the Perseus Multitext
Viewer. The files under `upstream/` are unchanged from
[`farnoosh-shamsian/SKZ`](https://github.com/farnoosh-shamsian/SKZ) at the
commit recorded in `upstream/UPSTREAM_COMMIT` and remain licensed under
CC BY-SA 4.0.

Run:

```bash
python3 tools/skz/build_pmv_sources.py
make work=skz.inscription
```

The converter writes four line-aligned TEI witnesses, two PMV token-alignment
files (Greek–Parthian and Greek–Middle Persian), and
`lodcache/citations_skz.csv` for PMV's map. The Parthian transliteration is a
fourth reading column; the upstream word-pair table aligns the Greek text to
the Parthian and Middle Persian transcriptions.
