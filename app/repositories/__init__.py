"""Data access boundary.

Routes and services go through these modules instead of calling `app.db` directly, so the
persistence swap in P2 (SQLAlchemy Core + PostgreSQL) has a single surface to replace.
"""

from . import accounts, audit, collaboration, identity, jobs, projects, runs, workspaces

__all__ = ["accounts", "audit", "collaboration", "identity", "jobs", "projects", "runs", "workspaces"]
