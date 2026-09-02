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


def test_motion_scene_is_responsive_and_respects_reduced_motion():
    script = (PROJECT_ROOT / "static" / "landing.js").read_text(encoding="utf-8")

    assert "requestAnimationFrame" in script
    assert "prefers-reduced-motion: reduce" in script
    assert "ResizeObserver" in script
    assert "pointermove" in script


def test_container_static_bundle_matches_the_live_landing_assets():
    deployed_static = PROJECT_ROOT / "deploy" / "cloudflare-container" / "static"

    for filename in ("landing.html", "landing.css", "landing.js"):
        assert (PROJECT_ROOT / "static" / filename).read_bytes() == (
            deployed_static / filename
        ).read_bytes()
