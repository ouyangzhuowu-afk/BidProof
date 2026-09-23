"""Public page contracts focus on navigation, honest evidence, and safe progressive enhancement."""
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_landing_build_has_real_ctas_accessible_demo_and_no_inline_script():
    html = (PROJECT_ROOT / "static/marketing/index.html").read_text(encoding="utf-8")
    parser = LandingParser()
    parser.feed(html)
    links = [attrs.get("href") for tag, attrs in parser.elements if tag == "a"]
    assert links.count("/app") >= 8
    assert "#demo" in links
    assert "/privacy" in links
    assert not any("mail.qq.com" in (link or "") for link in links)
    ids = {attrs.get("id") for _, attrs in parser.elements}
    for href in links:
        if href and href.startswith("#"):
            assert href[1:] in ids
    scripts = [attrs for tag, attrs in parser.elements if tag == "script"]
    assert scripts and all(attrs.get("src", "").startswith("/static/marketing/assets/") for attrs in scripts)
    assert all(attrs.get("type") == "module" for attrs in scripts)
    assert not any(name.startswith("on") for _, attrs in parser.elements for name in attrs)
    assert "__PUBLIC_ORIGIN__" in html  # Replaced only by the configured backend origin.
    assert "合成数据" in html and "不写入你的工作区" in html
    assert "当前为试点方案，价格与服务范围按需确认。" in html
    assert "真实任务评估" in html and "按需求报价" in html
    assert any(tag == "noscript" for tag, _ in parser.elements)
    assert sum(tag == "details" for tag, _ in parser.elements) >= 7
    assert any(attrs.get("role") == "tablist" for _, attrs in parser.elements)
    assert any(attrs.get("role") == "status" and attrs.get("aria-live") == "polite" for _, attrs in parser.elements)


def test_landing_sources_keep_safe_dom_and_reduced_motion_contracts():
    sources = PROJECT_ROOT / "landing/src"
    demo = (sources / "demo.ts").read_text(encoding="utf-8")
    entry = (sources / "main.ts").read_text(encoding="utf-8")
    css = (sources / "style.css").read_text(encoding="utf-8")
    assert "innerHTML" not in demo and "insertAdjacentHTML" not in demo
    assert "textContent" in demo
    assert "AbortController" in demo
    assert "prefers-reduced-motion: reduce" in entry and "prefers-reduced-motion: reduce" in css
    assert "IntersectionObserver" in entry and "visibilitychange" in entry
    assert "@import \"tailwindcss\"" in css
    assert "@media (max-width: 560px)" in css
    assert '"strict": true' in (PROJECT_ROOT / "landing/tsconfig.json").read_text(encoding="utf-8")


def test_no_forked_copy_of_the_application_tree_is_vendored():
    """A second app/static tree silently drifts from the live application."""
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
        path for path in PROJECT_ROOT.rglob("*/static/app.js") if keep(path)
    ]
    assert duplicates == []
