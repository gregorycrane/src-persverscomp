from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_large_fragment_navigation_is_bounded_and_searchable():
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "LARGE_CHAPTER_NAV_THRESHOLD = 80" in app
    assert "renderLargeChapterNavigation" in app
    assert 'input.placeholder = isArnimFragmentWork(workKey) ? "SVF II 456"' in app
    assert "chapters.includes(target)" in app
    assert "chList.slice(railStart, railEnd)" in app
    assert "flatChapters.includes(startRef)" in app


def test_large_navigation_controls_have_compact_styles():
    styles = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    assert "#chapter-items-container.chapter-items-large" in styles
    assert ".chapter-jump-control" in styles
    assert ".chapter-jump-input" in styles
    assert "flex-wrap: nowrap; overflow-x: auto" in styles
    assert "@media (max-width: 600px)" in styles
