"""Authentication seam for local and future Cloud Tasks identities."""

from __future__ import annotations

import secrets
from typing import Protocol


LOCAL_TASK_IDENTITY = "local-development-task"
TASK_IDENTITY_HEADER = "X-Worker-Task-Identity"


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
            presented_identity,
            self._expected_identity,
        ):
            raise InvalidTaskIdentityError("invalid task identity")
