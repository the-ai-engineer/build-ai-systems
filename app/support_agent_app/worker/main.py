"""Composition root for the private worker process.

This is the one module allowed to name concrete adapters. It reads settings,
picks a Postgres store, a Slack client, and a model, and hands them to the use
case. Everything below it depends only on protocols.

Run it with:

    uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import FastAPI

from ..agent.agent import run_support_workflow
from ..application.failures import WorkerTemporaryError
from ..application.process_request import WorkerService
from ..database.repositories.policy_repository import PostgresPolicyRepository
from ..database.repositories.support_request_repository import PostgresSupportRepository
from ..integrations.messaging import SlackWebApiClient
from ..settings import WorkerBoundarySettings, WorkerSettings
from .auth import StaticTaskAuthenticator, TaskAuthenticator
from .routes import RequestProcessor, create_router


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
    build_processor: Callable[[], RequestProcessor]
    build_processor = (lambda: service) if service is not None else build_default_service

    app = FastAPI(title="HR policy support worker")
    app.include_router(
        create_router(
            authenticator=selected_authenticator,
            build_processor=build_processor,
            deadline_seconds=(
                settings.worker_deadline_seconds if deadline_seconds is None else deadline_seconds
            ),
        )
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
