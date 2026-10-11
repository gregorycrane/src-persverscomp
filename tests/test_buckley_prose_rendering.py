from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bare_speaker_repair_is_limited_to_numbered_poetry_cards():
    """A whole prose card must never be promoted to a speaker label."""
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    guard = "const hasPoetryLineCells = Boolean(wrapper.querySelector('.line-num-cell'));"
    guarded_repair = "if (hasPoetryLineCells) {\n                    Array.from(wrapper.childNodes).forEach"
    assert guard in app
    assert guarded_repair in app
    assert "if (!hasPoetryLineCells)" in app
