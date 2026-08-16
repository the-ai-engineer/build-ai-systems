"""A Slack client that records attempts instead of sending them.

Each behaviour maps to a failure mode the worker must handle differently:
`clear-failure` means Slack refused, `uncertain` means the worker cannot know
whether the employee already got a reply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..application.failures import SlackSendError, SlackSendUncertainError


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
