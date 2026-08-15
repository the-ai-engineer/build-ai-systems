"""Durable support-request lifecycle with Postgres claim fencing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .domain import (
    AnswerDecision,
    HumanReviewDecision,
    SourceCitation,
    SupportDecision,
    WorkflowOutcome,
)

MAX_BUSINESS_ATTEMPTS = 5


class LifecycleOutcome(StrEnum):
    CLAIMED = "claimed"
    DUPLICATE_COMPLETE = "duplicate-complete"
    ACTIVE_LEASE = "active-lease"
    RETRYABLE = "retryable"
    PERMANENT_FAILURE = "permanent-failure"
    RECONCILIATION = "reconciliation"


class RequestLifecycleError(RuntimeError):
    """Base class for invalid lifecycle operations."""


class RequestNotFoundError(RequestLifecycleError):
    pass


class StaleClaimError(RequestLifecycleError):
    pass


class StateConflictError(RequestLifecycleError):
    pass


class ActionConflictError(RequestLifecycleError):
    pass


@dataclass(frozen=True)
class IncomingSupportRequest:
    slack_event_id: str
    slack_team_id: str
    slack_channel_id: str
    slack_message_ts: str
    slack_thread_ts: str
    slack_user_id: str
    question_text: str


@dataclass(frozen=True)
class AcceptedRequest:
    request_id: UUID
    created: bool


@dataclass(frozen=True)
class Claim:
    request_id: UUID
    claim_token: UUID
    lease_version: int
    business_attempt_number: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class ClaimResult:
    outcome: LifecycleOutcome
    claim: Claim | None = None


@dataclass(frozen=True)
class ClaimedRequest:
    request_id: UUID
    slack_channel_id: str
    slack_thread_ts: str
    question_text: str = field(repr=False)


@dataclass(frozen=True)
class OutboundAction:
    action_id: UUID
    request_id: UUID
    action_generation: int
    status: str
    outbound_text: str
    content_hash: str


class PostgresSupportRepository:
    """A small transactional API for accepted work and worker-owned changes."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def _connect(self):
        from psycopg import connect

        return connect(self._database_url, row_factory=dict_row)

    def accept_request(self, incoming: IncomingSupportRequest) -> AcceptedRequest:
        """Store an event once without returning its sensitive question text."""

        request_id = uuid4()
        with self._connect() as connection:
            row = connection.execute(
                """
                insert into support_requests (
                    request_id, slack_event_id, slack_team_id, slack_channel_id,
                    slack_message_ts, slack_thread_ts, slack_user_id, question_text,
                    content_expires_at, status
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, now() + interval '30 days', 'accepted')
                on conflict (slack_event_id) do nothing
                returning request_id
                """,
                (
                    request_id,
                    incoming.slack_event_id,
                    incoming.slack_team_id,
                    incoming.slack_channel_id,
                    incoming.slack_message_ts,
                    incoming.slack_thread_ts,
                    incoming.slack_user_id,
                    incoming.question_text,
                ),
            ).fetchone()
            if row is not None:
                return AcceptedRequest(request_id=row["request_id"], created=True)
            existing = connection.execute(
                "select request_id from support_requests where slack_event_id = %s",
                (incoming.slack_event_id,),
            ).fetchone()
            assert existing is not None
            return AcceptedRequest(request_id=existing["request_id"], created=False)

    def mark_queued(self, request_id: UUID) -> None:
        """Make accepted work ready for a future internal delivery adapter."""

        with self._connect() as connection:
            row = connection.execute(
                """
                update support_requests
                set status = 'queued', queued_at = coalesce(queued_at, now())
                where request_id = %s and status in ('accepted', 'queued')
                returning request_id
                """,
                (request_id,),
            ).fetchone()
            if row is not None:
                return
            self._raise_request_state(connection, request_id, "cannot queue request")

    def claim_request(self, request_id: UUID, lease_duration: timedelta) -> ClaimResult:
        """Atomically obtain the next lease version or return an explicit no-work outcome."""

        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")

        with self._connect() as connection:
            request = connection.execute(
                """
                select request_id, status, task_generation, business_attempt_count
                from support_requests
                where request_id = %s
                for update
                """,
                (request_id,),
            ).fetchone()
            if request is None:
                raise RequestNotFoundError(str(request_id))

            status = request["status"]
            if status == "completed":
                return ClaimResult(LifecycleOutcome.DUPLICATE_COMPLETE)
            if status == "reconciliation":
                return ClaimResult(LifecycleOutcome.RECONCILIATION)
            if status == "failed":
                return ClaimResult(LifecycleOutcome.PERMANENT_FAILURE)

            current = connection.execute(
                """
                select claim_token, lease_version, lease_expires_at, released_at
                from support_request_claims
                where request_id = %s
                order by lease_version desc
                limit 1
                """,
                (request_id,),
            ).fetchone()
            if (
                current is not None
                and current["released_at"] is None
                and current["lease_expires_at"] > self._database_now(connection)
            ):
                return ClaimResult(LifecycleOutcome.ACTIVE_LEASE)

            attempt_number = request["business_attempt_count"] + 1
            if attempt_number > MAX_BUSINESS_ATTEMPTS:
                connection.execute(
                    """
                    update support_requests
                    set status = 'failed', failed_at = coalesce(failed_at, now()),
                        last_error_category = 'attempts_exhausted'
                    where request_id = %s
                    """,
                    (request_id,),
                )
                return ClaimResult(LifecycleOutcome.PERMANENT_FAILURE)

            lease_version = 1 if current is None else current["lease_version"] + 1
            claim_token = uuid4()
            attempt_id = uuid4()
            lease_seconds = lease_duration.total_seconds()
            claim_row = connection.execute(
                """
                insert into support_request_claims (
                    request_id, claim_token, lease_version, lease_expires_at,
                    business_attempt_number
                )
                values (%s, %s, %s, now() + make_interval(secs => %s), %s)
                returning lease_expires_at
                """,
                (request_id, claim_token, lease_version, lease_seconds, attempt_number),
            ).fetchone()
            connection.execute(
                """
                insert into support_attempts (
                    attempt_id, request_id, task_generation, claim_token,
                    attempt_kind, outcome
                )
                values (%s, %s, %s, %s, 'workflow', 'processing')
                """,
                (attempt_id, request_id, request["task_generation"], claim_token),
            )
            connection.execute(
                """
                update support_requests
                set status = 'processing', business_attempt_count = %s,
                    processing_at = coalesce(processing_at, now()),
                    last_error_category = null
                where request_id = %s
                """,
                (attempt_number, request_id),
            )
            return ClaimResult(
                LifecycleOutcome.CLAIMED,
                Claim(
                    request_id=request_id,
                    claim_token=claim_token,
                    lease_version=lease_version,
                    business_attempt_number=attempt_number,
                    lease_expires_at=claim_row["lease_expires_at"],
                ),
            )

    def load_claimed_request(self, claim: Claim) -> ClaimedRequest:
        """Load sensitive worker input only while the supplied claim is current."""

        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            row = connection.execute(
                """
                select request_id, slack_channel_id, slack_thread_ts, question_text
                from support_requests
                where request_id = %s
                """,
                (claim.request_id,),
            ).fetchone()
            assert row is not None
            return ClaimedRequest(
                request_id=row["request_id"],
                slack_channel_id=row["slack_channel_id"],
                slack_thread_ts=row["slack_thread_ts"],
                question_text=row["question_text"],
            )

    def load_latest_decision(self, claim: Claim) -> SupportDecision | None:
        """Resume a verified result without repeating a completed model call."""

        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            row = connection.execute(
                """
                select decision, reason_code, answer, reason, sources
                from support_decisions
                where request_id = %s
                order by created_at desc, decision_id desc
                limit 1
                """,
                (claim.request_id,),
            ).fetchone()
            if row is None:
                return None
            if row["decision"] == "answer":
                return AnswerDecision(
                    answer=row["answer"],
                    reason=row["reason"],
                    sources=tuple(
                        SourceCitation.model_validate(source) for source in row["sources"]
                    ),
                )
            return HumanReviewDecision(
                reason=row["reason"],
                reason_code=row["reason_code"],
            )

    def find_failed_reply_action(self, claim: Claim) -> OutboundAction | None:
        """Return a known failed action whose exact text can be retried safely."""

        return self._find_reply_action(claim, ("failed",))

    def find_stranded_reply_action(self, claim: Claim) -> OutboundAction | None:
        """Return an old pending or sending action that must not be resent."""

        return self._find_reply_action(claim, ("pending", "sending"))

    def record_workflow_result(self, claim: Claim, outcome: WorkflowOutcome) -> UUID:
        """Persist decision, run metadata, and source revisions under one current fence."""

        agent_run_id = uuid4()
        decision_id = uuid4()
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            run = outcome.run
            connection.execute(
                """
                insert into agent_runs (
                    agent_run_id, request_id, claim_token, model_id, model_location,
                    service_tier, input_tokens, output_tokens, duration_ms, finish_reason,
                    retrieved_context_tokens, tool_call_count, model_turn_count
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    agent_run_id,
                    claim.request_id,
                    claim.claim_token,
                    run.model_id,
                    run.model_location,
                    run.service_tier,
                    run.input_tokens,
                    run.output_tokens,
                    run.duration_ms,
                    run.finish_reason,
                    run.retrieved_context_tokens,
                    run.tool_call_count,
                    run.model_turn_count,
                ),
            )
            for source in run.selected_documents:
                connection.execute(
                    """
                    insert into agent_run_sources (agent_run_id, document_id, document_revision)
                    values (%s, %s, %s)
                    """,
                    (agent_run_id, source.document_id, source.revision),
                )
            result = outcome.result
            sources = [source.model_dump(mode="json") for source in result.sources]
            connection.execute(
                """
                insert into support_decisions (
                    decision_id, request_id, claim_token, decision, reason_code,
                    answer, reason, sources
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision_id,
                    claim.request_id,
                    claim.claim_token,
                    result.decision,
                    getattr(result, "reason_code", None),
                    result.answer,
                    result.reason,
                    Jsonb(sources),
                ),
            )
        return agent_run_id

    def create_reply_action(
        self,
        claim: Claim,
        outbound_text: str,
        *,
        action_generation: int = 1,
    ) -> OutboundAction:
        """Persist exact send content and its hash in the action-creation transaction."""

        if not outbound_text:
            raise ValueError("outbound_text is required")
        if action_generation < 1:
            raise ValueError("action_generation must be positive")
        content_hash = f"sha256:{hashlib.sha256(outbound_text.encode('utf-8')).hexdigest()}"
        action_id = uuid4()

        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            row = connection.execute(
                """
                insert into outbound_actions (
                    action_id, request_id, action_generation, claim_token, action_type,
                    status, outbound_text, content_hash
                )
                values (%s, %s, %s, %s, 'reply', 'pending', %s, %s)
                on conflict do nothing
                returning action_id, request_id, action_generation, status,
                          outbound_text, content_hash
                """,
                (
                    action_id,
                    claim.request_id,
                    action_generation,
                    claim.claim_token,
                    outbound_text,
                    content_hash,
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    select action_id, request_id, action_generation, status,
                           outbound_text, content_hash
                    from outbound_actions
                    where request_id = %s and action_type = 'reply' and status <> 'cancelled'
                    """,
                    (claim.request_id,),
                ).fetchone()
                assert row is not None
                if (
                    row["action_generation"] != action_generation
                    or row["content_hash"] != content_hash
                    or row["outbound_text"] != outbound_text
                ):
                    raise ActionConflictError(
                        "a different non-cancelled reply already exists for this request"
                    )
            return self._action_from_row(row)

    def mark_action_sending(self, claim: Claim, action_id: UUID) -> None:
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            row = connection.execute(
                """
                update outbound_actions
                set status = 'sending', started_at = coalesce(started_at, now())
                where action_id = %s and request_id = %s and claim_token = %s
                  and status = 'pending'
                returning action_id
                """,
                (action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if row is None:
                raise StateConflictError("reply action is not pending under this claim")

    def complete_reply(self, claim: Claim, action_id: UUID, slack_message_ts: str) -> None:
        """Record known success and complete the request in one fenced transaction."""

        if not slack_message_ts:
            raise ValueError("slack_message_ts is required")
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            action = connection.execute(
                """
                update outbound_actions
                set status = 'succeeded', slack_message_ts = %s, completed_at = now()
                where action_id = %s and request_id = %s and claim_token = %s
                  and status = 'sending'
                returning action_id
                """,
                (slack_message_ts, action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if action is None:
                raise StateConflictError("reply action is not sending under this claim")
            self._finish_attempt(connection, claim, "completed")
            connection.execute(
                """
                update support_requests
                set status = 'completed', completed_at = now()
                where request_id = %s
                """,
                (claim.request_id,),
            )

    def record_failure(
        self,
        claim: Claim,
        error_category: str,
        *,
        retryable: bool,
    ) -> LifecycleOutcome:
        """Release retryable work or record an explicit permanent failure."""

        if not error_category:
            raise ValueError("error_category is required")
        outcome = LifecycleOutcome.RETRYABLE if retryable else LifecycleOutcome.PERMANENT_FAILURE
        request_status = "queued" if retryable else "failed"
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            self._finish_attempt(connection, claim, outcome.value.replace("-", "_"))
            connection.execute(
                """
                update support_requests
                set status = %s, last_error_category = %s,
                    queued_at = case when %s = 'queued' then now() else queued_at end,
                    failed_at = case when %s = 'failed' then now() else failed_at end
                where request_id = %s
                """,
                (
                    request_status,
                    error_category,
                    request_status,
                    request_status,
                    claim.request_id,
                ),
            )
        return outcome

    def mark_action_failed(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        retryable: bool,
    ) -> LifecycleOutcome:
        """Record a known failed send, then release or permanently fail the request."""

        if not error_category:
            raise ValueError("error_category is required")
        outcome = LifecycleOutcome.RETRYABLE if retryable else LifecycleOutcome.PERMANENT_FAILURE
        request_status = "queued" if retryable else "failed"
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            action = connection.execute(
                """
                update outbound_actions
                set status = 'failed', last_error_category = %s, completed_at = now()
                where action_id = %s and request_id = %s and claim_token = %s
                  and status = 'sending'
                returning action_id
                """,
                (error_category, action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if action is None:
                raise StateConflictError("reply action is not sending under this claim")
            self._finish_attempt(connection, claim, outcome.value.replace("-", "_"))
            connection.execute(
                """
                update support_requests
                set status = %s, last_error_category = %s,
                    queued_at = case when %s = 'queued' then now() else queued_at end,
                    failed_at = case when %s = 'failed' then now() else failed_at end
                where request_id = %s
                """,
                (
                    request_status,
                    error_category,
                    request_status,
                    request_status,
                    claim.request_id,
                ),
            )
        return outcome

    def mark_unsent_action_failed(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
        *,
        retryable: bool,
    ) -> LifecycleOutcome:
        """Record a clear failure when the external send was never called."""

        if not error_category:
            raise ValueError("error_category is required")
        outcome = LifecycleOutcome.RETRYABLE if retryable else LifecycleOutcome.PERMANENT_FAILURE
        request_status = "queued" if retryable else "failed"
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            action = connection.execute(
                """
                update outbound_actions
                set status = 'failed', last_error_category = %s, completed_at = now()
                where action_id = %s and request_id = %s and claim_token = %s
                  and status in ('pending', 'sending')
                returning action_id
                """,
                (error_category, action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if action is None:
                raise StateConflictError("reply action was not unsent under this claim")
            self._finish_attempt(connection, claim, outcome.value.replace("-", "_"))
            connection.execute(
                """
                update support_requests
                set status = %s, last_error_category = %s,
                    queued_at = case when %s = 'queued' then now() else queued_at end,
                    failed_at = case when %s = 'failed' then now() else failed_at end
                where request_id = %s
                """,
                (
                    request_status,
                    error_category,
                    request_status,
                    request_status,
                    claim.request_id,
                ),
            )
        return outcome

    def retry_failed_reply(self, claim: Claim, failed_action_id: UUID) -> OutboundAction:
        """Replace one known-failed reply with the next controlled action generation."""

        next_action_id = uuid4()
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            failed = connection.execute(
                """
                select action_generation, outbound_text, content_hash
                from outbound_actions
                where action_id = %s and request_id = %s and action_type = 'reply'
                  and status = 'failed'
                for update
                """,
                (failed_action_id, claim.request_id),
            ).fetchone()
            if failed is None:
                raise StateConflictError("reply action is not a known failed send")
            connection.execute(
                """
                update outbound_actions
                set status = 'cancelled'
                where action_id = %s
                """,
                (failed_action_id,),
            )
            row = connection.execute(
                """
                insert into outbound_actions (
                    action_id, request_id, action_generation, claim_token, action_type,
                    status, outbound_text, content_hash
                )
                values (%s, %s, %s, %s, 'reply', 'pending', %s, %s)
                returning action_id, request_id, action_generation, status,
                          outbound_text, content_hash
                """,
                (
                    next_action_id,
                    claim.request_id,
                    failed["action_generation"] + 1,
                    claim.claim_token,
                    failed["outbound_text"],
                    failed["content_hash"],
                ),
            ).fetchone()
            return self._action_from_row(row)

    def mark_action_uncertain(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
    ) -> LifecycleOutcome:
        """Stop automatic retries after an ambiguous send outcome."""

        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            action = connection.execute(
                """
                update outbound_actions
                set status = 'uncertain', last_error_category = %s, completed_at = now()
                where action_id = %s and request_id = %s and claim_token = %s
                  and status = 'sending'
                returning action_id
                """,
                (error_category, action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if action is None:
                raise StateConflictError("reply action is not sending under this claim")
            self._finish_attempt(connection, claim, "reconciliation")
            connection.execute(
                """
                update support_requests
                set status = 'reconciliation', last_error_category = %s
                where request_id = %s
                """,
                (error_category, claim.request_id),
            )
        return LifecycleOutcome.RECONCILIATION

    def reconcile_stranded_reply(
        self,
        claim: Claim,
        action_id: UUID,
        error_category: str,
    ) -> LifecycleOutcome:
        """Fence a stranded old action and stop automatic delivery."""

        if not error_category:
            raise ValueError("error_category is required")
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            action = connection.execute(
                """
                update outbound_actions
                set status = 'uncertain', last_error_category = %s, completed_at = now()
                where action_id = %s and request_id = %s
                  and claim_token <> %s and status in ('pending', 'sending')
                returning action_id
                """,
                (error_category, action_id, claim.request_id, claim.claim_token),
            ).fetchone()
            if action is None:
                raise StateConflictError("reply action is not stranded under an expired claim")
            self._finish_attempt(connection, claim, "reconciliation")
            connection.execute(
                """
                update support_requests
                set status = 'reconciliation', last_error_category = %s
                where request_id = %s
                """,
                (error_category, claim.request_id),
            )
        return LifecycleOutcome.RECONCILIATION

    def _find_reply_action(
        self,
        claim: Claim,
        statuses: tuple[str, ...],
    ) -> OutboundAction | None:
        with self._connect() as connection:
            self._lock_current_claim(connection, claim)
            row = connection.execute(
                """
                select action_id, request_id, action_generation, status,
                       outbound_text, content_hash
                from outbound_actions
                where request_id = %s and action_type = 'reply'
                  and status = any(%s)
                order by action_generation desc, created_at desc
                limit 1
                """,
                (claim.request_id, list(statuses)),
            ).fetchone()
            return None if row is None else self._action_from_row(row)

    def _lock_current_claim(self, connection, claim: Claim) -> None:
        row = connection.execute(
            """
            select r.status, c.claim_token, c.lease_version,
                   c.lease_expires_at, c.released_at
            from support_requests as r
            left join lateral (
                select claim_token, lease_version, lease_expires_at, released_at
                from support_request_claims
                where request_id = r.request_id
                order by lease_version desc
                limit 1
            ) as c on true
            where r.request_id = %s
            for update of r
            """,
            (claim.request_id,),
        ).fetchone()
        if row is None:
            raise RequestNotFoundError(str(claim.request_id))
        if (
            row["status"] != "processing"
            or row["claim_token"] != claim.claim_token
            or row["lease_version"] != claim.lease_version
            or row["released_at"] is not None
            or row["lease_expires_at"] <= self._database_now(connection)
        ):
            raise StaleClaimError(
                f"claim {claim.lease_version} is not current for request {claim.request_id}"
            )

    @staticmethod
    def _finish_attempt(connection, claim: Claim, outcome: str) -> None:
        connection.execute(
            """
            update support_attempts
            set outcome = %s, completed_at = now()
            where request_id = %s and claim_token = %s
            """,
            (outcome, claim.request_id, claim.claim_token),
        )
        connection.execute(
            """
            update support_request_claims
            set released_at = now()
            where request_id = %s and claim_token = %s
            """,
            (claim.request_id, claim.claim_token),
        )

    @staticmethod
    def _database_now(connection) -> datetime:
        return connection.execute("select clock_timestamp() as now").fetchone()["now"]

    @staticmethod
    def _action_from_row(row: dict[str, Any]) -> OutboundAction:
        return OutboundAction(
            action_id=row["action_id"],
            request_id=row["request_id"],
            action_generation=row["action_generation"],
            status=row["status"],
            outbound_text=row["outbound_text"],
            content_hash=row["content_hash"],
        )

    @staticmethod
    def _raise_request_state(connection, request_id: UUID, message: str) -> None:
        row = connection.execute(
            "select status from support_requests where request_id = %s",
            (request_id,),
        ).fetchone()
        if row is None:
            raise RequestNotFoundError(str(request_id))
        raise StateConflictError(f"{message}: {row['status']}")
