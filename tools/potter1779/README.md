# Robert Potter's Aeschylus (1779)

The seven corrected TEI translations used by the Perseus Multitext Viewer
belong in `grcnewxml/data/tlg0085/tlgNNN/`. `work_registry.json` points to
those canonical corpus files; this directory contains only the repair tool.

`rebuild_remaining.py` rebuilds the six plays other than *Eumenides* from an
existing Potter TEI file and the corresponding HathiTrust OCR export.  It
joins lowercase continuations and one-word wraps, removes catchwords and OCR
debris, repairs page-split notes, restores missing note anchors, renumbers the
verse lines, and writes a JSON audit beside a review copy.  It never overwrites
its input file. Review output should be installed in the corresponding
`grcnewxml` work directory, not stored in this build-pipeline repository.

Example:

```sh
python3 tools/potter1779/rebuild_remaining.py \
  INPUT.xml OUTPUT.xml AUDIT.json --ocr HATHITRUST_OCR.txt
```

The generated TEI should be reviewed and validated before replacing the
corresponding file in `grcnewxml`, followed by `make work=tlg0085.tlgNNN`.
