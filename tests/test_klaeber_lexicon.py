from pathlib import Path

from pipeline.lexicon.parsers import parse_lexicon_klaeber_tei
from pipeline.lexicon.reconcile_klaeber import build_klaeber_index, reconcile_conllu


FIXTURE = Path(__file__).parent / "fixtures" / "klaeber_minimal.xml"


def test_klaeber_entryfree_variants_and_compact_aliases():
    entries, aliases, citations = parse_lexicon_klaeber_tei(FIXTURE, "klaeber-beowulf")
    by_id = {entry["entry_id"]: entry for entry in entries}
    alias_pairs = {(alias["alias_key"], alias["entry_id"]) for alias in aliases}

    assert citations == []
    assert by_id["entry-he"]["headword_display"] == "hē, hēo, hit"
    assert ("heo", "entry-he") in alias_pairs
    assert ("hit", "entry-he") in alias_pairs
    assert ("geseon", "entry-geseon") in alias_pairs
    assert ("eall", "entry-eall") in alias_pairs


def test_klaeber_text_ref_links_and_pointer_aliases_to_full_entry():
    entries, aliases, _ = parse_lexicon_klaeber_tei(FIXTURE, "klaeber-beowulf")
    by_id = {entry["entry_id"]: entry for entry in entries}
    alias_pairs = {(alias["alias_key"], alias["entry_id"]) for alias in aliases}

    assert "openLexiconEntry('klaeber-beowulf','entry-geseon')" in by_id["entry-gesion"]["entry_html"]
    assert ("gesion", "entry-geseon") in alias_pairs


def test_klaeber_reconciliation_changes_only_safe_lemma_cells():
    index = build_klaeber_index(FIXTURE)
    source = (
        "1\tgeseah\tgeseon\tVERB\tv\t_\t0\troot\t_\tgloss=saw\n"
        "2\t.\t)\tPUNCT\tu\t_\t1\tpunct\t_\t_\n"
        "3\toð þæt\toð þæt\tCCONJ\tc\t_\t1\tmark\t_\t_\n"
    )
    reconciled, report = reconcile_conllu(source, index)

    assert "\tge-sēon\tVERB\t" in reconciled
    assert "\t)\tPUNCT\t" in reconciled
    assert "\toð þæt\tCCONJ\t" in reconciled
    assert report["stats"]["changed"] == 1
