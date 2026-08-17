"""Boundaries the application owns and adapters implement.

The use case in `process_request.py` depends only on these. Concrete Postgres,
Slack, and model adapters are supplied by a composition root such as
`worker/main.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from .domain import (
    SupportDecision,
    SupportDocument,
    SupportDocumentIndexItem,
    SupportQuestion,
    WorkflowOutcome,
)
from .lifecycle import (
    AcceptedRequest,
    Claim,
    ClaimedRequest,
    ClaimResult,
    IncomingSupportRequest,
    LifecycleOutcome,
    OutboundAction,
)


class PolicyRepository(Protocol):
    """The complete knowledge capability exposed to the agent."""

    def list_active_documents(self) -> list[SupportDocumentIndexItem]: ...

    def get_active_document(self, document_id: str) -> SupportDocument | None: ...


@runtime_checkable
class TimeoutAwarePolicyRepository(PolicyRepository, Protocol):
    """A policy repository that can be rebound to the caller's remaining budget."""

    def with_timeout_provider(
        self,
        timeout_provider: Callable[[], float],
    ) -> PolicyRepository: ...


class SupportRequestStore(Protocol):
    """Durable support-request lifecycle, including fenced worker claims.

    Every worker-owned change takes a `Claim`. An implementation must reject a
    claim that a newer lease has superseded.
    """

    def claim_request(
        self,
        request_id: UUID,
        lease_duration: timedelta,
        *,
        timeout_seconds: float | None = None,
    ) -> ClaimResult: ...

    def load_claimed_request(
        self,
        claim: Claim,
        *,
        timeout_seconds: float | None = None,
    ) -> ClaimedRequest: ...

    def load_latest_decision(
        self,
        claim: Claim,
        *,
        timeout_seconds: float | None = None,
    ) -> SupportDecision | None: ...

    def find_failed_reply_action(
        self,
        claim: Claim,
        *,
        timeout_seconds: float | None = None,
    ) -> OutboundAction | None: ...

    def find_stranded_reply_action(
        self,
        claim: Claim,
        *,
        timeout_seconds: float | None = None,
    ) -> OutboundAction | None: ...

    def record_workflow_result(
        self,
        claim: Claim,
        outcome: WorkflowOutcome,
        *,
        timeout_seconds: float | None = None,
    ) -> UUID: ...

    def create_reply_action(
        self,
        claim: Claim,
        outbound_text: str,
        *,
        action_generation: int = 1,
        timeout_seconds: float | None = None,
    ) -> OutboundAction: ...

    def retry_failed_reply(
        self,
        claim: Claim,
        failed_action_id: UUID,
        *,
        timeout_seconds: float | None = None,
    ) -> OutboundAction: ...

    def reconcile_stranded_reply(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        timeout_seconds: float | None = None,
    ) -> LifecycleOutcome: ...

    def mark_action_sending(
        self,
        claim: Claim,
        action_id: UUID,
        *,
        timeout_seconds: float | None = None,
    ) -> None: ...

    def complete_reply(
        self,
        claim: Claim,
        action_id: UUID,
        slack_message_ts: str,
        *,
        timeout_seconds: float | None = None,
    ) -> None: ...

    def mark_action_failed(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        retryable: bool,
        timeout_seconds: float | None = None,
    ) -> LifecycleOutcome: ...

    def mark_unsent_action_failed(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        retryable: bool,
        timeout_seconds: float | None = None,
    ) -> LifecycleOutcome: ...

    def mark_action_uncertain(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        timeout_seconds: float | None = None,
    ) -> LifecycleOutcome: ...

    def record_failure(
        self,
        claim: Claim,
        error_category: str,
        *,
        retryable: bool,
        timeout_seconds: float | None = None,
    ) -> LifecycleOutcome: ...


class SlackClient(Protocol):
    """One controlled outbound action, with no provider detail exposed."""

    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str: ...


class AgentRunner(Protocol):
    """Run the policy agent and return a verified decision plus run evidence.

    `model` is deliberately untyped here. The application knows a model gets
    passed through to the agent; it does not know which SDK defines it.
    """

    def __call__(
        self,
        question: SupportQuestion,
        repository: PolicyRepository,
        *,
        model: Any = None,
        model_timeout_seconds: float = ...,
    ) -> WorkflowOutcome: ...


class SupportRequestIntake(Protocol):
    """The ingress capability the public Slack webhook uses."""

    def accept_request(self, incoming: IncomingSupportRequest) -> AcceptedRequest: ...

    def mark_queued(self, request_id: UUID, *, confirmed_task_name: str | None = None) -> None: ...


class TaskQueue(Protocol):
    """Hand one request ID to a queue for later delivery to the worker.

    Enqueueing is expected to return quickly and say only whether the queue
    accepted the task. Delivery, retries, and backoff belong to the queue.

    Raise `TaskAlreadyQueuedError` when the name already exists, which is the
    queue rejecting a duplicate rather than a failure.
    """

    def enqueue_support_request(self, *, request_id: UUID, task_name: str) -> None: ...


__all__ = [
    "AgentRunner",
    "PolicyRepository",
    "SlackClient",
    "SupportRequestIntake",
    "SupportRequestStore",
    "TaskQueue",
    "TimeoutAwarePolicyRepository",
]
