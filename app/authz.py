"""Permissions.

Roles used to be checked as a set membership test at each route, which made every mutating
role equivalent and let a VIEWER export the audit trail and bulk reports. Permissions are
named here once and each role is granted an explicit set.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import HTTPException


class Permission(StrEnum):
    RUN_READ = "run:read"
    RUN_CREATE = "run:create"
    RUN_UPDATE = "run:update"
    RUN_DELETE = "run:delete"
    RUN_REVIEW = "run:review"
    RUN_DECIDE = "run:decide"
    REPORT_EXPORT = "report:export"
    REPORT_BULK_EXPORT = "report:bulk-export"
    EVIDENCE_DOWNLOAD = "evidence:download"
    JOB_READ = "job:read"
    JOB_MANAGE = "job:manage"
    MEMBER_READ = "member:read"
    MEMBER_MANAGE = "member:manage"
    PROJECT_MANAGE = "project:manage"
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_MANAGE = "workspace:manage"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    BACKUP_MANAGE = "backup:manage"
    RETENTION_MANAGE = "retention:manage"
    TOKEN_MANAGE = "token:manage"
    METRICS_READ = "metrics:read"
    HEALTH_DETAIL_READ = "health:detail"


VIEWER_PERMISSIONS = frozenset({
    Permission.RUN_READ,
    Permission.JOB_READ,
    Permission.MEMBER_READ,
    Permission.WORKSPACE_READ,
    Permission.METRICS_READ,
})

REVIEWER_PERMISSIONS = VIEWER_PERMISSIONS | {
    Permission.RUN_CREATE,
    Permission.RUN_UPDATE,
    Permission.RUN_REVIEW,
    Permission.RUN_DECIDE,
    Permission.REPORT_EXPORT,
    Permission.EVIDENCE_DOWNLOAD,
    Permission.JOB_MANAGE,
    Permission.AUDIT_READ,
    Permission.HEALTH_DETAIL_READ,
}

ADMIN_PERMISSIONS = REVIEWER_PERMISSIONS | {
    Permission.RUN_DELETE,
    Permission.REPORT_BULK_EXPORT,
    Permission.MEMBER_MANAGE,
    Permission.PROJECT_MANAGE,
    Permission.WORKSPACE_MANAGE,
    Permission.AUDIT_EXPORT,
    Permission.BACKUP_MANAGE,
    Permission.RETENTION_MANAGE,
    Permission.TOKEN_MANAGE,
}

OWNER_PERMISSIONS = frozenset(Permission)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "OWNER": OWNER_PERMISSIONS,
    "ADMIN": frozenset(ADMIN_PERMISSIONS),
    "REVIEWER": frozenset(REVIEWER_PERMISSIONS),
    "VIEWER": VIEWER_PERMISSIONS,
}

ROLES = tuple(ROLE_PERMISSIONS)


def permissions_for(role: str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role.upper(), frozenset())


def has_permission(principal: dict, permission: Permission) -> bool:
    granted = permissions_for(principal.get("role", ""))
    scoped = principal.get("permissions")
    if scoped is not None:
        # An API token may hold a subset of its owner's role.
        granted = granted & _as_permissions(scoped)
    return permission in granted


def _as_permissions(values) -> frozenset[Permission]:
    parsed: set[Permission] = set()
    for value in values:
        try:
            parsed.add(value if isinstance(value, Permission) else Permission(str(value)))
        except ValueError:
            continue
    return frozenset(parsed)


def require(principal: dict, permission: Permission) -> None:
    if not has_permission(principal, permission):
        raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")
