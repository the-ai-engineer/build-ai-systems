"""The public Slack webhook: verify, normalize, store, queue, acknowledge.

Slack expects a response within three seconds and retries when it does not get
one. Everything slow therefore belongs to the worker. This file must never call
a model or read a policy document (INV-2).

The route answers 2xx in two situations that look alike but are not:

- an event this app does not handle, so Slack stops retrying something it was
  never going to act on
- a valid mention that is now durable and queued

It answers non-2xx only when a retry could actually help.

Run it with:

    uv run uvicorn support_agent_app.api.main:create_app --factory --port 8080
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Request, Response

from ..application.accept_request import (
    AcceptedForProcessing,
    RequestNotQueuedError,
    accept_and_queue,
)
from ..application.lifecycle import IncomingSupportRequest
from ..application.protocols import SupportRequestIntake, TaskQueue
from ..database.repositories.support_request_repository import PostgresSupportRepository
from ..integrations.task_queue import LocalTaskQueue
from ..settings import ApiSettings
from ..worker.auth import TASK_IDENTITY_HEADER
from .auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    InvalidSlackSignatureError,
    SlackSignatureVerifier,
)

logger = logging.getLogger(__name__)

SLACK_EVENTS_PATH = "/slack/events"
MAX_QUESTION_LENGTH = 2_000

# Slack writes a mention as <@U123> or <@U123|name>. Strip every mention, not
# only the leading one, so what gets stored is what the employee actually asked.
MENTION_PATTERN = re.compile(r"<@[UW][A-Z0-9]+(?:\|[^>]*)?>")


class RequestAccepter(Protocol):
    def __call__(
        self,
        incoming: IncomingSupportRequest,
        *,
        requests: SupportRequestIntake,
        queue: TaskQueue,
    ) -> AcceptedForProcessing: ...


class UnsupportedEvent(Exception):
    """A validly signed request this app does not turn into work."""


def create_app(
    *,
    settings: ApiSettings | None = None,
    verifier: SlackSignatureVerifier | None = None,
    requests: SupportRequestIntake | None = None,
    queue: TaskQueue | None = None,
    accepter: RequestAccepter = accept_and_queue,
) -> FastAPI:
    resolved = settings or ApiSettings.load()
    selected_verifier = verifier or SlackSignatureVerifier(
        resolved.slack_signing_secret.get_secret_value()
    )
    allowed_teams = resolved.allowed_team_ids()
    allowed_channels = resolved.allowed_channel_ids()

    owns_queue = queue is None
    selected_queue: TaskQueue = queue or LocalTaskQueue(
        worker_base_url=resolved.worker_base_url,
        task_identity=resolved.worker_task_identity,
        identity_header=TASK_IDENTITY_HEADER,
    )
    selected_requests = requests or PostgresSupportRepository(resolved.database_url)

    # The webhook owns the local queue's dispatcher thread only when it built
    # the queue itself. A caller that passes one in owns its lifetime.
    runs_queue = owns_queue and isinstance(selected_queue, LocalTaskQueue)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runs_queue:
            selected_queue.start()  # pyright: ignore[reportAttributeAccessIssue]
        try:
            yield
        finally:
            if runs_queue:
                selected_queue.stop()  # pyright: ignore[reportAttributeAccessIssue]

    app = FastAPI(title="HR policy support webhook", lifespan=lifespan)

    @app.post(SLACK_EVENTS_PATH)
    async def slack_events(
        request: Request,
        slack_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
        slack_timestamp: str | None = Header(default=None, alias=TIMESTAMP_HEADER),
    ) -> Response:
        raw_body = await request.body()
        try:
            selected_verifier.verify(
                raw_body=raw_body,
                timestamp=slack_timestamp,
                signature=slack_signature,
            )
        except InvalidSlackSignatureError as error:
            raise HTTPException(status_code=401, detail="invalid slack signature") from error

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise HTTPException(status_code=400, detail="malformed payload") from error
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="malformed payload")

        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            if not isinstance(challenge, str):
                raise HTTPException(status_code=400, detail="malformed challenge")
            return Response(content=challenge, media_type="text/plain")

        try:
            incoming = normalize_app_mention(
                payload,
                allowed_team_ids=allowed_teams,
                allowed_channel_ids=allowed_channels,
            )
        except UnsupportedEvent as error:
            # 2xx on purpose: a retry cannot change this answer.
            logger.info("ignoring slack event: %s", error)
            return Response(status_code=200)

        try:
            accepted = accepter(
                incoming,
                requests=selected_requests,
                queue=selected_queue,
            )
        except RequestNotQueuedError as error:
            # The request is already stored. Slack retries, the same task name
            # is re-derived, and the retry converges instead of duplicating.
            logger.warning("request stored but not queued: %s", error)
            raise HTTPException(status_code=503, detail="queue unavailable") from error

        # Identifiers only. The question never reaches a log (INV-9).
        logger.info(
            "accepted request %s (new=%s, already_queued=%s)",
            accepted.request_id,
            accepted.created,
            accepted.already_queued,
        )
        return Response(status_code=200)

    return app


def normalize_app_mention(
    payload: dict[str, Any],
    *,
    allowed_team_ids: frozenset[str],
    allowed_channel_ids: frozenset[str],
) -> IncomingSupportRequest:
    """Turn a Slack event callback into the application's own input type.

    Raises `UnsupportedEvent` for anything this app does not act on, which the
    caller turns into a 2xx because a Slack retry would be pointless.

    Slack's wire shapes stop here. Nothing downstream knows what Slack is.
    """

    if payload.get("type") != "event_callback":
        raise UnsupportedEvent(f"unsupported payload type {payload.get('type')!r}")

    event_id = payload.get("event_id")
    team_id = payload.get("team_id")
    event = payload.get("event")
    if not isinstance(event, dict):
        raise UnsupportedEvent("missing event")
    if not isinstance(event_id, str) or not event_id:
        raise UnsupportedEvent("missing event_id")
    if not isinstance(team_id, str) or not team_id:
        raise UnsupportedEvent("missing team_id")

    if event.get("type") != "app_mention":
        raise UnsupportedEvent(f"unsupported event type {event.get('type')!r}")

    # A bot answering itself would loop. Drop it before anything else.
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        raise UnsupportedEvent("bot-authored event")

    channel_id = event.get("channel")
    user_id = event.get("user")
    message_ts = event.get("ts")
    text = event.get("text")
    if not _is_present(channel_id) or not _is_present(user_id) or not _is_present(message_ts):
        raise UnsupportedEvent("missing channel, user, or ts")
    if not isinstance(text, str):
        raise UnsupportedEvent("missing text")

    # A valid signature proves the request came from Slack, not that it came
    # from the workspace and channel this deployment serves. Fail closed.
    if team_id not in allowed_team_ids:
        raise UnsupportedEvent("team is not allowed")
    if channel_id not in allowed_channel_ids:
        raise UnsupportedEvent("channel is not allowed")

    question_text = strip_mentions(text)
    if not question_text:
        raise UnsupportedEvent("mention carried no question")

    # A mention inside an existing thread replies into that thread. A top-level
    # mention starts one, so its own timestamp becomes the thread root.
    thread_ts = event.get("thread_ts")
    if not _is_present(thread_ts):
        thread_ts = message_ts

    return IncomingSupportRequest(
        slack_event_id=event_id,
        slack_team_id=team_id,
        slack_channel_id=str(channel_id),
        slack_message_ts=str(message_ts),
        slack_thread_ts=str(thread_ts),
        slack_user_id=str(user_id),
        question_text=question_text[:MAX_QUESTION_LENGTH],
    )


def strip_mentions(text: str) -> str:
    """Remove Slack mentions and collapse the whitespace they leave behind."""

    return " ".join(MENTION_PATTERN.sub(" ", text).split())


def _is_present(value: object) -> bool:
    return isinstance(value, str) and bool(value)
