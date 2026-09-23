"""parse_mode -> parser function registry, keyed by the ACTUAL strings used
in work_registry.json's per-edition `parse_mode` field (not a work-level
`doc_type` -- there is no such top-level field; dispatch in
ingest_work.py's if/elif chain is per edition/translation/commentary entry,
and a single work_key can mix several parse_modes across its editions).
`None` (parse_mode omitted) falls through to parse_hierarchical_tei, same
as ingest_work.py's own `else` branch.

Used by build_all.py's dep_paths_for() so that editing a parser's code
correctly invalidates the manifest fingerprint for every work that uses
it -- see that module's docstring for why this needed fixing (the keys
here originally didn't match any real registry value at all).
"""
from pipeline.parsers.poetry_cards import parse_poetry_cards_tei
from pipeline.parsers.card_prose import parse_card_prose_tei
from pipeline.parsers.milestones import parse_milestone_tei
from pipeline.parsers.reading_lines import parse_reading_lines_tei
from pipeline.parsers.hierarchical import parse_hierarchical_tei
from pipeline.parsers.speech_collection import parse_speech_collection_tei
from pipeline.parsers.book_chapter_section import parse_book_chapter_section_tei
from pipeline.parsers.line_commentary import parse_line_commentary_tei
from pipeline.parsers.section_sentences import parse_section_sentences_tei

PARSE_MODE_PARSERS = {
    "poetry_cards": parse_poetry_cards_tei,
    "card_prose": parse_card_prose_tei,
    "milestones": parse_milestone_tei,
    "reading_lines": parse_reading_lines_tei,
    None: parse_hierarchical_tei,
    "speech_collection_sentences": parse_speech_collection_tei,
    "book_chapter_section": parse_book_chapter_section_tei,
    "line_commentary": parse_line_commentary_tei,
    "section_sentences": parse_section_sentences_tei,
}

# Kept as an alias -- some callers may still refer to the old name.
DOC_TYPE_PARSERS = PARSE_MODE_PARSERS
