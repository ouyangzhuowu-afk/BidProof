"""Rate limiting backed by the database.

The pilot limiter was a dict in one process: it reset on restart, was invisible to a second
worker, and only guarded login. Storing hits in the database means every worker sees the same
counters without introducing another service into an on-premise install.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import HTTPException

from .db import engine
from .models import rate_limit_hits


@dataclass(frozen=True)
class Limit:
    scope: str
    max_hits: int
    window_seconds: int


LOGIN = Limit(
    scope="login",
    max_hits=int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_LIMIT", "5")),
    window_seconds=int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_WINDOW_SECONDS", "900")),
)
MFA = Limit(scope="mfa", max_hits=int(os.environ.get("BIDPROOF_MFA_ATTEMPT_LIMIT", "8")), window_seconds=300)
TOKEN_AUTH = Limit(scope="token-auth", max_hits=int(os.environ.get("BIDPROOF_TOKEN_ATTEMPT_LIMIT", "20")), window_seconds=300)
WRITE = Limit(
    scope="write",
    max_hits=int(os.environ.get("BIDPROOF_WRITE_LIMIT", "240")),
    window_seconds=int(os.environ.get("BIDPROOF_WRITE_WINDOW_SECONDS", "60")),
)
EXPORT = Limit(
    scope="export",
    max_hits=int(os.environ.get("BIDPROOF_EXPORT_LIMIT", "30")),
    window_seconds=int(os.environ.get("BIDPROOF_EXPORT_WINDOW_SECONDS", "300")),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff(limit: Limit, moment: datetime) -> str:
    return (moment - timedelta(seconds=limit.window_seconds)).isoformat()


def count(limit: Limit, bucket: str, path=None, *, moment: datetime | None = None) -> int:
    at = moment or _now()
    statement = sa.select(sa.func.count()).select_from(rate_limit_hits).where(
        rate_limit_hits.c.scope == limit.scope,
        rate_limit_hits.c.bucket == bucket,
        rate_limit_hits.c.occurred_at > _cutoff(limit, at),
    )
    with engine(path).connect() as connection:
        return int(connection.execute(statement).scalar_one())


def record(limit: Limit, bucket: str, path=None, *, moment: datetime | None = None) -> None:
    at = moment or _now()
    with engine(path).begin() as connection:
        connection.execute(
            sa.insert(rate_limit_hits).values(
                hit_id=uuid.uuid4().hex,
                scope=limit.scope,
                bucket=bucket,
                occurred_at=at.isoformat(),
            )
        )
        # Pruning on write keeps the table proportional to the active window instead of growing
        # forever, and avoids needing a separate cleanup job.
        connection.execute(
            sa.delete(rate_limit_hits).where(
                rate_limit_hits.c.scope == limit.scope,
                rate_limit_hits.c.occurred_at <= _cutoff(limit, at),
            )
        )


def retry_after(limit: Limit, bucket: str, path=None, *, moment: datetime | None = None) -> int:
    at = moment or _now()
    statement = (
        sa.select(rate_limit_hits.c.occurred_at)
        .where(
            rate_limit_hits.c.scope == limit.scope,
            rate_limit_hits.c.bucket == bucket,
            rate_limit_hits.c.occurred_at > _cutoff(limit, at),
        )
        .order_by(rate_limit_hits.c.occurred_at)
        .limit(1)
    )
    with engine(path).connect() as connection:
        oldest = connection.execute(statement).scalar()
    if not oldest:
        return limit.window_seconds
    elapsed = (at - datetime.fromisoformat(oldest)).total_seconds()
    return max(1, int(limit.window_seconds - elapsed))


def enforce(limit: Limit, bucket: str, path=None, *, detail: str = "请求过于频繁，请稍后再试") -> None:
    """Raise 429 when the bucket has already used its allowance."""
    if count(limit, bucket, path) >= limit.max_hits:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(retry_after(limit, bucket, path))},
        )


def register_failure(limit: Limit, bucket: str, path=None, *, detail: str = "请求过于频繁，请稍后再试") -> None:
    """Record a failed attempt and raise 429 if it exhausted the allowance."""
    record(limit, bucket, path)
    if count(limit, bucket, path) >= limit.max_hits:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(retry_after(limit, bucket, path))},
        )


def clear(limit: Limit, bucket: str, path=None) -> None:
    with engine(path).begin() as connection:
        connection.execute(
            sa.delete(rate_limit_hits).where(
                rate_limit_hits.c.scope == limit.scope,
                rate_limit_hits.c.bucket == bucket,
            )
        )
