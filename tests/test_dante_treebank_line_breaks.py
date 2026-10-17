from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dante_uses_line_aware_treebank_renderer():
    """Dante tokens carry Canto.Line refs and must use the poetry grid.

    The poetry branch in ``renderTreebankColumn`` starts a new visual row
    whenever a token's ``ref`` changes.  If Dante falls through to the prose
    branch, those same tokens are rendered as one continuous sentence and
    the verse divisions disappear.
    """
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'wKey.startsWith("dante.")' in app
    assert "const currentTokenLine = tok.ref ? tok.ref.trim() : null;" in app
    assert "currentTokenLine !== lastSeenLineNum" in app
    assert "numCell.className = 'line-num-cell';" in app
