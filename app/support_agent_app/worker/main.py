"""The private worker runtime: one route, and the wiring behind it.

The worker has a single job, so it is a single file. It holds the wire schemas,
the route, and the composition root together because reading them in order is
how you understand what the worker does.

This is the only module here allowed to name concrete adapters. Everything it
hands to `WorkerService` is a protocol from `application/protocols.py`.

Run it with:

    uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
"""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from ..application.lifecycle import LifecycleOutcome, RequestNotFoundError
from ..database.repositories.policy_repository import PostgresPolicyRepository
from ..database.repositories.support_request_repository import PostgresSupportRepository
from ..settings import WorkerBoundarySettings, WorkerSettings
from .agent.agent import run_support_workflow
from .auth import (
    TASK_IDENTITY_HEADER,
    InvalidTaskIdentityError,
    StaticTaskAuthenticator,
    TaskAuthenticator,
)
from .deadlines import WorkerDeadline, WorkerDeadlineExceeded
from .failures import WorkerTemporaryError
from .messaging import SlackWebApiClient
from .process_request import WorkerResult, WorkerService

RETRYABLE_OUTCOMES = frozenset(
    {
        LifecycleOutcome.ACTIVE_LEASE.value,
        LifecycleOutcome.RETRYABLE.value,
    }
)


class ProcessRequest(BaseModel):
    """The task payload: a request ID and nothing else.

    The employee's question stays in the database, so the queue never carries
    sensitive content.
    """

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
    boundary_settings: WorkerBoundarySettings | None = None,
    deadline_seconds: float | None = None,
) -> FastAPI:
    settings = boundary_settings or WorkerBoundarySettings.load()
    selected_authenticator = authenticator or StaticTaskAuthenticator(
        settings.worker_expected_task_identity
    )
    budget = settings.worker_deadline_seconds if deadline_seconds is None else deadline_seconds

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
            processor = service if service is not None else build_default_service()
            result = processor.process(payload.request_id, WorkerDeadline.after(budget))
        except RequestNotFoundError as error:
            raise HTTPException(status_code=404, detail="request not found") from error
        except (WorkerTemporaryError, WorkerDeadlineExceeded) as error:
            raise HTTPException(status_code=503, detail="worker retry required") from error

        # A retryable outcome becomes a 503 so the queue delivers the task again.
        if result.outcome in RETRYABLE_OUTCOMES:
            raise HTTPException(status_code=503, detail=result.outcome)
        return ProcessResponse(
            request_id=result.request_id,
            outcome=result.outcome,
            send_attempted=result.send_attempted,
        )

    return app


def build_default_service(settings: WorkerSettings | None = None) -> WorkerService:
    """Assemble the real worker from configuration.

    Fixture adapters are opt-in. `WORKER_ADAPTER_MODE` defaults to `configured`,
    so a misconfigured deployment fails loudly instead of quietly answering
    employees from a canned model and swallowing the Slack reply.
    """

    try:
        resolved = settings or WorkerSettings.load()
    except Exception as error:
        raise WorkerTemporaryError("worker configuration is incomplete") from error

    if resolved.worker_adapter_mode == "local-fixtures":
        from ..testing.fake_model import FixtureName, fixture_model
        from ..testing.fake_slack import FakeSlackClient
        from ..testing.fixtures import FIXTURE_NAMES

        if resolved.worker_fake_fixture not in FIXTURE_NAMES:
            raise WorkerTemporaryError("WORKER_FAKE_FIXTURE is invalid")
        model: object | None = fixture_model(cast(FixtureName, resolved.worker_fake_fixture))
        slack = FakeSlackClient()
    else:
        model = None
        bot_token = resolved.slack_bot_token.get_secret_value()
        if not bot_token:
            raise WorkerTemporaryError("SLACK_BOT_TOKEN is required")
        slack = SlackWebApiClient(bot_token)

    return WorkerService(
        requests=PostgresSupportRepository(resolved.database_url),
        policies=PostgresPolicyRepository(resolved.database_url),
        model=model,
        slack=slack,
        workflow_runner=run_support_workflow,
    )
