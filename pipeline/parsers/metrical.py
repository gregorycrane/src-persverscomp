"""Metrical-annotation TSV parser. Relocated from Cell 4."""
import os
import csv

def parse_metrical_tsv(path):
    """Parse a tab-separated metrical annotation file.

    Each row: URN_REF<TAB>WORD<TAB>START<TAB>END<TAB>SCANSION<TAB>HEMI[<TAB>TAG...]
    Returns a dict: { "BOOK.LINE": [ {word, start, end, hemi, syls, tags}, ...] }
    where syls = [ {q: "long"|"short"|"onset", text: str}, ...]
    and mora positions 1-24 encode metrical weight (long=2, short=1).
    """
    import re
    if not os.path.exists(path):
        print(f"  ✗ Metrical file not found: {path}")
        return {}
    lines_data = {}
    with open(path, 'r', encoding='utf-8') as fh:
        for raw in fh:
            raw = raw.rstrip('\n')
            if not raw or raw.startswith('#'):
                continue
            parts = raw.split('\t')
            if len(parts) < 6:
                continue
            urn_ref  = parts[0]   # e.g. tlg001:1.1
            word     = parts[1]
            try:
                start = int(parts[2]); end = int(parts[3])
            except ValueError:
                continue
            scansion = parts[4]
            hemi     = parts[5]
            tags     = [t for t in parts[6:] if t]

            # Extract BOOK.LINE reference
            ref = urn_ref.split(':')[1] if ':' in urn_ref else urn_ref
            # Strip a zero-padded book prefix ("01.5" -> "1.5") so it matches
            # the edition's own unpadded book numbering (master_intervals'
            # book keys come from the TEI div's bare @n, e.g. "1" not "01").
            if '.' in ref:
                _bk, _rest = ref.split('.', 1)
                if _bk.isdigit():
                    ref = f"{int(_bk)}.{_rest}"

            # Parse syllables from scansion string
            syls = []
            for tok in re.split(r'(?=(?:long|short)-)', scansion):
                if not tok:
                    continue
                if tok.startswith('long-'):
                    syls.append({'q': 'long',   'text': tok[5:].rstrip('-')})
                elif tok.startswith('short-'):
                    syls.append({'q': 'short',  'text': tok[6:].rstrip('-')})
                else:
                    syls.append({'q': 'onset',  'text': tok.rstrip('-')})

            word_obj = {'word': word, 'start': start, 'end': end,
                        'hemi': hemi, 'syls': syls, 'tags': tags}
            lines_data.setdefault(ref, []).append(word_obj)
    return lines_data
