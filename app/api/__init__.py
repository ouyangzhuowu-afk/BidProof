"""HTTP surface.

Routers translate requests into service calls. Literal paths are registered before
parameterised ones so `/api/runs/bulk/report.zip` cannot be captured by `/api/runs/{run_id}`.
"""

from fastapi import FastAPI

from . import admin, auth, health, jobs, members, projects, reports, runs


def register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(projects.router)
    app.include_router(reports.router)
    app.include_router(runs.router)
    app.include_router(runs.remediation_router)
    app.include_router(jobs.router)
    app.include_router(admin.router)


__all__ = ["register_routers"]
