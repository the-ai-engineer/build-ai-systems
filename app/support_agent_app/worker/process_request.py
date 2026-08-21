"""The use case: process one stored support request, exactly once, in time.

This is the heart of the system and it names no provider. It talks to a request
store, a policy repository, an agent runner, and a Slack client, all of which
are protocols in `protocols.py`. `worker/main.py` supplies the real ones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from ..application.domain import SupportDecision, SupportQuestion
from ..application.failures import SlackSendError, SlackSendUncertainError
from ..application.lifecycle import (
    Claim,
    LifecycleOutcome,
    RequestNotFoundError,
    StaleClaimError,
)
from ..application.protocols import (
    AgentRunner,
    PolicyRepository,
    SlackClient,
    SupportRequestStore,
    TimeoutAwarePolicyRepository,
)
from .deadlines import (
    DEFAULT_LEASE_DURATION,
    FINALIZATION_RESERVE_SECONDS,
    MINIMUM_WORKFLOW_BUDGET_SECONDS,
    WorkerDeadline,
    WorkerDeadlineExceeded,
)
from .failures import WorkerTemporaryError, classify_workflow_failure

HUMAN_REVIEW_REPLY = (
    "I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team."
)
OFF_TOPIC_REPLY = "I can only help with questions about company HR policies."
REQUEST_ACKNOWLEDGEMENT_REACTION = "eyes"
MAX_ACKNOWLEDGEMENT_TIMEOUT_SECONDS = 2.0

logger = logging.getLogger(__name__)


def format_slack_reply(decision: SupportDecision) -> str:
    """Format only a validated decision, never raw model output."""

    if decision.decision == "human_review":
        if decision.reason_code == "off_topic":
            return OFF_TOPIC_REPLY
        return HUMAN_REVIEW_REPLY

    source_lines = "\n".join(f"- {source.source_filename}" for source in decision.sources)
    return f"{decision.answer}\n\nSources\n{source_lines}"


@dataclass(frozen=True)
class WorkerResult:
    request_id: UUID
    outcome: str
    send_attempted: bool = False


class WorkerPermanentFailure(RuntimeError):
    def __init__(self, result: WorkerResult) -> None:
        super().__init__(result.outcome)
        self.result = result


class WorkerService:
    """Coordinate durable state, the policy workflow, and one Slack action."""

    def __init__(
        self,
        *,
        requests: SupportRequestStore,
        policies: PolicyRepository,
        model: object | None,
        slack: SlackClient,
        workflow_runner: AgentRunner,
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
            claim_result = self._requests.claim_request(
                request_id,
                self._lease_duration,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
        except RequestNotFoundError:
            raise
        except Exception as error:
            raise WorkerTemporaryError("request claim failed") from error

        if claim_result.outcome != LifecycleOutcome.CLAIMED:
            return WorkerResult(request_id=request_id, outcome=claim_result.outcome.value)

        claim = claim_result.claim
        assert claim is not None
        try:
            stored_request = self._requests.load_claimed_request(
                claim,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
            self._acknowledge_request(
                channel_id=stored_request.slack_channel_id,
                message_ts=stored_request.slack_message_ts,
                deadline=deadline,
            )

            failed_action = self._requests.find_failed_reply_action(
                claim,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
            if failed_action is not None:
                action = self._requests.retry_failed_reply(
                    claim,
                    failed_action.action_id,
                    timeout_seconds=deadline.database_timeout_seconds(),
                )
                return self._send_reply(
                    claim,
                    action.action_id,
                    stored_request.slack_channel_id,
                    stored_request.slack_thread_ts,
                    action.outbound_text,
                    deadline,
                )

            stranded_action = self._requests.find_stranded_reply_action(
                claim,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
            if stranded_action is not None:
                outcome = self._requests.reconcile_stranded_reply(
                    claim,
                    stranded_action.action_id,
                    "expired_claim_action",
                    timeout_seconds=deadline.database_timeout_seconds(),
                )
                return WorkerResult(request_id=request_id, outcome=outcome.value)

            decision = self._requests.load_latest_decision(
                claim,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
            if decision is None:
                decision = self._run_and_record_workflow(
                    claim,
                    stored_request.question_text,
                    deadline,
                )

            deadline.require("reply action", FINALIZATION_RESERVE_SECONDS)
            outbound_text = format_slack_reply(decision)
            action = self._requests.create_reply_action(
                claim,
                outbound_text,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
            return self._send_reply(
                claim,
                action.action_id,
                stored_request.slack_channel_id,
                stored_request.slack_thread_ts,
                action.outbound_text,
                deadline,
            )
        except WorkerDeadlineExceeded:
            return self._record_pre_send_failure(claim, "worker_deadline", deadline)
        except StaleClaimError:
            return WorkerResult(request_id=request_id, outcome=LifecycleOutcome.RETRYABLE.value)
        except WorkerTemporaryError:
            raise
        except WorkerPermanentFailure as error:
            return error.result
        except Exception:
            try:
                return self._record_pre_send_failure(
                    claim,
                    "worker_temporary_failure",
                    deadline,
                )
            except Exception as record_error:
                raise WorkerTemporaryError("worker state update failed") from record_error

    def _acknowledge_request(
        self,
        *,
        channel_id: str,
        message_ts: str,
        deadline: WorkerDeadline,
    ) -> None:
        """Best-effort progress signal before the model starts.

        Slack keeps one reaction per bot, message, and emoji. A retried worker
        may call this again, but `already_reacted` is success and the employee
        still sees one reaction. Failure is deliberately non-fatal because the
        accepted request and final reply matter more than this progress signal.
        """

        available = (
            deadline.remaining_seconds()
            - MINIMUM_WORKFLOW_BUDGET_SECONDS
            - FINALIZATION_RESERVE_SECONDS
        )
        if available <= 0:
            return
        timeout_seconds = min(MAX_ACKNOWLEDGEMENT_TIMEOUT_SECONDS, available)
        try:
            acknowledged = self._slack.add_reaction(
                channel_id=channel_id,
                message_ts=message_ts,
                name=REQUEST_ACKNOWLEDGEMENT_REACTION,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            logger.warning("request acknowledgement reaction failed unexpectedly")
            return
        if not acknowledged:
            logger.warning("request acknowledgement reaction was not accepted")

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
                self._deadline_policies(deadline),
                model=self._model,
                model_timeout_seconds=deadline.model_timeout_seconds(),
            )
        except Exception as error:
            category, retryable = classify_workflow_failure(error)
            result = self._record_pre_send_failure(
                claim,
                category,
                deadline,
                retryable=retryable,
            )
            if retryable:
                raise WorkerTemporaryError("policy workflow failed") from None
            raise WorkerPermanentFailure(result) from None

        deadline.require("workflow result", FINALIZATION_RESERVE_SECONDS)
        try:
            self._requests.record_workflow_result(
                claim,
                outcome,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
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
        """Attempt the one outbound action, and record which of three ways it went.

        A send has three outcomes, not two, and that is the reason this whole
        lifecycle exists:

        - refused, so a retry is safe
        - uncertain, so a retry might reply to the employee twice
        - succeeded

        Anything before the send is "not sent", which is always safe to retry.
        Anything after it is "we tried", which is not.
        """

        # Not sent yet: no budget left, or the database would not let us start.
        try:
            deadline.slack_timeout_seconds()
        except WorkerDeadlineExceeded:
            return self._unsent(claim, action_id, "worker_deadline", deadline)

        try:
            self._requests.mark_action_sending(
                claim,
                action_id,
                timeout_seconds=deadline.database_timeout_seconds(),
            )
        except StaleClaimError:
            raise
        except Exception:
            return self._unsent(claim, action_id, "database_pre_send_failure", deadline)

        # Re-check. Marking the action as sending is a database write, and it
        # can consume the remaining budget. Calling Slack with what is left of a
        # spent budget is how a send becomes uncertain for no reason.
        try:
            timeout_seconds = deadline.slack_timeout_seconds()
        except WorkerDeadlineExceeded:
            return self._unsent(claim, action_id, "worker_deadline", deadline)

        # The send itself. From here on, the employee may already have a reply.
        try:
            slack_message_ts = self._slack.post_thread_reply(
                channel_id=channel_id,
                thread_ts=thread_ts,
                text=outbound_text,
                timeout_seconds=timeout_seconds,
            )
        except SlackSendError as error:
            # Refused. Slack did not accept it, so a retry is safe.
            outcome = self._requests.mark_action_failed(
                claim,
                action_id,
                error.category,
                retryable=error.retryable,
                timeout_seconds=deadline.finalization_timeout_seconds(),
            )
            return self._attempted(claim, outcome)
        except SlackSendUncertainError as error:
            return self._attempted(
                claim, self._uncertain(claim, action_id, error.category, deadline)
            )
        except Exception:
            # An unexpected error after the send began is still uncertain.
            return self._attempted(
                claim, self._uncertain(claim, action_id, "send_uncertain", deadline)
            )

        # Sent. If we cannot record that, the reply exists but our record does
        # not, which is uncertain rather than successful.
        try:
            self._requests.complete_reply(
                claim,
                action_id,
                slack_message_ts,
                timeout_seconds=deadline.finalization_timeout_seconds(),
            )
        except Exception:
            outcome = self._uncertain(claim, action_id, "send_result_not_recorded", deadline)
            return self._attempted(claim, outcome)
        return WorkerResult(
            request_id=claim.request_id,
            outcome="completed",
            send_attempted=True,
        )

    def _unsent(
        self,
        claim: Claim,
        action_id: UUID,
        category: str,
        deadline: WorkerDeadline,
    ) -> WorkerResult:
        """Record a failure that happened before anything reached Slack."""

        try:
            outcome = self._requests.mark_unsent_action_failed(
                claim,
                action_id,
                category,
                retryable=True,
                timeout_seconds=deadline.finalization_timeout_seconds(),
            )
        except Exception as error:
            raise WorkerTemporaryError("pre-send state update failed") from error
        return WorkerResult(request_id=claim.request_id, outcome=outcome.value)

    def _uncertain(
        self,
        claim: Claim,
        action_id: UUID,
        category: str,
        deadline: WorkerDeadline,
    ) -> LifecycleOutcome:
        """Record that we cannot know whether the employee received the reply."""

        try:
            return self._requests.mark_action_uncertain(
                claim,
                action_id,
                category,
                timeout_seconds=deadline.finalization_timeout_seconds(),
            )
        except Exception as error:
            raise WorkerTemporaryError("Slack result persistence failed") from error

    @staticmethod
    def _attempted(claim: Claim, outcome: LifecycleOutcome) -> WorkerResult:
        return WorkerResult(
            request_id=claim.request_id,
            outcome=outcome.value,
            send_attempted=True,
        )

    def _record_pre_send_failure(
        self,
        claim: Claim,
        category: str,
        deadline: WorkerDeadline | None = None,
        *,
        retryable: bool = True,
    ) -> WorkerResult:
        timeout_seconds = None
        if deadline is not None:
            timeout_seconds = deadline.finalization_timeout_seconds()
        outcome = self._requests.record_failure(
            claim,
            category,
            retryable=retryable,
            timeout_seconds=timeout_seconds,
        )
        return WorkerResult(request_id=claim.request_id, outcome=outcome.value)

    def _deadline_policies(self, deadline: WorkerDeadline) -> PolicyRepository:
        """Give the policy reads whatever is left of the attempt's budget.

        An in-memory repository has nothing to time out, so it is used as-is.
        """
        if isinstance(self._policies, TimeoutAwarePolicyRepository):
            return self._policies.with_timeout_provider(deadline.database_timeout_seconds)
        return self._policies
