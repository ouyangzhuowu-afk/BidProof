"""Request-scoped transaction helper.

Services that must write several tables together should use `transaction()` so a failure
cannot commit a partial evidence chain.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy.engine import Connection


_active: ContextVar[Connection | None] = ContextVar("bidproof_uow", default=None)


def current_connection() -> Connection | None:
    return _active.get()


@contextmanager
def transaction(path=None) -> Iterator[Connection]:
    existing = _active.get()
    if existing is not None:
        yield existing
        return
    from .db import engine as get_engine

    with get_engine(path).begin() as connection:
        token = _active.set(connection)
        try:
            yield connection
        finally:
            _active.reset(token)
