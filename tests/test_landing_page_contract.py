from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_hero_uses_a_dedicated_evidence_motion_scene():
    html = (PROJECT_ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "static" / "landing.css").read_text(encoding="utf-8")
    parser = LandingParser()
    parser.feed(html)

    hero_canvas = [
        attrs
        for tag, attrs in parser.elements
        if tag == "canvas" and attrs.get("id") == "hero-evidence-canvas"
    ]

    assert hero_canvas
    assert hero_canvas[0].get("aria-hidden") == "true"
    assert any(
        tag == "script" and attrs.get("src", "").startswith("/static/landing.js?")
        for tag, attrs in parser.elements
    )
    assert "bidproof-workspace.png" not in css
    assert "bidproof-workspace-v2.png" not in css
    assert 'id="verdicts"' in html
    assert 'class="login-link"' in html
    assert "登录 / 注册" in html


def test_motion_scene_is_responsive_and_respects_reduced_motion():
    script = (PROJECT_ROOT / "static" / "landing.js").read_text(encoding="utf-8")

    assert "requestAnimationFrame" in script
    assert "prefers-reduced-motion: reduce" in script
    assert "ResizeObserver" in script
    assert "pointermove" in script


def test_no_forked_copy_of_the_application_tree_is_vendored():
    """A second copy of app/ or static/ silently drifts from the live one.

    The Cloudflare container skeleton previously vendored both and had already diverged, so
    on-premise delivery keeps exactly one source of truth for application code and assets.
    """
    def keep(path):
        return (
            ".venv" not in path.parts
            and "node_modules" not in path.parts
            and "_zip-sync" not in path.parts
            and not any(part.startswith("_incoming") for part in path.parts)
        )

    duplicates = [
        path
        for candidate in ("app", "static")
        for path in PROJECT_ROOT.rglob(f"*/{candidate}/main.py")
        if keep(path)
    ]
    duplicates += [
        path
        for path in PROJECT_ROOT.rglob("*/static/app.js")
        if keep(path)
    ]

    assert duplicates == []
