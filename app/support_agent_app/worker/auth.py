"""Authentication seam for local and future Cloud Tasks identities.

`StaticTaskAuthenticator` is a shared-secret stand-in. The queue lesson swaps in
Google OIDC verification behind the same `TaskAuthenticator` protocol, so no
route or use case changes.
"""

from __future__ import annotations

import secrets
from typing import Protocol

from ..application.protocols import TASK_IDENTITY_HEADER
from ..settings import LOCAL_TASK_IDENTITY

__all__ = [
    "TASK_IDENTITY_HEADER",
    "InvalidTaskIdentityError",
    "StaticTaskAuthenticator",
    "TaskAuthenticator",
]


class InvalidTaskIdentityError(PermissionError):
    pass


class TaskAuthenticator(Protocol):
    def authenticate(self, presented_identity: str | None) -> None: ...


class StaticTaskAuthenticator:
    """Local identity check that is replaceable with Google OIDC verification."""

    def __init__(self, expected_identity: str = LOCAL_TASK_IDENTITY) -> None:
        if not expected_identity:
            raise ValueError("expected_identity is required")
        self._expected_identity = expected_identity

    def authenticate(self, presented_identity: str | None) -> None:
        if presented_identity is None or not secrets.compare_digest(
            presented_identity.encode("utf-8"),
            self._expected_identity.encode("utf-8"),
        ):
            raise InvalidTaskIdentityError("invalid task identity")
