from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from psycopg import connect

from support_agent_app.domain import AgentRunRecord, HumanReviewDecision, WorkflowOutcome
from support_agent_app.request_repository import LifecycleOutcome, StaleClaimError
from tests.postgres_test_case import PostgresTestCase


def synthetic_outcome() -> WorkflowOutcome:
    return WorkflowOutcome(
        result=HumanReviewDecision(
            reason="Synthetic request needs human review.",
            reason_code="unsupported",
        ),
        run=AgentRunRecord(
            model_id="function:test",
            model_location="local",
            service_tier="test",
            selected_documents=(),
            input_tokens=3,
            retrieved_context_tokens=0,
            output_tokens=2,
            duration_ms=1,
            finish_reason="stop",
            tool_call_count=1,
            model_turn_count=2,
        ),
    )


class WorkerClaimTests(PostgresTestCase):
    def test_concurrent_claim_is_atomic_and_active_lease_is_explicit(self) -> None:
        accepted = self.accept_request("Ev-claim-race")

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self.repository.claim_request(
                        accepted.request_id,
                        timedelta(minutes=1),
                    ),
                    range(2),
                )
            )

        self.assertCountEqual(
            [result.outcome for result in results],
            [LifecycleOutcome.CLAIMED, LifecycleOutcome.ACTIVE_LEASE],
        )
        self.assertEqual(
            self.fetchone(
                "select count(*) as count from support_request_claims where request_id = %s",
                (accepted.request_id,),
            )["count"],
            1,
        )

    def test_expired_worker_is_fenced_after_next_claim(self) -> None:
        accepted = self.accept_request("Ev-stale-worker")
        worker_a = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert worker_a is not None
        worker_a_action = self.repository.create_reply_action(
            worker_a,
            "Synthetic planned reply.",
        )
        with connect(self.database_url) as connection:
            connection.execute(
                """
                update support_request_claims
                set lease_expires_at = now() - interval '1 second'
                where request_id = %s and claim_token = %s
                """,
                (accepted.request_id, worker_a.claim_token),
            )

        worker_b_result = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        )
        worker_b = worker_b_result.claim
        assert worker_b is not None

        self.assertEqual(worker_b_result.outcome, LifecycleOutcome.CLAIMED)
        self.assertEqual(worker_b.lease_version, worker_a.lease_version + 1)
        with self.assertRaises(StaleClaimError):
            self.repository.record_workflow_result(worker_a, synthetic_outcome())
        with self.assertRaises(StaleClaimError):
            self.repository.create_reply_action(worker_a, "Synthetic stale reply.")
        with self.assertRaises(StaleClaimError):
            self.repository.mark_action_sending(worker_a, worker_a_action.action_id)
        with self.assertRaises(StaleClaimError):
            self.repository.retry_failed_reply(worker_a, worker_a_action.action_id)
        with self.assertRaises(StaleClaimError):
            self.repository.mark_action_failed(
                worker_a,
                worker_a_action.action_id,
                "stale_failure",
                retryable=True,
            )
        with self.assertRaises(StaleClaimError):
            self.repository.mark_action_uncertain(
                worker_a,
                worker_a_action.action_id,
                "stale_timeout",
            )
        with self.assertRaises(StaleClaimError):
            self.repository.record_failure(
                worker_a,
                "stale_failure",
                retryable=True,
            )
        with self.assertRaises(StaleClaimError):
            self.repository.complete_reply(worker_a, worker_a_action.action_id, "reply-ts")

        self.assertEqual(
            self.fetchone(
                "select count(*) as count from agent_runs where request_id = %s",
                (accepted.request_id,),
            )["count"],
            0,
        )
        self.assertEqual(
            self.fetchone(
                "select count(*) as count from outbound_actions where request_id = %s",
                (accepted.request_id,),
            )["count"],
            1,
        )

    def test_retryable_and_permanent_failure_outcomes_are_explicit(self) -> None:
        accepted = self.accept_request("Ev-failures")
        first_claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert first_claim is not None

        retryable = self.repository.record_failure(
            first_claim,
            "database_unavailable",
            retryable=True,
        )
        second_claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert second_claim is not None
        permanent = self.repository.record_failure(
            second_claim,
            "invalid_request",
            retryable=False,
        )

        self.assertEqual(retryable, LifecycleOutcome.RETRYABLE)
        self.assertEqual(permanent, LifecycleOutcome.PERMANENT_FAILURE)
        self.assertEqual(
            self.repository.claim_request(
                accepted.request_id,
                timedelta(minutes=1),
            ).outcome,
            LifecycleOutcome.PERMANENT_FAILURE,
        )

    def test_sixth_business_attempt_is_rejected_as_permanent_failure(self) -> None:
        accepted = self.accept_request("Ev-attempt-limit")

        for expected_attempt in range(1, 6):
            result = self.repository.claim_request(
                accepted.request_id,
                timedelta(minutes=1),
            )
            self.assertEqual(result.outcome, LifecycleOutcome.CLAIMED)
            assert result.claim is not None
            self.assertEqual(result.claim.business_attempt_number, expected_attempt)
            self.assertEqual(
                self.repository.record_failure(
                    result.claim,
                    "temporary_failure",
                    retryable=True,
                ),
                LifecycleOutcome.RETRYABLE,
            )

        exhausted = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        )

        self.assertEqual(exhausted.outcome, LifecycleOutcome.PERMANENT_FAILURE)
        row = self.fetchone(
            """
            select status, business_attempt_count, last_error_category
            from support_requests
            where request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["business_attempt_count"], 5)
        self.assertEqual(row["last_error_category"], "attempts_exhausted")

    def test_duplicate_complete_outcome_does_not_consume_an_attempt(self) -> None:
        accepted = self.accept_request("Ev-complete")
        claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert claim is not None
        action = self.repository.create_reply_action(claim, "Synthetic completed reply.")
        self.repository.mark_action_sending(claim, action.action_id)
        self.repository.complete_reply(claim, action.action_id, "200.001")

        duplicate = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        )

        self.assertEqual(duplicate.outcome, LifecycleOutcome.DUPLICATE_COMPLETE)
        self.assertEqual(
            self.fetchone(
                "select business_attempt_count from support_requests where request_id = %s",
                (accepted.request_id,),
            )["business_attempt_count"],
            1,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
