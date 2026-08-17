"""In-memory doubles for the ingress path, so webhook tests need no Postgres."""

from __future__ import annotations

from uuid import UUID, uuid4

from support_agent_app.application.lifecycle import (
    AcceptedRequest,
    IncomingSupportRequest,
    TaskAlreadyQueuedError,
)


class FakeIntake:
    """Records requests and enforces the one-request-per-event rule."""

    def __init__(self) -> None:
        self.by_event_id: dict[str, UUID] = {}
        self.queued: list[tuple[UUID, str | None]] = []
        self.accepted: list[IncomingSupportRequest] = []

    def accept_request(self, incoming: IncomingSupportRequest) -> AcceptedRequest:
        self.accepted.append(incoming)
        existing = self.by_event_id.get(incoming.slack_event_id)
        if existing is not None:
            return AcceptedRequest(request_id=existing, created=False)
        request_id = uuid4()
        self.by_event_id[incoming.slack_event_id] = request_id
        return AcceptedRequest(request_id=request_id, created=True)

    def mark_queued(self, request_id: UUID, *, confirmed_task_name: str | None = None) -> None:
        self.queued.append((request_id, confirmed_task_name))


class FakeQueue:
    """Accepts task names once, and can be told to fail."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.names: list[str] = []
        self.request_ids: list[UUID] = []
        self.fail_with = fail_with

    def enqueue_support_request(self, *, request_id: UUID, task_name: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        if task_name in self.names:
            raise TaskAlreadyQueuedError(task_name)
        self.names.append(task_name)
        self.request_ids.append(request_id)
