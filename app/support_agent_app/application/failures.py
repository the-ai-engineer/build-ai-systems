"""Failure signals that cross a boundary.

These two live in the shared contract because an integration raises them and a
runtime catches them. Splitting a send failure three ways is the reason the
whole request lifecycle exists: refused is safe to retry, uncertain is not.
"""

from __future__ import annotations


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
