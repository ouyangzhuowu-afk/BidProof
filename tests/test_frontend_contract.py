"""Frontend engineering constraints: Vite modules, escaped render, shipping palette."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
STATIC = ROOT / "static"


def test_shipping_palette_is_the_light_teal_workbench():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    master = (ROOT / "design-system" / "bidproof" / "MASTER.md").read_text(encoding="utf-8")

    assert "--primary: #087f72" in css
    assert "#087f72" in master
    assert "canonical" in master


def test_app_source_is_es_modules_with_a_single_store():
    app = (SRC / "app.js").read_text(encoding="utf-8")
    state = (SRC / "state.js").read_text(encoding="utf-8")
    render = (SRC / "ui" / "render.js").read_text(encoding="utf-8")
    tsconfig = (ROOT / "frontend" / "tsconfig.json").read_text(encoding="utf-8")
    vite = (ROOT / "frontend" / "vite.config.js").read_text(encoding="utf-8")

    assert re.search(r"import\s*\{[^}]*\bstore\b[^}]*\}\s*from\s*[\"']\./state\.js[\"']", app)
    assert "export const store" in state
    assert "export function html" in render
    assert "export function mount" in render
    assert '"allowJs": true' in tsconfig
    assert "formats: ['iife']" in vite
    assert "let currentRun" not in app
    assert "store.currentRun" in app
    assert not (SRC / "escape.js").exists()


def test_innerhtml_assignments_go_through_sethtml():
    """Render paths must not assign innerHTML except through setHtml, which requires SafeHtml."""
    app = (SRC / "app.js").read_text(encoding="utf-8")
    assignments = re.findall(r"\.innerHTML\s*=", app)
    assert assignments == []
    assert "setHtml(" in app
    assert app.count("raw(") == 1


def test_built_bundle_keeps_the_ui_contract_function_names():
    bundle = (STATIC / "app.js").read_text(encoding="utf-8")
    for name in ("showJobs", "reloadJobs", "showAdmin", "cancelJob"):
        assert f"function {name}" in bundle
    assert "mount" in bundle or "setHtml" in bundle
    assert "function escapeHtml" in (SRC / "ui" / "render.js").read_text(encoding="utf-8")
