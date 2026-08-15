"""Slack reply formatting and replaceable delivery adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from .domain import SupportDecision


HUMAN_REVIEW_REPLY = (
    "I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team."
)
OFF_TOPIC_REPLY = "I can only help with questions about company HR policies."


def format_slack_reply(decision: SupportDecision) -> str:
    """Format only a validated decision, never raw model output."""

    if decision.decision == "human_review":
        if decision.reason_code == "off_topic":
            return OFF_TOPIC_REPLY
        return HUMAN_REVIEW_REPLY

    source_lines = "\n".join(f"- {source.source_filename}" for source in decision.sources)
    return f"{decision.answer}\n\nSources\n{source_lines}"


class SlackSendError(RuntimeError):
    """A known send failure for which Slack did not accept the reply."""

    def __init__(self, category: str, *, retryable: bool) -> None:
        super().__init__(category)
        self.category = category
        self.retryable = retryable


class SlackSendUncertainError(RuntimeError):
    """A send began, but the caller cannot know whether Slack accepted it."""

    def __init__(self, category: str = "send_uncertain") -> None:
        super().__init__(category)
        self.category = category


class SlackClient(Protocol):
    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str: ...


@dataclass(frozen=True)
class FakeSlackAttempt:
    channel_id: str
    thread_ts: str
    text: str
    timeout_seconds: float


class FakeSlackClient:
    """Deterministic local adapter that records attempts without network access."""

    def __init__(
        self,
        behavior: Literal["success", "clear-failure", "uncertain"] = "success",
    ) -> None:
        self.behavior = behavior
        self.attempts: list[FakeSlackAttempt] = []

    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str:
        self.attempts.append(
            FakeSlackAttempt(
                channel_id=channel_id,
                thread_ts=thread_ts,
                text=text,
                timeout_seconds=timeout_seconds,
            )
        )
        if self.behavior == "clear-failure":
            raise SlackSendError("slack_temporarily_unavailable", retryable=True)
        if self.behavior == "uncertain":
            raise SlackSendUncertainError("send_timeout")
        return "900.001"


class SlackWebApiClient:
    """Configured real Slack adapter kept behind the same narrow interface."""

    def __init__(self, bot_token: str, *, client: httpx.Client | None = None) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        self._bot_token = bot_token
        self._client = client or httpx.Client(base_url="https://slack.com/api")

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
        except httpx.ConnectError as error:
            raise SlackSendError("slack_connect_failed", retryable=True) from error
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise SlackSendUncertainError() from error

        if response.status_code >= 500 or response.status_code == 429:
            raise SlackSendError("slack_temporarily_unavailable", retryable=True)
        if response.status_code >= 400:
            raise SlackSendError("slack_request_rejected", retryable=False)

        payload = response.json()
        if not payload.get("ok"):
            provider_code = payload.get("error")
            retryable = provider_code in {
                "internal_error",
                "ratelimited",
                "service_unavailable",
            }
            category = "slack_temporarily_unavailable" if retryable else "slack_request_rejected"
            raise SlackSendError(category, retryable=retryable)
        message_ts = payload.get("ts")
        if not isinstance(message_ts, str) or not message_ts:
            raise SlackSendUncertainError("slack_missing_message_timestamp")
        return message_ts
