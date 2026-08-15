"""Private FastAPI boundary for processing one stored request ID."""

from __future__ import annotations

import os
from typing import Protocol, cast
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from .fake_model import FixtureName, fixture_model
from .repositories import PostgresPolicyRepository
from .request_repository import LifecycleOutcome, PostgresSupportRepository, RequestNotFoundError
from .slack_actions import FakeSlackClient, SlackWebApiClient
from .worker_auth import (
    LOCAL_TASK_IDENTITY,
    TASK_IDENTITY_HEADER,
    InvalidTaskIdentityError,
    StaticTaskAuthenticator,
    TaskAuthenticator,
)
from .worker_service import (
    DEFAULT_WORKER_DEADLINE_SECONDS,
    WorkerDeadline,
    WorkerDeadlineExceeded,
    WorkerResult,
    WorkerService,
    WorkerTemporaryError,
)


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID


class ProcessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    outcome: str
    send_attempted: bool


class RequestProcessor(Protocol):
    def process(self, request_id: UUID, deadline: WorkerDeadline) -> WorkerResult: ...


def create_app(
    *,
    service: RequestProcessor | None = None,
    authenticator: TaskAuthenticator | None = None,
    deadline_seconds: float = DEFAULT_WORKER_DEADLINE_SECONDS,
) -> FastAPI:
    selected_authenticator = authenticator or StaticTaskAuthenticator(
        os.getenv("WORKER_EXPECTED_TASK_IDENTITY", LOCAL_TASK_IDENTITY)
    )
    app = FastAPI(title="HR policy support worker")

    @app.post("/tasks/process-support-request", response_model=ProcessResponse)
    def process_support_request(
        payload: ProcessRequest,
        task_identity: str | None = Header(default=None, alias=TASK_IDENTITY_HEADER),
    ) -> ProcessResponse:
        try:
            selected_authenticator.authenticate(task_identity)
        except InvalidTaskIdentityError as error:
            raise HTTPException(status_code=401, detail="invalid task identity") from error

        try:
            processor = service or build_default_service()
            result = processor.process(
                payload.request_id,
                WorkerDeadline.after(deadline_seconds),
            )
        except RequestNotFoundError as error:
            raise HTTPException(status_code=404, detail="request not found") from error
        except (WorkerTemporaryError, WorkerDeadlineExceeded) as error:
            raise HTTPException(status_code=503, detail="worker retry required") from error

        if result.outcome in {
            LifecycleOutcome.ACTIVE_LEASE.value,
            LifecycleOutcome.RETRYABLE.value,
        }:
            raise HTTPException(status_code=503, detail=result.outcome)
        return ProcessResponse(
            request_id=result.request_id,
            outcome=result.outcome,
            send_attempted=result.send_attempted,
        )

    return app


def build_default_service() -> WorkerService:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise WorkerTemporaryError("DATABASE_URL is required")

    adapter_mode = os.getenv("WORKER_ADAPTER_MODE", "fake")
    if adapter_mode == "fake":
        fixture_name = os.getenv("WORKER_FAKE_FIXTURE", "documented")
        allowed_fixtures = (
            "documented",
            "unsupported",
            "sensitive",
            "conflicting",
            "prompt-injection",
            "invalid-evidence",
        )
        if fixture_name not in allowed_fixtures:
            raise WorkerTemporaryError("WORKER_FAKE_FIXTURE is invalid")
        model = fixture_model(cast(FixtureName, fixture_name))
        slack = FakeSlackClient()
    elif adapter_mode == "configured":
        model = None
        bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        if not bot_token:
            raise WorkerTemporaryError("SLACK_BOT_TOKEN is required")
        slack = SlackWebApiClient(bot_token)
    else:
        raise WorkerTemporaryError("WORKER_ADAPTER_MODE is invalid")

    return WorkerService(
        requests=PostgresSupportRepository(database_url),
        policies=PostgresPolicyRepository(database_url),
        model=model,
        slack=slack,
    )


app = create_app()
