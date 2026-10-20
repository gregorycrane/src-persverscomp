"""The reader navigation can be collapsed without losing its restore control."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_navigation_toggle_is_present_and_persistent():
    shell = (ROOT / "web" / "index_shell.html").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'id="btn-toggle-navigation"' in shell
    assert 'onclick="toggleNavigationBar()"' in shell
    assert 'aria-controls="nav-bar browse-bar"' in shell
    assert "body.navigation-bars-hidden #nav-bar" in styles
    assert "body.navigation-bars-hidden #browse-bar" in styles
    assert "window.toggleNavigationBar = toggleNavigationBar" in app
    assert "pmv-navigation-bars-hidden" in app


def test_toggle_stays_outside_the_collapsible_navigation_rows():
    shell = (ROOT / "web" / "index_shell.html").read_text(encoding="utf-8")

    toggle = shell.index('id="btn-toggle-navigation"')
    banner_end = shell.index('</div>', toggle)
    nav = shell.index('<div id="nav-bar">')
    browse = shell.index('<div id="browse-bar">')

    assert toggle < banner_end < nav < browse
