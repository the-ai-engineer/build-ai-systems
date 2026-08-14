from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from support_agent_app.request_repository import ActionConflictError, LifecycleOutcome
from tests.postgres_test_case import PostgresTestCase


class OutboundActionTests(PostgresTestCase):
    def claim(self, event_id: str):
        accepted = self.accept_request(event_id)
        claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert claim is not None
        return claim

    def test_exact_outbound_text_and_hash_are_persisted_together(self) -> None:
        claim = self.claim("Ev-exact-action")
        outbound_text = "Synthetic exact outbound text."

        action = self.repository.create_reply_action(claim, outbound_text)

        expected_hash = f"sha256:{hashlib.sha256(outbound_text.encode('utf-8')).hexdigest()}"
        row = self.fetchone(
            """
            select status, outbound_text, content_hash
            from outbound_actions
            where action_id = %s
            """,
            (action.action_id,),
        )
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["outbound_text"], outbound_text)
        self.assertEqual(row["content_hash"], expected_hash)
        self.assertEqual(action.content_hash, expected_hash)

    def test_concurrent_action_creation_returns_one_sendable_action(self) -> None:
        claim = self.claim("Ev-action-race")

        with ThreadPoolExecutor(max_workers=2) as executor:
            actions = list(
                executor.map(
                    lambda _: self.repository.create_reply_action(
                        claim,
                        "Synthetic concurrent reply.",
                    ),
                    range(2),
                )
            )

        self.assertEqual(actions[0].action_id, actions[1].action_id)
        self.assertEqual(
            self.fetchone(
                """
                select count(*) as count
                from outbound_actions
                where request_id = %s and status <> 'cancelled'
                """,
                (claim.request_id,),
            )["count"],
            1,
        )

    def test_different_reply_for_same_generation_is_rejected(self) -> None:
        claim = self.claim("Ev-action-conflict")
        self.repository.create_reply_action(claim, "Synthetic first reply.")

        with self.assertRaises(ActionConflictError):
            self.repository.create_reply_action(claim, "Synthetic different reply.")

    def test_second_non_cancelled_reply_generation_is_rejected(self) -> None:
        claim = self.claim("Ev-action-generation")
        self.repository.create_reply_action(
            claim,
            "Synthetic first generation.",
            action_generation=1,
        )

        with self.assertRaises(ActionConflictError):
            self.repository.create_reply_action(
                claim,
                "Synthetic second generation.",
                action_generation=2,
            )

        self.assertEqual(
            self.fetchone(
                """
                select count(*) as count
                from outbound_actions
                where request_id = %s and status <> 'cancelled'
                """,
                (claim.request_id,),
            )["count"],
            1,
        )

    def test_known_send_failure_can_retry_the_exact_reply_with_a_new_claim(self) -> None:
        claim = self.claim("Ev-action-failed")
        action = self.repository.create_reply_action(claim, "Synthetic failed reply.")
        self.repository.mark_action_sending(claim, action.action_id)

        outcome = self.repository.mark_action_failed(
            claim,
            action.action_id,
            "provider_unavailable",
            retryable=True,
        )

        self.assertEqual(outcome, LifecycleOutcome.RETRYABLE)
        next_claim = self.repository.claim_request(
            claim.request_id,
            timedelta(minutes=1),
        ).claim
        assert next_claim is not None
        retry_action = self.repository.retry_failed_reply(next_claim, action.action_id)
        self.assertEqual(retry_action.action_generation, action.action_generation + 1)
        self.assertEqual(retry_action.outbound_text, action.outbound_text)
        self.assertEqual(retry_action.content_hash, action.content_hash)
        self.repository.mark_action_sending(next_claim, retry_action.action_id)
        self.repository.complete_reply(next_claim, retry_action.action_id, "300.001")

        rows = self.fetchone(
            """
            select
                count(*) filter (where a.status = 'cancelled') as cancelled_count,
                count(*) filter (where a.status = 'succeeded') as succeeded_count,
                min(r.status) as request_status
            from outbound_actions as a
            join support_requests as r using (request_id)
            where a.request_id = %s
            """,
            (claim.request_id,),
        )
        self.assertEqual(rows["cancelled_count"], 1)
        self.assertEqual(rows["succeeded_count"], 1)
        self.assertEqual(rows["request_status"], "completed")

    def test_uncertain_action_moves_request_to_reconciliation(self) -> None:
        claim = self.claim("Ev-uncertain")
        action = self.repository.create_reply_action(claim, "Synthetic uncertain reply.")
        self.repository.mark_action_sending(claim, action.action_id)

        outcome = self.repository.mark_action_uncertain(
            claim,
            action.action_id,
            "send_timeout",
        )

        self.assertEqual(outcome, LifecycleOutcome.RECONCILIATION)
        self.assertEqual(
            self.repository.claim_request(
                claim.request_id,
                timedelta(minutes=1),
            ).outcome,
            LifecycleOutcome.RECONCILIATION,
        )
        row = self.fetchone(
            """
            select a.status as action_status, r.status as request_status
            from outbound_actions as a
            join support_requests as r using (request_id)
            where a.action_id = %s
            """,
            (action.action_id,),
        )
        self.assertEqual(row["action_status"], "uncertain")
        self.assertEqual(row["request_status"], "reconciliation")


if __name__ == "__main__":
    import unittest

    unittest.main()
