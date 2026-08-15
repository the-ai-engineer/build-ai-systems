"""Deadline-aware orchestration for one stored support request."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from time import monotonic
from typing import Callable
from uuid import UUID

from pydantic_ai.models import Model

from .domain import SupportDecision, SupportQuestion, WorkflowOutcome
from .repositories import PolicyRepository
from .request_repository import (
    Claim,
    LifecycleOutcome,
    PostgresSupportRepository,
    RequestNotFoundError,
    StaleClaimError,
)
from .slack_actions import (
    SlackClient,
    SlackSendError,
    SlackSendUncertainError,
    format_slack_reply,
)
from .workflow import run_support_workflow


DEFAULT_LEASE_DURATION = timedelta(seconds=90)
DEFAULT_WORKER_DEADLINE_SECONDS = 55.0
MINIMUM_WORKFLOW_BUDGET_SECONDS = 21.0
FINALIZATION_RESERVE_SECONDS = 1.0
MAX_SLACK_TIMEOUT_SECONDS = 15.0


class WorkerDeadlineExceeded(RuntimeError):
    pass


class WorkerTemporaryError(RuntimeError):
    """A safe retry signal that deliberately carries no request content."""


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


@dataclass(frozen=True)
class WorkerResult:
    request_id: UUID
    outcome: str
    send_attempted: bool = False


WorkflowRunner = Callable[..., WorkflowOutcome]


class WorkerService:
    """Coordinate durable state, the policy workflow, and one Slack action."""

    def __init__(
        self,
        *,
        requests: PostgresSupportRepository,
        policies: PolicyRepository,
        model: Model | str | None,
        slack: SlackClient,
        workflow_runner: WorkflowRunner = run_support_workflow,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
    ) -> None:
        self._requests = requests
        self._policies = policies
        self._model = model
        self._slack = slack
        self._workflow_runner = workflow_runner
        self._lease_duration = lease_duration

    def process(self, request_id: UUID, deadline: WorkerDeadline) -> WorkerResult:
        deadline.require("claim", FINALIZATION_RESERVE_SECONDS)
        try:
            claim_result = self._requests.claim_request(request_id, self._lease_duration)
        except RequestNotFoundError:
            raise
        except Exception as error:
            raise WorkerTemporaryError("request claim failed") from error

        if claim_result.outcome != LifecycleOutcome.CLAIMED:
            return WorkerResult(request_id=request_id, outcome=claim_result.outcome.value)

        claim = claim_result.claim
        assert claim is not None
        try:
            stored_request = self._requests.load_claimed_request(claim)

            failed_action = self._requests.find_failed_reply_action(claim)
            if failed_action is not None:
                action = self._requests.retry_failed_reply(claim, failed_action.action_id)
                return self._send_reply(
                    claim,
                    action.action_id,
                    stored_request.slack_channel_id,
                    stored_request.slack_thread_ts,
                    action.outbound_text,
                    deadline,
                )

            stranded_action = self._requests.find_stranded_reply_action(claim)
            if stranded_action is not None:
                outcome = self._requests.reconcile_stranded_reply(
                    claim,
                    stranded_action.action_id,
                    "expired_claim_action",
                )
                return WorkerResult(request_id=request_id, outcome=outcome.value)

            decision = self._requests.load_latest_decision(claim)
            if decision is None:
                decision = self._run_and_record_workflow(
                    claim,
                    stored_request.question_text,
                    deadline,
                )

            deadline.require("reply action", FINALIZATION_RESERVE_SECONDS)
            outbound_text = format_slack_reply(decision)
            action = self._requests.create_reply_action(claim, outbound_text)
            return self._send_reply(
                claim,
                action.action_id,
                stored_request.slack_channel_id,
                stored_request.slack_thread_ts,
                action.outbound_text,
                deadline,
            )
        except WorkerDeadlineExceeded:
            return self._record_pre_send_failure(claim, "worker_deadline")
        except StaleClaimError:
            return WorkerResult(request_id=request_id, outcome=LifecycleOutcome.RETRYABLE.value)
        except WorkerTemporaryError:
            raise
        except Exception:
            try:
                return self._record_pre_send_failure(claim, "worker_temporary_failure")
            except Exception as record_error:
                raise WorkerTemporaryError("worker state update failed") from record_error

    def _run_and_record_workflow(
        self,
        claim: Claim,
        question_text: str,
        deadline: WorkerDeadline,
    ) -> SupportDecision:
        deadline.require("policy workflow", MINIMUM_WORKFLOW_BUDGET_SECONDS)
        try:
            outcome = self._workflow_runner(
                SupportQuestion(text=question_text),
                self._policies,
                model=self._model,
            )
        except Exception:
            self._record_pre_send_failure(claim, "model_temporary_failure")
            raise WorkerTemporaryError("policy workflow failed") from None

        deadline.require("workflow result", FINALIZATION_RESERVE_SECONDS)
        try:
            self._requests.record_workflow_result(claim, outcome)
        except StaleClaimError:
            raise
        except Exception as error:
            raise WorkerTemporaryError("workflow result persistence failed") from error
        return outcome.result

    def _send_reply(
        self,
        claim: Claim,
        action_id: UUID,
        channel_id: str,
        thread_ts: str,
        outbound_text: str,
        deadline: WorkerDeadline,
    ) -> WorkerResult:
        try:
            timeout_seconds = deadline.slack_timeout_seconds()
        except WorkerDeadlineExceeded:
            outcome = self._requests.mark_unsent_action_failed(
                claim,
                action_id,
                "worker_deadline",
                retryable=True,
            )
            return WorkerResult(request_id=claim.request_id, outcome=outcome.value)

        try:
            self._requests.mark_action_sending(claim, action_id)
        except StaleClaimError:
            raise
        except Exception:
            try:
                outcome = self._requests.mark_unsent_action_failed(
                    claim,
                    action_id,
                    "database_pre_send_failure",
                    retryable=True,
                )
            except Exception as failure_error:
                raise WorkerTemporaryError("pre-send state update failed") from failure_error
            return WorkerResult(request_id=claim.request_id, outcome=outcome.value)
        try:
            slack_message_ts = self._slack.post_thread_reply(
                channel_id=channel_id,
                thread_ts=thread_ts,
                text=outbound_text,
                timeout_seconds=timeout_seconds,
            )
        except SlackSendError as error:
            outcome = self._requests.mark_action_failed(
                claim,
                action_id,
                error.category,
                retryable=error.retryable,
            )
            return WorkerResult(
                request_id=claim.request_id,
                outcome=outcome.value,
                send_attempted=True,
            )
        except SlackSendUncertainError as error:
            outcome = self._requests.mark_action_uncertain(claim, action_id, error.category)
            return WorkerResult(
                request_id=claim.request_id,
                outcome=outcome.value,
                send_attempted=True,
            )
        except Exception:
            outcome = self._requests.mark_action_uncertain(
                claim,
                action_id,
                "send_uncertain",
            )
            return WorkerResult(
                request_id=claim.request_id,
                outcome=outcome.value,
                send_attempted=True,
            )

        try:
            self._requests.complete_reply(claim, action_id, slack_message_ts)
        except Exception:
            try:
                outcome = self._requests.mark_action_uncertain(
                    claim,
                    action_id,
                    "send_result_not_recorded",
                )
            except Exception as reconciliation_error:
                raise WorkerTemporaryError("Slack result persistence failed") from (
                    reconciliation_error
                )
            return WorkerResult(
                request_id=claim.request_id,
                outcome=outcome.value,
                send_attempted=True,
            )
        return WorkerResult(
            request_id=claim.request_id,
            outcome="completed",
            send_attempted=True,
        )

    def _record_pre_send_failure(self, claim: Claim, category: str) -> WorkerResult:
        outcome = self._requests.record_failure(claim, category, retryable=True)
        return WorkerResult(request_id=claim.request_id, outcome=outcome.value)
