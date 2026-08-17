"""The worker's time budget, split across the stages of one attempt.

Cloud Tasks gives the worker a bounded window. Every external call takes its
timeout from what is left of that window, and a reserve is held back so the
worker can always record what happened before the window closes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from time import monotonic

DEFAULT_LEASE_DURATION = timedelta(seconds=90)
DEFAULT_WORKER_DEADLINE_SECONDS = 55.0
MINIMUM_WORKFLOW_BUDGET_SECONDS = 21.0
FINALIZATION_RESERVE_SECONDS = 1.0
MAX_SLACK_TIMEOUT_SECONDS = 15.0


class WorkerDeadlineExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerDeadline:
    expires_at: float
    clock: Callable[[], float] = field(default=monotonic, repr=False, compare=False)

    @classmethod
    def after(
        cls,
        seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> WorkerDeadline:
        if seconds < 0:
            raise ValueError("deadline seconds cannot be negative")
        return cls(expires_at=clock() + seconds, clock=clock)

    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - self.clock())

    def require(self, stage: str, minimum_seconds: float = 0.0) -> None:
        if self.remaining_seconds() <= minimum_seconds:
            raise WorkerDeadlineExceeded(f"insufficient deadline budget before {stage}")

    def slack_timeout_seconds(self) -> float:
        available = self.remaining_seconds() - FINALIZATION_RESERVE_SECONDS
        if available <= 0:
            raise WorkerDeadlineExceeded("insufficient deadline budget before Slack send")
        return min(MAX_SLACK_TIMEOUT_SECONDS, available)

    def database_timeout_seconds(self) -> float:
        available = self.remaining_seconds() - FINALIZATION_RESERVE_SECONDS
        if available <= 0:
            raise WorkerDeadlineExceeded("insufficient deadline budget before database operation")
        return available

    def model_timeout_seconds(self) -> float:
        available = self.remaining_seconds() - FINALIZATION_RESERVE_SECONDS
        if available <= 0:
            raise WorkerDeadlineExceeded("insufficient deadline budget before model operation")
        return available

    def finalization_timeout_seconds(self) -> float:
        available = self.remaining_seconds()
        if available <= 0:
            raise WorkerDeadlineExceeded("worker deadline expired before finalization")
        return available
