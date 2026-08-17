"""Ordering races between the webhook's follow-up write and a fast worker."""

from __future__ import annotations

from datetime import timedelta

from support_agent_app.application.lifecycle import LifecycleOutcome, task_name_for

from tests.fakes.postgres_test_case import PostgresTestCase


class MarkQueuedRaceTests(PostgresTestCase):
    def test_marking_queued_is_a_no_op_once_a_worker_has_claimed(self) -> None:
        """A fast queue can beat the webhook's own follow-up write.

        The task is delivered and claimed before `mark_queued` lands. That is
        the system working, so the late write must not raise.
        """
        accepted = self.accept_request("Ev-race")
        claim = self.repository.claim_request(accepted.request_id, timedelta(minutes=1))
        self.assertEqual(claim.outcome, LifecycleOutcome.CLAIMED)

        task_name = task_name_for("Ev-race")
        self.repository.mark_queued(accepted.request_id, confirmed_task_name=task_name)

        row = self.fetchone(
            "select status, confirmed_task_name from support_requests where request_id = %s",
            (accepted.request_id,),
        )
        assert row is not None
        # Still processing under the claim, and the task name was recorded.
        self.assertEqual(row["status"], "processing")
        self.assertEqual(row["confirmed_task_name"], task_name)

    def test_the_first_confirmed_task_name_is_kept(self) -> None:
        accepted = self.accept_request("Ev-first-name")

        self.repository.mark_queued(accepted.request_id, confirmed_task_name="task-one")
        self.repository.mark_queued(accepted.request_id, confirmed_task_name="task-two")

        row = self.fetchone(
            "select confirmed_task_name from support_requests where request_id = %s",
            (accepted.request_id,),
        )
        assert row is not None
        self.assertEqual(row["confirmed_task_name"], "task-one")


if __name__ == "__main__":
    import unittest

    unittest.main()
