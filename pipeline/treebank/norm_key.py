"""Accent/case-insensitive search-key normalizer.

Was duplicated verbatim in Cell 5 (treebank flatten) and Cell 12 (lexicon
parsers) in the original notebook -- one of the concrete reasons for this
split. Both now import it from here.
"""
import unicodedata

def norm_key(s):
    """Accent/diacritic- and case-insensitive search key.

    Strips Unicode combining marks (category Mn) -- this covers Greek
    polytonic accents/breathings/iota subscript AND Arabic tashkeel in one
    pass -- then folds Greek final sigma and lowercases. Plain Latin/Persian
    strings pass through unchanged (aside from lowercasing).
    """
    if not s:
        return None
    t = unicodedata.normalize('NFD', s)
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    t = unicodedata.normalize('NFC', t).lower()
    t = t.replace('\u03c2', '\u03c3')  # final sigma -> medial sigma
    return t
