# Potter Sophocles OCR repair

`rebuild_sophocles.py` repairs one of Robert Potter's seven Sophocles
translations from the combined HathiTrust OCR witness.

The repair is intentionally review-first. It writes a new XML file and a JSON
audit rather than editing the canonical source in place. The audit records
removed prose intrusions, line joins, restored source notes, note anchors, and
any remaining lowercase-start or one-word verse lines.

Example:

```bash
python3 tools/potter1788/rebuild_sophocles.py \
  /path/to/tlg0011.tlg001.potter1788-eng1.xml \
  /tmp/tlg0011.tlg001.potter1788-eng1.xml \
  /tmp/tlg0011.tlg001.audit.json \
  --ocr /path/to/sophocles-potter-hathi.txt
```

The seven canonical XML files remain in `grcnewxml/data/tlg0011/`; this tool
belongs here because `src-persverscomp` owns the ingestion and repair tooling,
not the source texts.
