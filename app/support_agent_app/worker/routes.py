"""The worker's single route: authenticate, validate, delegate, translate.

No orchestration lives here. The route maps a lifecycle outcome onto the status
code the queue needs, so a retryable outcome becomes a 503 and Cloud Tasks
retries it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from ..application.deadlines import WorkerDeadline, WorkerDeadlineExceeded
from ..application.failures import WorkerTemporaryError
from ..application.lifecycle import LifecycleOutcome, RequestNotFoundError
from ..application.process_request import WorkerResult
from .auth import TASK_IDENTITY_HEADER, InvalidTaskIdentityError, TaskAuthenticator
from .schemas import ProcessRequest, ProcessResponse

RETRYABLE_OUTCOMES = frozenset(
    {
        LifecycleOutcome.ACTIVE_LEASE.value,
        LifecycleOutcome.RETRYABLE.value,
    }
)


class RequestProcessor(Protocol):
    def process(self, request_id: UUID, deadline: WorkerDeadline) -> WorkerResult: ...


def create_router(
    *,
    authenticator: TaskAuthenticator,
    build_processor: Callable[[], RequestProcessor],
    deadline_seconds: float,
) -> APIRouter:
    router = APIRouter()

    @router.post("/tasks/process-support-request", response_model=ProcessResponse)
    def process_support_request(
        payload: ProcessRequest,
        task_identity: str | None = Header(default=None, alias=TASK_IDENTITY_HEADER),
    ) -> ProcessResponse:
        try:
            authenticator.authenticate(task_identity)
        except InvalidTaskIdentityError as error:
            raise HTTPException(status_code=401, detail="invalid task identity") from error

        try:
            result = build_processor().process(
                payload.request_id,
                WorkerDeadline.after(deadline_seconds),
            )
        except RequestNotFoundError as error:
            raise HTTPException(status_code=404, detail="request not found") from error
        except (WorkerTemporaryError, WorkerDeadlineExceeded) as error:
            raise HTTPException(status_code=503, detail="worker retry required") from error

        if result.outcome in RETRYABLE_OUTCOMES:
            raise HTTPException(status_code=503, detail=result.outcome)
        return ProcessResponse(
            request_id=result.request_id,
            outcome=result.outcome,
            send_attempted=result.send_attempted,
        )

    return router
