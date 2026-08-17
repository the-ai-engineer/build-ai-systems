"""The support-request lifecycle vocabulary, independent of any database.

A worker claims a request, and every later change carries that `Claim`. The
claim is a fencing token: a store must reject changes from a claim that a newer
lease has superseded, which is what stops two workers replying to one employee.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_BUSINESS_ATTEMPTS = 5
FIRST_TASK_GENERATION = 1


def task_name_for(slack_event_id: str, task_generation: int = FIRST_TASK_GENERATION) -> str:
    """Return the stable task name for one Slack event and task generation.

    The name is derived, not random, so a Slack retry of the same event asks the
    queue to create the same task. The queue then rejects the duplicate, which
    is how one mention stays one unit of work even when the webhook runs twice.
    """

    if not slack_event_id:
        raise ValueError("slack_event_id is required")
    if task_generation < 1:
        raise ValueError("task_generation starts at 1")
    digest = hashlib.sha256(f"{slack_event_id}:{task_generation}".encode()).hexdigest()
    return f"support-{digest}"


class LifecycleOutcome(StrEnum):
    CLAIMED = "claimed"
    DUPLICATE_COMPLETE = "duplicate-complete"
    ACTIVE_LEASE = "active-lease"
    RETRYABLE = "retryable"
    PERMANENT_FAILURE = "permanent-failure"
    RECONCILIATION = "reconciliation"


class RequestLifecycleError(RuntimeError):
    """Base class for invalid lifecycle operations."""


class RequestNotFoundError(RequestLifecycleError):
    pass


class StaleClaimError(RequestLifecycleError):
    pass


class StateConflictError(RequestLifecycleError):
    pass


class ActionConflictError(RequestLifecycleError):
    pass


class TaskAlreadyQueuedError(RequestLifecycleError):
    """The queue already holds a task with this name.

    Not a failure. It means an earlier delivery of the same Slack event already
    created the work, so the request is queued and there is nothing more to do.
    """


@dataclass(frozen=True)
class IncomingSupportRequest:
    slack_event_id: str
    slack_team_id: str
    slack_channel_id: str
    slack_message_ts: str
    slack_thread_ts: str
    slack_user_id: str
    question_text: str


@dataclass(frozen=True)
class AcceptedRequest:
    request_id: UUID
    created: bool


@dataclass(frozen=True)
class Claim:
    request_id: UUID
    claim_token: UUID
    lease_version: int
    business_attempt_number: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class ClaimResult:
    outcome: LifecycleOutcome
    claim: Claim | None = None


@dataclass(frozen=True)
class ClaimedRequest:
    request_id: UUID
    slack_channel_id: str
    slack_thread_ts: str
    question_text: str = field(repr=False)


@dataclass(frozen=True)
class OutboundAction:
    action_id: UUID
    request_id: UUID
    action_generation: int
    status: str
    outbound_text: str
    content_hash: str
