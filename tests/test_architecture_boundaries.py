"""Structural contract for the layering introduced in P1.

These guard the boundaries that make the persistence and queue work in later phases tractable:
routes stay thin, services stay free of HTTP request objects, and data access is funnelled
through the repository package.
"""

import ast
from pathlib import Path

from fastapi import FastAPI

from app.api import register_routers
from app.main import app


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
MAIN = APP_ROOT / "main.py"


def _module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def test_main_only_assembles_the_application():
    source = MAIN.read_text(encoding="utf-8")
    definitions = _module_names(MAIN)

    # main.py was a 1707-line module holding all 62 routes; it now only wires the app together.
    assert len(source.splitlines()) < 80
    assert definitions == {"lifespan", "create_app"}
    assert "@app." not in source
    assert "APIRouter" not in source


def test_importing_the_app_does_not_create_the_schema_as_a_side_effect():
    source = MAIN.read_text(encoding="utf-8")

    # Schema creation belongs to the first database connection, so a worker or CLI does not
    # have to import the web application to get a usable database.
    assert "init_db" not in source


def test_every_route_lives_in_the_api_package():
    routers = sorted(path.stem for path in (APP_ROOT / "api").glob("*.py") if path.stem != "__init__")

    assert routers == ["admin", "auth", "health", "jobs", "members", "projects", "reports", "runs"]
    for name in routers:
        assert "@router." in (APP_ROOT / "api" / f"{name}.py").read_text(encoding="utf-8")


def test_registered_route_surface_is_stable():
    fresh = FastAPI()
    register_routers(fresh)

    operations = {
        f"{method.upper()} {path}"
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in {"get", "post", "patch", "delete", "put"}
    }

    assert len(operations) == 79
    assert "POST /api/runs" in operations
    # A literal path registered after its parameterised sibling would be shadowed by it.
    assert "POST /api/auth/mfa/verify" in operations
    assert "POST /api/auth/register" in operations
    assert "POST /api/runs/bulk/report.zip" in operations
    assert "POST /api/runs/{run_id}/rescan" in operations


def _parameters_annotated_as_request(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    annotated: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]
        for argument in arguments:
            annotation = argument.annotation
            if isinstance(annotation, ast.Name) and annotation.id in {"Request", "Response"}:
                annotated.add(f"{node.name}.{argument.arg}")
    return annotated


def test_services_take_a_principal_rather_than_a_request():
    """The scan pipeline used to re-enter the HTTP handler with a synthetic request object.

    Keeping request and response types out of the workflow services is what lets the same
    `create_run` serve an interactive upload and a queued job.
    """
    for path in (APP_ROOT / "services").glob("*.py"):
        if path.stem == "auth_service":
            # Login and session issuance legitimately read cookies and set the session cookie.
            continue
        assert _parameters_annotated_as_request(path) == set(), path.name


def test_routes_reach_storage_through_repositories():
    for path in (APP_ROOT / "api").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from ..db import" not in source, path.name
        assert "from .. import db" not in source, path.name
