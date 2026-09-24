"""Atomic OTP lifecycle; writes are shared by all application workers."""
from __future__ import annotations

import secrets
import threading
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..db import engine
from ..models import auth_challenges as table
from ..models import auth_delivery_guards as guards

# Also support the shared connection of in-memory test databases; file SQLite/PostgreSQL
# use independent connections. Conditional SQL remains the cross-process authority.
_lock = threading.RLock()


def reserve(fields: dict, now: datetime, cooldown: int) -> int:
    """Return retry seconds, or zero after atomically reserving delivery."""
    with _lock, engine().begin() as connection:
        insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
        cutoff = (now - timedelta(seconds=cooldown)).isoformat()
        result = connection.execute(insert(guards).values(
            bucket=fields["identifier_digest"], sent_at=now.isoformat(),
        ).on_conflict_do_update(
            index_elements=[guards.c.bucket], set_={"sent_at": now.isoformat()},
            where=guards.c.sent_at <= cutoff,
        ).returning(guards.c.bucket)).scalar_one_or_none()
        if result is None:
            sent = connection.execute(sa.select(guards.c.sent_at).where(
                guards.c.bucket == fields["identifier_digest"])).scalar_one()
            return max(1, int(cooldown - (now - datetime.fromisoformat(sent)).total_seconds()) + 1)
        # Resending invalidates every earlier challenge, including a delayed delivery.
        connection.execute(sa.update(table).where(
            table.c.identifier_digest == fields["identifier_digest"], table.c.consumed_at.is_(None),
        ).values(consumed_at=now.isoformat()))
        connection.execute(sa.insert(table).values(**fields))
        stale = (now - timedelta(days=1)).isoformat()
        connection.execute(sa.delete(table).where(table.c.created_at < stale))
        connection.execute(sa.delete(guards).where(guards.c.sent_at < stale))
    return 0


def mark_delivery(challenge_id: str, *, successful: bool) -> None:
    with _lock, engine().begin() as connection:
        values = {"delivered": 1} if successful else {"consumed_at": datetime.now(UTC).isoformat()}
        connection.execute(sa.update(table).where(table.c.challenge_id == challenge_id).values(**values))


def verify(challenge_id: str, submitted_digest: str, now: datetime) -> tuple[str, dict | None]:
    """Count every guess, claim a correct code once; never return a code digest to callers."""
    with _lock, engine().begin() as connection:
        snapshot = connection.execute(sa.update(table).where(
            table.c.challenge_id == challenge_id, table.c.expires_at > now.isoformat(),
            table.c.consumed_at.is_(None), table.c.delivered == 1, table.c.attempts < 5,
        ).values(attempts=table.c.attempts + 1).returning(table)).mappings().first()
        if snapshot is None:
            row = connection.execute(sa.select(table.c.attempts).where(table.c.challenge_id == challenge_id)).first()
            return ("locked" if row and row.attempts >= 5 else "expired"), None
        if not secrets.compare_digest(snapshot["code_digest"], submitted_digest):
            return ("locked" if snapshot["attempts"] >= 5 else "incorrect"), None
        claimed = connection.execute(sa.update(table).where(
            table.c.challenge_id == challenge_id, table.c.consumed_at.is_(None),
            table.c.attempts == snapshot["attempts"],
        ).values(consumed_at=now.isoformat()).returning(table.c.challenge_id)).scalar_one_or_none()
        if claimed is None:
            return "expired", None
        return "verified", {"channel": snapshot["channel"], "identifier": snapshot["identifier"]}


def consume_limit(scope: str, bucket: str, maximum: int, window_seconds: int) -> int:
    """Atomic fixed-window limiter. Returns zero when allowed, retry seconds otherwise."""
    from ..models import auth_rate_limits as limits

    now = datetime.now(UTC)
    with _lock, engine().begin() as connection:
        insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
        expired = limits.c.window_started_at <= (now - timedelta(seconds=window_seconds)).isoformat()
        capped_increment = sa.case((limits.c.hits <= maximum, limits.c.hits + 1), else_=limits.c.hits)
        row = connection.execute(insert(limits).values(
            bucket=scope + ":" + bucket, window_started_at=now.isoformat(), hits=1,
        ).on_conflict_do_update(index_elements=[limits.c.bucket], set_={
            "window_started_at": sa.case(
                (expired, sa.literal(now.isoformat(), type_=limits.c.window_started_at.type)),
                else_=limits.c.window_started_at),
            "hits": sa.case((expired, 1), else_=capped_increment),
        }).returning(limits.c.window_started_at, limits.c.hits)).one()
        connection.execute(sa.delete(limits).where(
            limits.c.window_started_at < (now - timedelta(days=1)).isoformat()))
        if row.hits <= maximum:
            return 0
        return max(1, int(window_seconds - (now - datetime.fromisoformat(row.window_started_at)).total_seconds()) + 1)
