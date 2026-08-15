"""
ToposText place-citation ingestion — v0, scoped to Thucydides, Iliad, Agamemnon.

WHAT THIS DOES
--------------
Reads ToposText's "places with citations from ancient texts" download
(World Historical Gazetteer / Linked Places format, JSON-LD) and produces
one row per (work, citation, place) triple for the three works we're
starting with, ready to load into a new `place_references` shard table
alongside your existing treebank_sentences / metrical_lines tables.

BEFORE RUNNING THE REAL INGEST: run step 0 first. I have NOT been able to
fetch and inspect the actual 9MB file (topostext.org/downloads/
ToposTextGazetteer.jsonld) from my environment, so the field names below
are my best inference from the Linked Places Format spec + what ToposText's
own work pages show (each tagged paragraph resolves to a CTS-style passage
URI like urn:cts:greekLit:tlg0085.tlg005.perseus-grc1:8). Step 0 prints the
real shape of a few records so we can fix CITATION_ID_FIELD / the regexes
below before trusting any of the counts in step 2.

Usage:
    python3 topostext_ingest.py inspect  <path-to-jsonld>   # step 0
    python3 topostext_ingest.py dump     <path-to-jsonld>   # step 0b -- full raw features, when inspect's field guess is wrong
    python3 topostext_ingest.py find_key <path-to-jsonld> [key]   # step 0c -- does this key exist ANYWHERE (default key: "citations")
    python3 topostext_ingest.py ingest   <path-to-jsonld>   # step 1+2
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field

# Characters that LOOK like whitespace (often copy-pasted in from formatted
# text/PDFs/spreadsheets) but which JSON's grammar does NOT recognize as
# whitespace -- only U+0020, U+0009, U+000A, U+000D are legal separators
# between JSON tokens. Anything in this set sitting between a number and
# its delimiter (e.g. inside a coordinates array) silently breaks the
# tokenizer with a confusing "Expecting ',' delimiter" error that has
# nothing to do with quoting. Safe to blanket-replace with a plain space
# anywhere in the file: none of these have legitimate meaning inside JSON
# structure, and they're vanishingly unlikely to be intentional inside a
# real word in a place name or label.
UNICODE_WS_RE = re.compile(
    "[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\u200b\ufeff]"
)


def normalize_unicode_whitespace(text):
    return UNICODE_WS_RE.sub(" ", text)

# ----------------------------------------------------------------------
# Config: the three works we're starting with.
#
# citation_depth is descriptive only (for the roll-up matcher on the app
# side); it does not change how this script parses ToposText's data.
# ----------------------------------------------------------------------

WORKS = {
    "tlg0003.tlg001": dict(name="Thucydides", textgroup="tlg0003", work="tlg001",
                            topostext_work_id=52, citation_depth="book.chapter"),
    "tlg0012.tlg001": dict(name="Iliad",       textgroup="tlg0012", work="tlg001",
                            topostext_work_id=2,  citation_depth="book.line"),
    "tlg0085.tlg005": dict(name="Agamemnon",   textgroup="tlg0085", work="tlg005",
                            topostext_work_id=12, citation_depth="line"),
}

# Matches a CTS-style passage citation string anywhere it appears, e.g.
#   "urn:cts:greekLit:tlg0085.tlg005.perseus-grc1:8"
#   "urn:cts:greekLit:tlg0003.tlg001.perseus-grc2:1.1"
# Captures (work_urn, passage_citation).
CTS_PASSAGE_RE = re.compile(
    r"urn:cts:greekLit:((?:tlg\d+\.tlg\d+))(?:\.[\w-]+)?:([\d.]+)"
)

# Fallback: a topostext.org/work/<id>#<para> or similar anchor style, in
# case the LOD export references its own site rather than CTS URIs.
TOPOSTEXT_ANCHOR_RE = re.compile(r"topostext\.org/work/(\d+)[/#]?(\d[\d.]*)?")


@dataclass
class PlaceReference:
    textgroup: str
    work: str
    citation: str          # raw citation string, e.g. "1.1" or "810"
    place_id: str
    place_name: str
    lat: float
    lon: float
    source: str = "topostext"


def repair_unescaped_quotes(path, max_fixes=2000):
    """Automatically repairs the most common failure mode in these large
    LOD/gazetteer exports: a free-text field (label/description) contains
    a literal straight double-quote that should have been escaped as \\",
    e.g.  "label": "the "Dark Age" period"
    which makes the JSON parser think the string ends right after the
    first embedded quote, then chokes on the leftover text with
    'Expecting , delimiter' (or a similar message) pointing at the
    character right after that quote.

    Strategy: on each such error, back up from the reported error
    position to the nearest '"' (skipping only whitespace), escape it in
    place, and re-parse from scratch. Repeat until it parses clean or we
    hit max_fixes. Each retry is a full re-parse, so this is O(n * fixes)
    -- fine for a one-off cleanup of a multi-MB file (seconds to at most
    a couple of minutes), and we cache the repaired text to disk so
    later runs (ingest, re-inspection) don't pay this cost again.
    """
    repaired_path = path + ".repaired.jsonld"
    if os.path.exists(repaired_path):
        print(f"Using cached repaired file: {repaired_path}")
        with open(repaired_path, encoding="utf-8") as f:
            return json.loads(f.read())

    with open(path, encoding="utf-8-sig") as f:
        text = f.read()

    text = normalize_unicode_whitespace(text)
    try:
        data = json.loads(text)
        print("Fixed by Unicode-whitespace normalization alone -- no "
              "quote-escaping needed.")
        with open(repaired_path, "w", encoding="utf-8") as f:
            f.write(text)
        return data
    except json.JSONDecodeError:
        pass  # fall through to the quote-repair loop below

    fixes = 0
    while True:
        try:
            data = json.loads(text)
            break
        except json.JSONDecodeError as e:
            if fixes >= max_fixes:
                print(f"Hit max_fixes ({max_fixes}) without a clean parse. "
                      f"Stopping -- this may not be the unescaped-quote "
                      f"pattern after all; see the error below.")
                raise
            pos = e.pos
            # Back up over whitespace to find the actual offending
            # character, then confirm it's the quote we expect just
            # before it.
            j = pos - 1
            while j > 0 and text[j] in " \t\r\n":
                j -= 1
            # The quote that wrongly closed the string should be at or
            # very near this position (walk back to the nearest quote).
            k = j
            while k > 0 and text[k] != '"':
                k -= 1
            if text[k] != '"':
                print(f"Could not locate an unescaped quote near offset "
                      f"{pos} (error: {e}). Falling back to manual "
                      f"diagnosis -- re-raising.")
                raise
            # Escape it: insert a backslash immediately before this quote,
            # but only if it isn't already escaped (defensive check).
            if k == 0 or text[k - 1] != "\\":
                text = text[:k] + "\\" + text[k:]
                fixes += 1
            else:
                # Already escaped -- something else is wrong; don't loop
                # forever on the same spot.
                print(f"Quote at offset {k} is already escaped but parse "
                      f"still fails at {pos} -- stopping for manual "
                      f"diagnosis.")
                raise

    print(f"Repaired {fixes} unescaped-quote occurrences. "
          f"Caching to {repaired_path} for future runs.")
    with open(repaired_path, "w", encoding="utf-8") as f:
        f.write(text)
    return data


def diagnose_raw(path, error=None):
    """Runs BEFORE attempting a full json.load. Figures out whether the
    file is a single JSON document, newline-delimited JSON (one object
    per line -- common for large gazetteer/LOD exports), or something
    truncated/corrupted, and prints enough context to tell which.
    """
    import os
    size = os.path.getsize(path)
    print(f"file size: {size:,} bytes")

    with open(path, "rb") as f:
        head = f.read(200)
        f.seek(max(0, size - 200))
        tail = f.read(200)
    print(f"first 200 bytes: {head!r}")
    print(f"last 200 bytes:  {tail!r}")

    # Check for a BOM, since that alone can break naive json.load in some
    # python versions/encodings.
    if head.startswith(b"\xef\xbb\xbf"):
        print("NOTE: file starts with a UTF-8 BOM -- strip it before parsing.")

    # Sample first few lines to see if each is independently valid JSON
    # (i.e. the file is JSON Lines, not one big document).
    with open(path, encoding="utf-8-sig") as f:
        sample_lines = [next(f, None) for _ in range(3)]
    parseable = 0
    for i, line in enumerate(sample_lines):
        if line is None:
            continue
        try:
            json.loads(line)
            parseable += 1
        except json.JSONDecodeError:
            pass
    if parseable == len([l for l in sample_lines if l]):
        print("Each of the first 3 lines parses as standalone JSON on its "
              "own -- this file is very likely JSON Lines (one JSON object "
              "per line), not one big JSON document. Use the jsonl loader.")
    else:
        print("First lines do NOT each parse independently -- probably a "
              "single (pretty-printed, multi-line) JSON document. If "
              "json.load() still fails, the file may be truncated or "
              "contain a malformed character partway through.")

    if error is not None:
        # error.pos is the character offset json gave us; show a WIDE
        # context window around it, using repr() so hidden/control
        # characters (stray literal newlines, smart quotes, unescaped
        # straight quotes, etc.) are visible rather than silently eaten
        # by the terminal.
        pos = getattr(error, "pos", None)
        if pos is not None:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            lo, hi = max(0, pos - 400), min(len(text), pos + 400)
            window = text[lo:hi]
            print(f"\n--- WIDE context around error offset {pos} (repr, so "
                  f"hidden characters are visible) ---")
            print(repr(window))
            print("--- end context ---")

            # Scan the window for the usual suspects: an unescaped
            # straight double-quote inside what looks like a string value,
            # or a raw control character (anything below 0x20 other than
            # the \r\n already used as the file's line ending).
            suspects = []
            for i, ch in enumerate(window):
                if ch == '"' :
                    continue  # quotes are everywhere legitimately; skip
                if ord(ch) < 0x20 and ch not in ("\r", "\n", "\t"):
                    suspects.append((lo + i, f"control char {ord(ch):#x}"))
            if suspects:
                print(f"\nRaw control characters found in window: {suspects}")
            else:
                print("\nNo raw control characters in window -- if this is "
                      "a stray straight quote inside a label/description "
                      "string, it won't show up as a 'suspect' here; check "
                      "the repr() output above by eye for a \" that isn't "
                      "closing/opening a JSON string where you'd expect.")

            # Count how many times a similar 'Expecting X delimiter' error
            # would recur, by doing a crude repeated-attempt scan: replace
            # this exact broken span with an escaped version and see if
            # the next error is much further along (suggesting this is a
            # one-off) or immediately adjacent (suggesting a systemic
            # pattern worth a real regex-based repair pass instead of a
            # one-character fix).
            print(f"\nTotal file length: {len(text):,} chars. Error at "
                  f"{pos:,} ({pos/len(text)*100:.1f}% through the file).")


def load_json_flexibly(path):
    """Try a single JSON document first; on failure, retry as JSON Lines
    (one object per line), concatenating features if they're each a
    Feature or a FeatureCollection fragment. Raises the ORIGINAL error
    with diagnostic context printed if neither works, rather than
    guessing silently.
    """
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print("Single-document JSON parse failed -- diagnosing...\n")
        diagnose_raw(path, error=e)

        print("\nAttempting automatic repair of unescaped quotes...")
        try:
            return repair_unescaped_quotes(path)
        except json.JSONDecodeError:
            print("Automatic quote repair did not fully resolve it -- "
                  "falling back to a JSON Lines guess.\n")

        # Attempt JSON Lines fallback.
        feats = []
        bad_lines = 0
        for line in raw.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]", "{", "}"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                feats.extend(obj.get("features", []))
            elif isinstance(obj, dict) and obj.get("type") == "Feature":
                feats.append(obj)
        if feats:
            print(f"\nJSON Lines fallback recovered {len(feats)} features "
                  f"({bad_lines} unparseable lines skipped).")
            return {"type": "FeatureCollection", "features": feats}

        print("\nJSON Lines fallback found nothing parseable either. "
              "Re-raising the original error -- the file is likely "
              "truncated or corrupted; try re-downloading it.")
        raise


def find_key(path, key, max_hits=5, context=400):
    """Directly answers 'does this key exist ANYWHERE in the file, and
    what does it look like' by substring-searching the repaired text,
    rather than continuing to guess from sampled features. Use this when
    dump_raw_features() shows real features that don't have the field
    you expected -- it's possible the field only appears on a minority
    of features (e.g. only ones with literary citations), so a small
    sample can easily miss it entirely.
    """
    data = load_json_flexibly(path)  # ensures repaired cache exists/used
    repaired_path = path + ".repaired.jsonld"
    with open(repaired_path, encoding="utf-8") as f:
        text = f.read()

    needle = f'"{key}"'
    count = text.count(needle)
    print(f'Literal substring {needle!r} appears {count} times in the file.')

    if count == 0:
        print("Not present anywhere under this exact key name. Either it's "
              "spelled/cased differently, or this download genuinely "
              "doesn't carry passage-level citations under this name.")
        return

    idx = -1
    for i in range(min(count, max_hits)):
        idx = text.find(needle, idx + 1)
        lo, hi = max(0, idx - context // 2), min(len(text), idx + context // 2)
        print(f"\n--- occurrence {i+1} at offset {idx} ---")
        print(text[lo:hi])


def dump_raw_features(path, n=3):
    """Prints N complete, unfiltered features verbatim (pretty-printed).
    Use this when inspect()'s citations-under-names assumption doesn't
    match reality -- rather than guessing at another field path, just
    look at real, whole features and find where citation/reference data
    actually lives.
    """
    data = load_json_flexibly(path)
    feats = data.get("features", data if isinstance(data, list) else [])
    # Prefer features that look non-trivial (more top-level keys), since
    # a minimal feature might not have whatever citation field we're
    # looking for at all.
    feats_sorted = sorted(feats, key=lambda f: -len(json.dumps(f)))
    for feat in feats_sorted[:n]:
        print(json.dumps(feat, indent=2, ensure_ascii=False))
        print("=" * 80)


def inspect(path, n=5):
    """Step 0 — print the real shape of the data before we trust any parser.

    Run this FIRST against the actual downloaded file. Look specifically at:
      - top-level keys (is it a bare FeatureCollection, or wrapped?)
      - one feature's "names" -> "citations" structure
      - whether citation entries carry a CTS URN, a topostext.org URL,
        both, or something else entirely (e.g. a bare work-id + paragraph
        number pair as separate fields)
    Then adjust extract_citations() below to match.
    """
    data = load_json_flexibly(path)

    feats = data.get("features", data if isinstance(data, list) else [])
    print(f"top-level type: {type(data).__name__}, feature count: {len(feats)}")
    print(f"top-level keys: {list(data.keys()) if isinstance(data, dict) else 'n/a'}")

    shown = 0
    for feat in feats:
        names = feat.get("names") or feat.get("properties", {}).get("names")
        if not names:
            continue
        for nm in names:
            citations = nm.get("citations")
            if citations:
                print("--- sample feature ---")
                print("properties/title:",
                      feat.get("properties", {}).get("title"))
                print("geometry:", feat.get("geometry"))
                print("citations sample:", json.dumps(citations[:5], indent=2))
                shown += 1
                break
        if shown >= n:
            break

    if shown == 0:
        print("No 'citations' found under names[]. The real structure differs "
              "from what this script assumes — paste a sample feature back "
              "and we'll fix extract_citations() to match.")


def extract_citations(citation_entries):
    """Given a list of citation dicts from one place-name's `citations`
    array, yield (work_urn, passage_citation) for any that match a work
    we care about. Tries CTS URN first, then a topostext.org anchor
    fallback. Silently skips anything unrecognized (recognized-but-
    irrelevant works are also skipped) rather than raising, since the
    gazetteer will contain thousands of citations to works we're not
    ingesting yet.
    """
    for cit in citation_entries:
        # Try every string field on the citation object -- id, label,
        # and any URL-shaped value -- since we don't yet know for certain
        # which field carries the passage reference.
        candidates = [v for v in cit.values() if isinstance(v, str)]
        for text in candidates:
            m = CTS_PASSAGE_RE.search(text)
            if m:
                work_urn, passage = m.groups()
                yield work_urn, passage
                break
            m = TOPOSTEXT_ANCHOR_RE.search(text)
            if m:
                work_id, passage = m.groups()
                # map topostext work id back to a CTS urn via WORKS table
                for urn, meta in WORKS.items():
                    if str(meta["topostext_work_id"]) == work_id:
                        yield urn, (passage or "")
                        break
                break


def extract_point_coords(geom):
    """Returns (lon, lat) from a GeoJSON geometry, handling both a plain
    Point and a GeometryCollection wrapping one or more geometries (real
    ToposText data uses both -- e.g. a GeometryCollection wrapping a
    single Point was seen during inspection). Takes the first Point
    found; returns None if there isn't one.
    """
    if not geom:
        return None
    gtype = geom.get("type")
    if gtype == "Point":
        coords = geom.get("coordinates")
        if coords and len(coords) >= 2:
            return coords[0], coords[1]
        return None
    if gtype == "GeometryCollection":
        for sub in geom.get("geometries", []):
            result = extract_point_coords(sub)
            if result:
                return result
        return None
    return None


def ingest(path):
    data = load_json_flexibly(path)
    feats = data.get("features", data if isinstance(data, list) else [])

    rows = []
    unmatched_citation_samples = []
    no_coords_count = 0

    for feat in feats:
        props = feat.get("properties", {})
        title = props.get("title") or feat.get("title")
        place_id = feat.get("@id") or props.get("id") or feat.get("id")
        point = extract_point_coords(feat.get("geometry"))
        if not point:
            no_coords_count += 1
            continue
        lon, lat = point

        names = feat.get("names") or props.get("names") or []
        for nm in names:
            citations = nm.get("citations") or []
            for work_urn, passage in extract_citations(citations):
                meta = WORKS.get(work_urn)
                if not meta:
                    continue
                if not passage:
                    if len(unmatched_citation_samples) < 10:
                        unmatched_citation_samples.append(citations)
                    continue
                rows.append(PlaceReference(
                    textgroup=meta["textgroup"],
                    work=meta["work"],
                    citation=passage,
                    place_id=str(place_id),
                    place_name=title,
                    lat=lat,
                    lon=lon,
                ))

    print(f"Extracted {len(rows)} place-reference rows across "
          f"{len(WORKS)} configured works.")
    if no_coords_count:
        print(f"({no_coords_count} features skipped -- no parseable "
              f"Point coordinates found)")
    for urn, meta in WORKS.items():
        cnt = sum(1 for r in rows if r.textgroup == meta["textgroup"]
                   and r.work == meta["work"])
        print(f"  {meta['name']:12s} ({urn}): {cnt} rows")

    if unmatched_citation_samples:
        print(f"\n{len(unmatched_citation_samples)} citation entries matched "
              f"a known work but had no parseable passage number -- sample:")
        print(json.dumps(unmatched_citation_samples[:3], indent=2))

    return rows


def write_csv(rows, out_path):
    import csv
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["textgroup", "work", "citation", "place_id",
                    "place_name", "lat", "lon", "source"])
        for r in rows:
            w.writerow([r.textgroup, r.work, r.citation, r.place_id,
                        r.place_name, r.lat, r.lon, r.source])
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "inspect":
        inspect(path)
    elif cmd == "dump":
        dump_raw_features(path)
    elif cmd == "find_key":
        key = sys.argv[3] if len(sys.argv) > 3 else "citations"
        find_key(path, key)
    elif cmd == "ingest":
        rows = ingest(path)
        write_csv(rows, "place_references.csv")
    else:
        print(__doc__)
