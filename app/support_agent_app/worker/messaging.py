"""The real Slack adapter. Every httpx and Slack detail stops here.

Callers see only `post_thread_reply`, plus the two application-owned send
errors that tell them whether a retry is safe.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..application.failures import SlackSendError, SlackSendUncertainError

logger = logging.getLogger(__name__)

SLACK_API_BASE_URL = "https://slack.com/api"

RETRYABLE_SLACK_ERROR_CODES = frozenset(
    {
        "internal_error",
        "ratelimited",
        "service_unavailable",
    }
)


class RecordingSlackClient:
    """Accept a reply without sending it anywhere.

    For running the system without a Slack workspace. It is not a test double:
    the reply text is already durable in `outbound_actions` before any send is
    attempted, so the employee-visible text is in Postgres either way. This only
    decides whether the network is involved.

    It returns a synthetic message timestamp so the lifecycle completes exactly
    as it would after a real send.
    """

    def __init__(self) -> None:
        self.sent = 0

    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str:
        self.sent += 1
        # Length only. The complete message text never reaches a log (INV-9).
        logger.info(
            "recorded a %s character reply for channel %s thread %s instead of sending it",
            len(text),
            channel_id,
            thread_ts,
        )
        return f"recorded.{self.sent:06d}"


class SlackWebApiClient:
    """Configured real Slack adapter kept behind the same narrow interface."""

    def __init__(self, bot_token: str, *, client: httpx.Client | None = None) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        self._bot_token = bot_token
        self._client = client or httpx.Client(base_url=SLACK_API_BASE_URL)

    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str:
        try:
            response = self._client.post(
                "/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                content=json.dumps({"channel": channel_id, "thread_ts": thread_ts, "text": text}),
                timeout=timeout_seconds,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            raise SlackSendError("slack_connect_failed", retryable=True) from error
        except (
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.ReadError,
            httpx.WriteError,
            httpx.RemoteProtocolError,
            httpx.NetworkError,
        ) as error:
            raise SlackSendUncertainError() from error

        if response.status_code >= 500 or response.status_code == 429:
            raise SlackSendError("slack_temporarily_unavailable", retryable=True)
        if response.status_code >= 400:
            raise SlackSendError("slack_request_rejected", retryable=False)

        payload = response.json()
        if not payload.get("ok"):
            provider_code = payload.get("error")
            retryable = provider_code in RETRYABLE_SLACK_ERROR_CODES
            category = "slack_temporarily_unavailable" if retryable else "slack_request_rejected"
            raise SlackSendError(category, retryable=retryable)
        message_ts = payload.get("ts")
        if not isinstance(message_ts, str) or not message_ts:
            raise SlackSendUncertainError("slack_missing_message_timestamp")
        return message_ts
