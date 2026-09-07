"""CoNLL-U treebank parser. Relocated from Cell 4."""
import os
import re
from collections import OrderedDict

def parse_conllu_treebank(path, version_short_id, tg, wk, card_intervals=None, has_books=True):
    paths = [path] if isinstance(path, (str, os.PathLike)) else list(path)
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        for p in missing:
            print(f"  ✗ Treebank not found: {p}")
        return [], {'annotators': []}

    line_to_card = {}
    if card_intervals:
        for idx, interval in enumerate(card_intervals):
            try:
                bk    = str(interval['book'])
                # Poem-carded works (e.g. Propertius) give a bare label like
                # "8a" -- no "-" to split on. That's expected: those cards
                # are matched via book_card_lookup/sent_id below instead, so
                # just skip line-range expansion for them here rather than
                # letting the missing second half raise IndexError.
                label_parts = interval['label'].split('-')
                if len(label_parts) < 2:
                    continue
                start = int(label_parts[0])
                end   = int(label_parts[1])
                for ln in range(start, end + 1):
                    # Key as BOOK.LINE (multi-book) and bare LINE (flat works)
                    line_to_card[f"{bk}.{ln}"] = interval['label']
                    line_to_card[str(ln)] = interval['label']
            except (ValueError, KeyError, IndexError):
                continue

    # Poem-carded works (elegy / letter collections, e.g. Propertius): the
    # card_n IS the poem's own citation label (verbatim -- "8a", "8b", ...),
    # not a line range, so it can't be expanded into line_to_card above.
    # sent_id already carries BOOK.POEM.SENTENCE, so build a lookup of valid
    # (book, poem) pairs and prefer that in flush() below over the line-based
    # path, which would otherwise collide (poem line numbers reset to 1 each
    # poem, so "line 5" is ambiguous across poems in the same book).
    book_card_lookup = set()
    if card_intervals:
        for interval in card_intervals:
            book_card_lookup.add((str(interval['book']), str(interval['card_n'])))

    # sent_id already carries the full book.chapter.section triple for
    # works like Boeckh's Orationes (e.g. "orat1.1.1") -- a prefix of
    # non-digits followed by exactly three dot-separated numbers. When it
    # matches, that's a strictly more reliable citation than Ref/subdoc,
    # which for some sources (Boeckh's included) is just a page number with
    # no dots at all -- not a real book.chapter.section address, and
    # unusable for aligning treebank sentences to the reading text no
    # matter how _derive_prose_chapter_section below tries to salvage it.
    # Prefer sent_id outright whenever it fits this shape, for every work,
    # not just Boeckh -- any work whose Ref doesn't encode real citation
    # structure benefits the same way, and works with a genuinely useful
    # Ref (Thucydides-style "1.89.3") essentially never have a sent_id that
    # ALSO happens to match this pattern by coincidence, so this doesn't
    # change behavior for anything that already works.
    _SENT_ID_CITATION_RE = re.compile(r'^\D*(\d+)\.(\d+)\.(\d+)$')

    def _derive_prose_chapter_section(ref, sid=None):
        """For prose (no card_intervals) addressing. Two distinct shapes are
        possible depending on whether the WORK itself has book divisions
        (has_books, closed over from the enclosing parse_conllu_treebank
        call -- same has_multiple_books value the edition-ingestion loop
        used to build alignment_grid for this work):

          * has_books=True  -> refs are book.chapter.section (e.g. Thucydides
            "1.89.3"). treebank_sentences has no separate book column, and
            the client (app.js's _hydrateTreebank) groups sentences purely
            by this chapter string, so collapsing to the bare book number
            merges every chapter of a book together -- and even a bare
            chapter number collides across different books (book 2 chapter 1
            is not book 3 chapter 1). Fold book into the chapter key itself
            ("book.chapter", e.g. "1.89") to keep it globally unique; app.js's
            lookup constructs this same compound key from payload.book/chapter.
            The real section (the passage/sentence number) is the LAST
            segment, not the middle one -- a 2-level "book.section" ref (no
            chapter subdivision) doesn't have a middle level at all.

          * has_books=False -> the work has no book level at all (e.g.
            Aristotle's Poetics, chapters 1-26 with no enclosing book), so a
            ref is simply chapter.section (e.g. "5.3" = chapter 5, section
            3). Treating that 2-part ref as "book.chapter" here would
            silently fold the chapter into a fake book id and produce a
            chapter value ("5.1") that never matches alignment_grid's bare
            chapter numbers ("5"), which is exactly what caused the Kassel/
            Bishr Matta Poetics treebanks to vanish from shards even though
            monolith ingestion looked fine.

        Before either of those Ref-based paths, sent_id is checked first --
        see _SENT_ID_CITATION_RE above -- since it's frequently a more
        trustworthy source than Ref for prose collections.
        """
        if sid and has_books:
            # Scoped to has_books=True only -- that's Boeckh's actual case
            # and the only one this fix has been validated against. Leaving
            # has_books=False (e.g. the Poetics' chapter-only addressing)
            # completely untouched rather than guessing at a 3-part sent_id
            # shape for works this hasn't been tested against.
            m = _SENT_ID_CITATION_RE.match(str(sid))
            if m:
                bk, ch, sec = m.group(1), m.group(2), m.group(3)
                return f"{bk}.{ch}", sec

        parts = ref.split('.')
        if not has_books:
            if len(parts) >= 2:
                return parts[0], '.'.join(parts[1:])
            return parts[0], (str(sid) if sid else '1')
        if len(parts) >= 3:
            return f"{parts[0]}.{parts[1]}", '.'.join(parts[2:])
        elif len(parts) == 2:
            return f"{parts[0]}.1", parts[1]
        else:
            return f"{parts[0]}.1", (str(sid) if sid else '1')

    def _looks_like_head(v):
        """Valid CoNLL-U HEAD values: a non-negative integer, or '_'. Used to
        detect a blank LEMMA field that whitespace-splitting has silently
        swallowed (some source files leave LEMMA blank by deliberate
        annotator choice for certain forms -- not an error -- but a truly
        empty field disappears rather than surviving as '' once a line is
        whitespace- rather than tab-split, shifting every field after it one
        position to the left; that shift makes something clearly non-head-
        shaped -- e.g. a deprel string -- turn up where HEAD should be)."""
        return v == '_' or v.isdigit()

    def _lookup_card(ref):
        """Resolve a Ref/subdoc line value to its card label. Handles the
        plain-integer case directly, and falls back to the leading digits
        for interpolated/lettered line variants (e.g. Evelyn-White's Theogony
        929a-929t insertion) that sit between two canonical integer lines but
        were never themselves enumerated when line_to_card was built."""
        if ref in line_to_card:
            return line_to_card[ref]
        m = re.match(r'^(\d+)', ref)
        if m and m.group(1) in line_to_card:
            return line_to_card[m.group(1)]
        return None

    # ── Document-level annotator roster ─────────────────────────────────
    # Two header conventions are supported:
    #   1. Tagged roster (one line per annotator, resolved by short code from
    #      a per-sentence "# sentannotators" line):
    #        # annotator <short>millermo</short> <name>Molly Miller</name> <address>Tufts University, Medford, MA, USA</address>
    #   2. Simple form (the common case — one flat credit for the whole
    #      document, no per-sentence variation):
    #        # annotator = Molly Miller, Tufts University, Medford, MA, USA
    # doc_roster maps short-code -> {name, address} (tagged form only).
    # doc_annotators_ordered preserves file order and is used as the
    # document-level fallback when a sentence has no "# sentannotators" line.
    doc_roster = OrderedDict()
    doc_annotators_ordered = []
    ANNOTATOR_TAGGED_RE = re.compile(
        r'^#\s*annotator\s+<short>(.*?)</short>\s*<name>(.*?)</name>\s*<address>(.*?)</address>\s*$'
    )
    ANNOTATOR_SIMPLE_RE = re.compile(r'^#\s*annotator\s*=\s*(.+)$')
    SENTANNOTATORS_RE   = re.compile(r'<(primary|secondary)>(.*?)</\1>')
    SOURCE_RE           = re.compile(r'^#\s*source\s*[:=]?\s*(.+)$', re.IGNORECASE)
    doc_source = None

    sentences = []
    cur = None

    def flush():
        if not cur or not cur.get('tokens'):
            return
        sent = dict(cur)
        # Resolve empty-node HEAD references (ellipsis/gapping): a token
        # whose basic HEAD pointed at an empty node's decimal id (e.g.
        # "10.1") gets reattached to that empty node's own real governor,
        # which we only learn once the whole sentence has been read (the
        # empty node's row can come before or after the token referencing
        # it). Anything unresolved (malformed/missing empty-node row) falls
        # back to root (0) rather than crashing.
        empty_heads = sent.pop('empty_heads', None) or {}
        for tok in sent['tokens']:
            ref = tok.pop('head_empty_ref', None)
            if ref is not None:
                tok['head'] = empty_heads.get(ref, 0)
        # Resolve this sentence's credits: prefer its own "sentannotators"
        # refs (short codes tagged primary/secondary), resolved against the
        # tagged roster; fall back to the whole-document roster/simple list
        # when the sentence didn't specify its own.
        refs = sent.pop('credits_refs', None)
        if refs:
            resolved = []
            for role, short in refs:
                entry = doc_roster.get(short)
                if entry:
                    resolved.append({'name': entry['name'], 'address': entry['address'], 'role': role})
                else:
                    resolved.append({'name': short, 'address': None, 'role': role})
            sent['credits'] = resolved
        else:
            sent['credits'] = None
        if sent.get('subdoc') is None:
            first_ref = None
            for tok in sent['tokens']:
                if tok.get('ref'):
                    first_ref = tok['ref']
                    break
            if first_ref is not None:
                sent['subdoc'] = first_ref

            if card_intervals:
                # Poem-carded works: sent_id is BOOK.POEM.SENTENCE (e.g.
                # "1.8a.3"). Prefer it whenever (book, poem) names a real
                # card -- this is exact and handles lettered sub-poems
                # correctly, unlike the line-based lookup below, which
                # assumes line numbers are unique within a book (true for
                # Homer/Vergil's continuous numbering, false for elegy,
                # where line numbers reset every poem).
                sid_parts = str(sent.get('sent_id') or '').split('.')
                matched_poem = None
                if len(sid_parts) >= 2 and (sid_parts[0], sid_parts[1]) in book_card_lookup:
                    matched_poem = sid_parts[1]

                if matched_poem is not None:
                    # chapter stays BARE -- alignment_grid.chapter is always
                    # bare too (book lives in its own column there), so this
                    # is what the shard router's chapter_book/cs_book lookup
                    # actually expects to match against.
                    sent['chapter'] = matched_poem
                    sent['book'] = sid_parts[0]
                    # BUT: for poetry, parse_poetry_cards_tei hardcodes
                    # section="1" on every alignment_grid row (poems aren't
                    # subdivided the way prose chapters are), so cs_book's
                    # (chapter, section) key has zero disambiguating power
                    # here -- (chapter, "1") collides across every book just
                    # like bare chapter does, and BOTH resolve via last-
                    # write-wins to whichever book sorts last. Net effect:
                    # every poem-carded treebank row in the whole work, from
                    # every book, was silently routed into ONE book's shard
                    # only -- not spread across books, and not "zero" at the
                    # DB level, but zero for every book except that one.
                    # sent_id already carries the real book unambiguously
                    # (e.g. "1.1.5" / "2.1.5"), so persist the FULL sent_id
                    # into subdoc (not just first_ref) -- the router (cell 9)
                    # is patched to read book straight out of it for
                    # poem-carded rows, bypassing chapter_book/cs_book
                    # entirely instead of trying to make that join work.
                    sent['subdoc'] = sent.get('sent_id') or sent['subdoc']
                elif first_ref is not None:
                    # Original line-carded (Homer/Vergil-style) path.
                    book_part = first_ref.split('.')[0] if '.' in first_ref else first_ref
                    sent['chapter'] = _lookup_card(first_ref) or book_part
                    # Only a REAL book prefix counts. Single-play tragedy
                    # works (Euripides etc.) cite by bare line number alone
                    # -- Ref="377", no dot at all -- so book_part above just
                    # falls back to the WHOLE bare ref ("377"), which is not
                    # a book id, it's a line number that happens to have no
                    # dot in it. Setting sent['book'] to that unconditionally
                    # poisoned the router (cell 9): it used "377" as if it
                    # were this sentence's book, never matched any real book
                    # in a single-play work's group_set, and the row silently
                    # failed to route into any shard at all -- reproducing
                    # uniformly across every book-less work (confirmed: all
                    # 6 Euripides plays, "no shard parts have rows"). Leave
                    # sent['book'] unset here; the router already falls back
                    # correctly to chapter_book/cs_book when it's absent.
                    if '.' in first_ref:
                        sent['book'] = book_part
            else:
                # Prose, no card structure: derive chapter/section straight
                # from sent_id whenever it carries its own BOOK.CHAPTER.SECTION
                # citation shape (see _SENT_ID_CITATION_RE) -- this no longer
                # requires a Ref field to exist at all. Ref is only consulted
                # as a fallback when sent_id doesn't fit that shape (works
                # whose sent_id is just an incrementing counter, not a real
                # citation). Guards against the degenerate case where BOTH
                # are unusable (empty ref, non-matching/absent sent_id),
                # which previously left chapter/section unset -- same as
                # before, just reached from a different branch now.
                sid = sent.get('sent_id')
                chapter, section = _derive_prose_chapter_section(first_ref or '', sid)
                if chapter and chapter != '.1':
                    sent['chapter'], sent['section'] = chapter, section
                    if has_books and '.' in sent['chapter']:
                        sent['book'] = sent['chapter'].split('.')[0]
                    # subdoc: prefer the sent_id-derived citation label (what
                    # chapter/section were actually built from) over a raw
                    # Ref value that may carry no real citation meaning (e.g.
                    # Boeckh's Ref is a stale page/line count, unrelated to
                    # the oration.paragraph.sentence scheme sent_id encodes).
                    sent['subdoc'] = (
                        sid if (sid and _SENT_ID_CITATION_RE.match(str(sid)))
                        else (first_ref if first_ref is not None else sid)
                    )
                elif first_ref is not None:
                    sent['subdoc'] = first_ref


        else:
            # subdoc came from a "# subdoc =" header; chapter/section were already
            # set when the header was parsed. Only poetry works need a card remap.
            if card_intervals and sent.get('subdoc'):
                subdoc_ref = sent['subdoc']
                book_part = subdoc_ref.split('.')[0] if '.' in subdoc_ref else subdoc_ref
                # Try BOOK.LINE key first, then bare LINE (flat works), fall back to book
                chapter = _lookup_card(subdoc_ref)
                if chapter is None and '.' not in subdoc_ref:
                    chapter = _lookup_card(f'1.{subdoc_ref}')
                sent['chapter'] = chapter or book_part
                # Populate the real `book` column too (this branch never did,
                # unlike the sibling "subdoc is None" path below) -- only when
                # subdoc_ref genuinely carried a book prefix, same "real
                # prefix only" guard as that sibling path uses, so a bare ref
                # in a single-book work doesn't get its whole line number
                # mistaken for a book id. The sharder (Cell 9) already prefers
                # a populated `book` column outright over its subdoc-parsing
                # fallback, so this makes routing exact instead of relying on
                # that fallback to reconstruct the same answer from subdoc.
                if '.' in subdoc_ref:
                    sent['book'] = book_part
                if not sent.get('section'):
                    sent['section'] = str(sent.get('sent_id', '1'))
            else:
                # prose work, no card intervals: recompute chapter/section
                # correctly rather than trusting the header's values, since
                # the header-parsing site below has this exact same
                # book.chapter.section derivation and needs the identical
                # fix -- keeping stale/mis-derived header values here would
                # just perpetuate whatever it got wrong.
                sent['chapter'], sent['section'] = _derive_prose_chapter_section(sent['subdoc'], sent.get('sent_id'))
                if has_books and '.' in sent['chapter']:
                    sent['book'] = sent['chapter'].split('.')[0]
                
        sentences.append(sent)

    for path in paths:
      with open(path, 'r', encoding='utf-8') as fh:
        for raw in fh:
            line = raw.rstrip('\n')

            is_sent_id   = line.startswith('# sentence_id')
            is_sent_id_s = line.startswith('# sent_id')
            if is_sent_id or is_sent_id_s:
                flush()
                sid = line.split('=', 1)[1].strip() if '=' in line else None
                cur = {'tokens': [], 'subdoc': None, 'chapter': None,
                       'section': None, 'book': None, 'prose': None, 'literal': None,
                       'translit': None, 'sent_id': sid, 'credits_refs': None,
                       'empty_heads': {}}
                continue

            if line.startswith('#'):
                # Document header lines (before the first sent_id) still need
                # to be scanned for the annotator roster/source, even though
                # there's no "cur" sentence yet to attach them to.
                m_tagged = ANNOTATOR_TAGGED_RE.match(line)
                if m_tagged:
                    short, name, address = m_tagged.group(1).strip(), m_tagged.group(2).strip(), m_tagged.group(3).strip()
                    entry = {'name': name, 'address': address}
                    doc_roster[short] = entry
                    doc_annotators_ordered.append(entry)
                elif ANNOTATOR_SIMPLE_RE.match(line):
                    name = ANNOTATOR_SIMPLE_RE.match(line).group(1).strip()
                    doc_annotators_ordered.append({'name': name, 'address': None})
                m_source = SOURCE_RE.match(line)
                if m_source and doc_source is None:
                    doc_source = m_source.group(1).strip()

                if cur is None:
                    continue

                m_sentann = re.match(r'^#\s*sentannotators\b(.*)$', line)
                if m_sentann:
                    refs = SENTANNOTATORS_RE.findall(m_sentann.group(1))
                    if refs:
                        cur['credits_refs'] = refs
                    continue

                def mval(key, ln=line):
                    m = re.match(rf'^#\s*{key}\s*=\s*(.+)', ln)
                    return m.group(1).strip() if m else None
                v = mval('subdoc')
                if v:
                    cur['subdoc'] = v
                    cur['chapter'], cur['section'] = _derive_prose_chapter_section(v, cur.get('sent_id'))
                # 'reading_translation' is an accepted alias for
                # 'prose_translation' -- same DB column/purpose (the fluent
                # translation shown alongside the word-for-word literal one),
                # just the header key your Boeckh/Propertius conllu files
                # already use. prose_translation still wins if a file
                # somehow has both.
                p = mval('prose_translation') or mval('reading_translation')
                if p: cur['prose'] = p
                lt = mval('literal_translation')
                if lt: cur['literal'] = lt
                tr = mval('transliteration')
                if tr: cur['translit'] = tr
                continue

            if cur is None:
                continue

            if line == '':
                # Historical Daphne exports use blank lines both before the
                # first token and *inside* a dependency tree. Sentence
                # boundaries are carried by the next # sent_id line, which
                # already calls flush(), so a blank line is presentation only
                # here. Flushing it used to lose continuation token rows.
                continue

            # Standard CoNLL-U is tab-separated, but some source files (seen
            # in the wild: a large stretch of Aeschylus's Prometheus Bound)
            # use space-padded columns instead of real tabs -- visually
            # aligned, but silently unparseable by a strict tab-split, which
            # would otherwise drop every one of those sentences with zero
            # tokens and no error. Try tabs first (this also preserves the
            # existing colon-typo'd-as-tab tolerance for empty nodes below,
            # which depends on the tab-split column layout); only fall back
            # to whitespace-splitting when tab-splitting clearly failed.
            cols = line.split('\t')
            if len(cols) < 8:
                ws_cols = line.split()
                if len(ws_cols) >= 8:
                    cols = ws_cols
            if len(cols) < 8:
                continue
            id_str = cols[0]
            if '-' in id_str:
                continue  # multiword token range row: no annotation of its own
            if re.match(r'^\d+\.$', id_str):
                # A stray period glued onto the token id with nothing after
                # the dot (seen in the wild when the token's own FORM is
                # itself "." and an export step merged the two with no
                # space, e.g. "13.\t.\tPUNCT..."). NOT a real empty node --
                # those are always "N.M" with digits on both sides of the
                # dot. Strip the glued-on dot and fall through to ordinary
                # token handling below instead of misreading it as ellipsis.
                id_str = id_str[:-1]
            elif '.' in id_str:
                # Empty node (CoNLL-U's standard way of encoding ellipsis/
                # gapping — a word position with no surface form). It carries
                # no token of its own, but real tokens can point to it as
                # their HEAD (see below), so remember its own governor,
                # normally packed as "HEAD:DEPREL" in the DEPS field (index 8).
                # Tolerate the corrupted variant where that colon was typo'd
                # as a tab, splitting "8:acl:compl" into cols[8]="8" and an
                # extra cols[9]="acl:compl" (bumping MISC to cols[10]).
                deps_field = cols[8] if len(cols) > 8 else '_'
                head_part = deps_field.split(':', 1)[0].strip()
                if not head_part.isdigit() and len(cols) > 9 and cols[8].strip().isdigit():
                    head_part = cols[8].strip()
                if head_part.isdigit():
                    cur.setdefault('empty_heads', {})[id_str] = int(head_part)
                continue

            # Realign LEMMA/UPOS/XPOS/FEATS/HEAD/DEPREL/DEPS/MISC from cols[2:],
            # auto-detecting a blank LEMMA (see _looks_like_head above) by
            # checking whether the position HEAD should occupy actually holds
            # a valid head value; if not, retry on the assumption LEMMA was
            # blank and everything after it shifted one column left.
            rest = cols[2:]
            if len(rest) >= 5 and _looks_like_head(rest[4]):
                lemma = rest[0]
                upos, xpos, feats, head_val = rest[1], rest[2], rest[3], rest[4]
                tail = rest[5:]
            elif len(rest) >= 4 and _looks_like_head(rest[3]):
                lemma = ''
                upos, xpos, feats, head_val = rest[0], rest[1], rest[2], rest[3]
                tail = rest[4:]
            else:
                # Neither alignment yields a valid head -- fall back to the
                # naive (lemma-present) reading rather than guessing further.
                lemma = rest[0] if rest else ''
                upos  = rest[1] if len(rest) > 1 else '_'
                xpos  = rest[2] if len(rest) > 2 else '_'
                feats = rest[3] if len(rest) > 3 else '_'
                head_val = rest[4] if len(rest) > 4 else '0'
                tail = rest[5:]
            deprel = tail[0] if len(tail) > 0 else '_'
            # tail[1], if present, is DEPS -- not stored on the token (only
            # used above for empty-node governor resolution).
            misc = tail[2] if len(tail) > 2 else '_'
            # Some source files pack gloss into MISC ("Ref=1|gloss=word");
            # others give gloss its own trailing column instead of using
            # MISC's pipe-joined convention for it at all. Support both:
            # prefer MISC's own gloss= if present, else the trailing column.
            gloss_trailing = tail[3] if len(tail) > 3 else None
            gloss = None
            ref   = None
            translit  = None
            ltranslit = None
            for kv in misc.split('|'):
                k2, _, v2 = kv.partition('=')
                # Case-insensitive match on the translit/ltranslit keys --
                # some source files write "Translit"/"LTranslit" (capitalized,
                # the original convention here), others (e.g. the Heike
                # DeepSeek treebank) write lowercase "translit"/"ltranslit".
                # "gloss" has only ever appeared lowercase, so stays exact-
                # match. "Ref" previously only ever appeared capitalized too
                # -- but the Nonnus/Dionysiaca OGA source uses lowercase
                # "ref=" throughout, so the old exact-match on 'Ref' silently
                # found nothing for every single token: first_ref never got
                # set, subdoc/chapter/book all stayed None, and the sentence
                # was then dropped entirely by the "if not sent.get('subdoc'):
                # continue" guard at insert time -- the whole treebank
                # ingested zero usable rows despite the reassuring sentence
                # COUNT printed (that count is taken before this filtering).
                if k2 == 'gloss':                       gloss     = v2.strip()
                if k2 in ('Ref', 'ref'):
                    _raw_ref = v2.strip()
                    # This source may also embed the work's own title
                    # abbreviation into the citation ("Dionys._34.1" rather
                    # than a bare "34.1"), which line_to_card/_lookup_card
                    # can't match as-is. Strip everything before the trailing
                    # BOOK.LINE[suffix] shape; a ref with no such shape (e.g.
                    # some other corpus's bare "1", no dot) is left untouched.
                    _m_ref = re.search(r'(\d+\.\d+[a-zA-Z]*)$', _raw_ref)
                    ref = _m_ref.group(1) if _m_ref else _raw_ref
                if k2 in ('Translit', 'translit'):      translit  = v2.strip()
                if k2 in ('LTranslit', 'ltranslit'):    ltranslit = v2.strip()
            if gloss is None and gloss_trailing:
                gloss = gloss_trailing.strip()

            # A real token's basic HEAD is normally an integer (or '_'/0 for
            # root). Some Daphne-annotated ellipsis constructions instead
            # point a token straight at an empty node (a decimal id like
            # "10.1"). We can't resolve that until the whole sentence (and
            # that empty node's own row, which may appear later) is read, so
            # stash the raw reference now and resolve it in flush() below.
            head_is_empty_ref = '.' in head_val
            cur['tokens'].append({
                'id':     int(id_str),
                # Stable within a published treebank version and globally
                # unambiguous across sentences/segments.  Consumers should
                # link to this identifier rather than to a repeated surface
                # form such as δέ or καί.
                'stable_id': f'urn:perseus:treebank:{tg}.{wk}.{version_short_id}:{cur.get("sent_id")}.{id_str}',
                'form':   cols[1],
                'lemma':  lemma,
                'upos':   upos,
                'xpos':   xpos,
                'feats':  feats,
                'head':   0 if head_is_empty_ref else (int(head_val) if head_val not in ('_',) else 0),
                'head_empty_ref': head_val if head_is_empty_ref else None,
                'deprel': deprel,
                'gloss':  gloss,
                'ref':    ref,
                'translit':  translit,
                'ltranslit': ltranslit,
            })

    flush()
    # Document-level credits: the tagged roster (if any annotator lines used
    # that form) plus any simple-form lines, in file order. This is the
    # fallback shown for sentences that don't carry their own sentannotators,
    # and is also stored once per version for the "common case" documents
    # that never use per-sentence credits at all.
    doc_credits = {
        'annotators': doc_annotators_ordered,
        'source': doc_source,
    }
    return sentences, doc_credits
