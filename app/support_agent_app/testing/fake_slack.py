"""A Slack client that records attempts instead of sending them.

Reaction and reply attempts are recorded in call order. Reply behaviour maps to
the failure modes the worker must handle differently: `clear-failure` means
Slack refused, `uncertain` means the worker cannot know whether the employee
already got a reply.
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


@dataclass(frozen=True)
class FakeSlackReaction:
    channel_id: str
    message_ts: str
    name: str
    timeout_seconds: float


class FakeSlackClient:
    """Deterministic local adapter that records attempts without network access."""

    def __init__(
        self,
        behavior: Literal["success", "clear-failure", "uncertain"] = "success",
        *,
        reaction_succeeds: bool = True,
    ) -> None:
        self.behavior = behavior
        self.reaction_succeeds = reaction_succeeds
        self.calls: list[str] = []
        self.reactions: list[FakeSlackReaction] = []
        self.attempts: list[FakeSlackAttempt] = []

    def add_reaction(
        self,
        *,
        channel_id: str,
        message_ts: str,
        name: str,
        timeout_seconds: float,
    ) -> bool:
        self.calls.append("reaction")
        self.reactions.append(
            FakeSlackReaction(
                channel_id=channel_id,
                message_ts=message_ts,
                name=name,
                timeout_seconds=timeout_seconds,
            )
        )
        return self.reaction_succeeds

    def post_thread_reply(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        text: str,
        timeout_seconds: float,
    ) -> str:
        self.calls.append("reply")
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
