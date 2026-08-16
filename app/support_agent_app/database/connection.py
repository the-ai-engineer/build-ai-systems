"""Small Postgres connection helper with an explicit operation budget."""

from __future__ import annotations

import math

from psycopg import connect


def connect_with_timeout(database_url: str, *, row_factory=None, timeout_seconds=None):
    kwargs = {}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            raise TimeoutError("database operation deadline expired")
        timeout_ms = max(1, min(2_147_483_647, int(timeout_seconds * 1_000)))
        kwargs["connect_timeout"] = max(1, math.ceil(timeout_seconds))
        kwargs["options"] = f"-c statement_timeout={timeout_ms}"
    return connect(database_url, **kwargs)
