from __future__ import annotations

import hashlib
from datetime import timedelta

from psycopg import connect, errors
from psycopg.rows import dict_row

from support_agent_app.fake_model import fixture_model
from support_agent_app.fixtures import FIXTURE_QUESTIONS
from support_agent_app.postgres import connect_with_timeout
from support_agent_app.repositories import PostgresPolicyRepository
from support_agent_app.request_repository import (
    IncomingSupportRequest,
    LifecycleOutcome,
)
from support_agent_app.seed_policies import seed_policy_documents
from support_agent_app.slack_actions import (
    HUMAN_REVIEW_REPLY,
    FakeSlackClient,
    SlackSendError,
)
from support_agent_app.worker_service import (
    WorkerDeadline,
    WorkerService,
    WorkerTemporaryError,
)
from support_agent_app.workflow import run_support_workflow
from tests.postgres_test_case import PostgresTestCase


class CountingWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self.model_timeouts = []

    def __call__(self, question, repository, *, model, model_timeout_seconds):
        self.calls += 1
        self.model_timeouts.append(model_timeout_seconds)
        return run_support_workflow(
            question,
            repository,
            model=model,
            model_timeout_seconds=model_timeout_seconds,
        )


class InspectingSlackClient(FakeSlackClient):
    def __init__(self, database_url: str, behavior="success") -> None:
        super().__init__(behavior)
        self.database_url = database_url
        self.persisted_before_send = False

    def post_thread_reply(self, **kwargs):
        with connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                select a.status, a.outbound_text, a.content_hash,
                       exists(
                           select 1 from agent_runs where request_id = a.request_id
                       ) as has_run,
                       exists(
                           select 1 from agent_run_sources as s
                           join agent_runs as r using (agent_run_id)
                           where r.request_id = a.request_id
                       ) as has_source_revision,
                       exists(
                           select 1 from support_decisions as d
                           where d.request_id = a.request_id
                             and jsonb_array_length(d.sources) > 0
                       ) as has_verified_sources
                from outbound_actions as a
                where a.outbound_text = %s
                """,
                (kwargs["text"],),
            ).fetchone()
        expected_hash = f"sha256:{hashlib.sha256(kwargs['text'].encode()).hexdigest()}"
        self.persisted_before_send = row == {
            "status": "sending",
            "outbound_text": kwargs["text"],
            "content_hash": expected_hash,
            "has_run": True,
            "has_source_revision": True,
            "has_verified_sources": True,
        }
        return super().post_thread_reply(**kwargs)


class PermanentlyRejectedSlackClient(FakeSlackClient):
    def post_thread_reply(self, **kwargs):
        self.attempts.append(kwargs)
        raise SlackSendError("slack_request_rejected", retryable=False)


class WorkerTests(PostgresTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if cls.database_url:
            seed_policy_documents(cls.database_url)

    def accept_fixture(self, fixture: str, event_id: str):
        accepted = self.repository.accept_request(
            IncomingSupportRequest(
                slack_event_id=event_id,
                slack_team_id="T-worker",
                slack_channel_id="C-worker",
                slack_message_ts="500.001",
                slack_thread_ts="500.001",
                slack_user_id="U-worker",
                question_text=FIXTURE_QUESTIONS[fixture].text,
            )
        )
        self.repository.mark_queued(accepted.request_id)
        return accepted

    def service(self, fixture: str, slack, workflow=None) -> WorkerService:
        return WorkerService(
            requests=self.repository,
            policies=PostgresPolicyRepository(self.database_url),
            model=fixture_model(fixture),
            slack=slack,
            workflow_runner=workflow or run_support_workflow,
        )

    def test_documented_request_persists_evidence_and_exact_reply_before_send(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-documented")
        slack = InspectingSlackClient(self.database_url)

        result = self.service("documented", slack).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, "completed")
        self.assertTrue(result.send_attempted)
        self.assertTrue(slack.persisted_before_send)
        self.assertEqual(len(slack.attempts), 1)
        reply = slack.attempts[0].text
        self.assertIn("Sources", reply)
        self.assertIn("annual-leave-policy.md", reply)
        row = self.fetchone(
            """
            select r.status as request_status, d.decision, d.sources,
                   a.status as action_status, a.outbound_text, a.content_hash,
                   count(ar.agent_run_id) over () as run_count,
                   count(ars.document_id) over () as source_revision_count
            from support_requests as r
            join support_decisions as d using (request_id)
            join outbound_actions as a using (request_id)
            join agent_runs as ar using (request_id)
            join agent_run_sources as ars using (agent_run_id)
            where r.request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(row["request_status"], "completed")
        self.assertEqual(row["decision"], "answer")
        self.assertEqual(row["action_status"], "succeeded")
        self.assertEqual(row["outbound_text"], reply)
        self.assertEqual(
            row["content_hash"],
            f"sha256:{hashlib.sha256(reply.encode()).hexdigest()}",
        )
        self.assertEqual(row["run_count"], 1)
        self.assertEqual(row["source_revision_count"], 1)
        self.assertEqual(row["sources"][0]["source_filename"], "annual-leave-policy.md")
        self.assertTrue(row["sources"][0]["supporting_excerpt"])
        self.assertTrue(row["sources"][0]["document_revision"].startswith("sha256:"))

    def test_database_operations_receive_a_statement_timeout(self) -> None:
        with self.assertRaises(errors.QueryCanceled):
            with connect_with_timeout(
                self.database_url,
                timeout_seconds=0.01,
            ) as connection:
                connection.execute("select pg_sleep(0.1)")

    def test_human_review_uses_exact_fixed_reply_without_a_tag(self) -> None:
        accepted = self.accept_fixture("unsupported", "Ev-worker-human-review")
        slack = FakeSlackClient()

        result = self.service("unsupported", slack).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, "completed")
        self.assertEqual(slack.attempts[0].text, HUMAN_REVIEW_REPLY)
        self.assertNotIn("<@", slack.attempts[0].text)
        self.assertNotIn("<!subteam", slack.attempts[0].text)
        decision = self.fetchone(
            """
            select decision, answer, sources
            from support_decisions
            where request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(decision["decision"], "human_review")
        self.assertIsNone(decision["answer"])
        self.assertEqual(decision["sources"], [])

    def test_duplicate_complete_does_not_repeat_model_or_send(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-duplicate")
        workflow = CountingWorkflow()
        slack = FakeSlackClient()
        service = self.service("documented", slack, workflow)

        first = service.process(accepted.request_id, WorkerDeadline.after(30))
        duplicate = service.process(accepted.request_id, WorkerDeadline.after(30))

        self.assertEqual(first.outcome, "completed")
        self.assertEqual(duplicate.outcome, LifecycleOutcome.DUPLICATE_COMPLETE.value)
        self.assertEqual(workflow.calls, 1)
        self.assertEqual(len(slack.attempts), 1)
        counts = self.fetchone(
            """
            select
                (select count(*) from agent_runs where request_id = %s) as runs,
                (select count(*) from outbound_actions
                 where request_id = %s and status = 'succeeded') as replies
            """,
            (accepted.request_id, accepted.request_id),
        )
        self.assertEqual(counts, {"runs": 1, "replies": 1})

    def test_active_lease_does_not_start_the_model_or_send(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-active-lease")
        active_claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert active_claim is not None
        workflow = CountingWorkflow()
        slack = FakeSlackClient()

        result = self.service("documented", slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, LifecycleOutcome.ACTIVE_LEASE.value)
        self.assertEqual(workflow.calls, 0)
        self.assertEqual(slack.attempts, [])

    def test_known_temporary_send_failure_retries_exact_reply_without_model(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-clear-failure")
        workflow = CountingWorkflow()
        first_slack = FakeSlackClient("clear-failure")

        first = self.service("documented", first_slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )
        second_slack = FakeSlackClient()
        second = self.service("documented", second_slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(first.outcome, LifecycleOutcome.RETRYABLE.value)
        self.assertEqual(second.outcome, "completed")
        self.assertEqual(workflow.calls, 1)
        self.assertEqual(first_slack.attempts[0].text, second_slack.attempts[0].text)
        counts = self.fetchone(
            """
            select count(*) filter (where status = 'cancelled') as cancelled,
                   count(*) filter (where status = 'succeeded') as succeeded
            from outbound_actions
            where request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(counts, {"cancelled": 1, "succeeded": 1})

    def test_database_failure_before_send_retries_without_reconciliation(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-pre-send-database")
        workflow = CountingWorkflow()
        first_slack = FakeSlackClient()
        original_mark_sending = self.repository.mark_action_sending

        def fail_before_send(*args, **kwargs):
            raise ConnectionError("synthetic pre-send database failure")

        self.repository.mark_action_sending = fail_before_send
        try:
            first = self.service("documented", first_slack, workflow).process(
                accepted.request_id,
                WorkerDeadline.after(30),
            )
        finally:
            self.repository.mark_action_sending = original_mark_sending

        self.assertEqual(first.outcome, LifecycleOutcome.RETRYABLE.value)
        self.assertEqual(first_slack.attempts, [])
        failed = self.fetchone(
            """
            select r.status as request_status, a.status as action_status,
                   r.last_error_category
            from support_requests as r
            join outbound_actions as a using (request_id)
            where r.request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(
            failed,
            {
                "request_status": "queued",
                "action_status": "failed",
                "last_error_category": "database_pre_send_failure",
            },
        )

        second_slack = FakeSlackClient()
        second = self.service("documented", second_slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(second.outcome, "completed")
        self.assertEqual(workflow.calls, 1)
        self.assertEqual(len(second_slack.attempts), 1)
        self.assertEqual(
            self.fetchone(
                "select status from support_requests where request_id = %s",
                (accepted.request_id,),
            )["status"],
            "completed",
        )

    def test_clear_permanent_send_rejection_fails_without_retry(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-permanent-send")
        slack = PermanentlyRejectedSlackClient()

        result = self.service("documented", slack).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, LifecycleOutcome.PERMANENT_FAILURE.value)
        self.assertEqual(len(slack.attempts), 1)
        row = self.fetchone(
            "select status, last_error_category from support_requests where request_id = %s",
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {"status": "failed", "last_error_category": "slack_request_rejected"},
        )

    def test_uncertain_send_reconciles_once_and_is_not_automatically_retried(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-uncertain")
        workflow = CountingWorkflow()
        slack = FakeSlackClient("uncertain")
        service = self.service("documented", slack, workflow)

        first = service.process(accepted.request_id, WorkerDeadline.after(30))
        duplicate = service.process(accepted.request_id, WorkerDeadline.after(30))

        self.assertEqual(first.outcome, LifecycleOutcome.RECONCILIATION.value)
        self.assertEqual(duplicate.outcome, LifecycleOutcome.RECONCILIATION.value)
        self.assertEqual(workflow.calls, 1)
        self.assertEqual(len(slack.attempts), 1)
        row = self.fetchone(
            """
            select r.status as request_status, a.status as action_status
            from support_requests as r
            join outbound_actions as a using (request_id)
            where r.request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {"request_status": "reconciliation", "action_status": "uncertain"},
        )

    def test_known_send_with_unrecorded_result_enters_reconciliation(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-result-write-failure")
        slack = FakeSlackClient()
        original_complete = self.repository.complete_reply

        def fail_completion(*args, **kwargs):
            raise ConnectionError("synthetic result write failure")

        self.repository.complete_reply = fail_completion
        try:
            result = self.service("documented", slack).process(
                accepted.request_id,
                WorkerDeadline.after(30),
            )
        finally:
            self.repository.complete_reply = original_complete

        self.assertEqual(result.outcome, LifecycleOutcome.RECONCILIATION.value)
        self.assertEqual(len(slack.attempts), 1)
        row = self.fetchone(
            """
            select r.status as request_status, a.status as action_status,
                   r.last_error_category
            from support_requests as r
            join outbound_actions as a using (request_id)
            where r.request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {
                "request_status": "reconciliation",
                "action_status": "uncertain",
                "last_error_category": "send_result_not_recorded",
            },
        )

    def test_expired_claim_resumes_recorded_decision_without_another_model_call(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-resume-decision")
        old_claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert old_claim is not None
        outcome = run_support_workflow(
            FIXTURE_QUESTIONS["documented"],
            PostgresPolicyRepository(self.database_url),
            model=fixture_model("documented"),
        )
        self.repository.record_workflow_result(old_claim, outcome)
        self._expire_claim(old_claim.claim_token)
        workflow = CountingWorkflow()
        slack = FakeSlackClient()

        result = self.service("documented", slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, "completed")
        self.assertEqual(workflow.calls, 0)
        self.assertEqual(len(slack.attempts), 1)
        self.assertEqual(
            self.fetchone(
                "select count(*) as count from agent_runs where request_id = %s",
                (accepted.request_id,),
            )["count"],
            1,
        )

    def test_expired_claim_with_stranded_action_enters_reconciliation_without_send(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-stranded-action")
        old_claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert old_claim is not None
        action = self.repository.create_reply_action(old_claim, "Synthetic stranded reply.")
        self._expire_claim(old_claim.claim_token)
        workflow = CountingWorkflow()
        slack = FakeSlackClient()

        result = self.service("documented", slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(30),
        )

        self.assertEqual(result.outcome, LifecycleOutcome.RECONCILIATION.value)
        self.assertEqual(workflow.calls, 0)
        self.assertEqual(slack.attempts, [])
        row = self.fetchone(
            "select status from outbound_actions where action_id = %s",
            (action.action_id,),
        )
        self.assertEqual(row["status"], "uncertain")

    def test_worker_stops_before_deadline_without_starting_the_model_or_send(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-deadline")
        workflow = CountingWorkflow()
        slack = FakeSlackClient()

        result = self.service("documented", slack, workflow).process(
            accepted.request_id,
            WorkerDeadline.after(5),
        )

        self.assertEqual(result.outcome, LifecycleOutcome.RETRYABLE.value)
        self.assertEqual(workflow.calls, 0)
        self.assertEqual(slack.attempts, [])
        row = self.fetchone(
            """
            select status, business_attempt_count, last_error_category
            from support_requests
            where request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {
                "status": "queued",
                "business_attempt_count": 1,
                "last_error_category": "worker_deadline",
            },
        )

    def test_database_step_consuming_send_budget_does_not_call_slack(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-send-budget")
        workflow = CountingWorkflow()
        slack = FakeSlackClient()
        clock = [0.0]
        deadline = WorkerDeadline(expires_at=30.0, clock=lambda: clock[0])
        original_mark_sending = self.repository.mark_action_sending

        def consume_send_budget(*args, **kwargs):
            self.assertLessEqual(kwargs["timeout_seconds"], 29.0)
            original_mark_sending(*args, **kwargs)
            clock[0] = 29.0

        self.repository.mark_action_sending = consume_send_budget
        try:
            result = self.service("documented", slack, workflow).process(
                accepted.request_id,
                deadline,
            )
        finally:
            self.repository.mark_action_sending = original_mark_sending

        self.assertEqual(result.outcome, LifecycleOutcome.RETRYABLE.value)
        self.assertFalse(result.send_attempted)
        self.assertEqual(slack.attempts, [])
        self.assertEqual(workflow.calls, 1)
        self.assertLessEqual(workflow.model_timeouts[0], 29.0)
        row = self.fetchone(
            """
            select r.status as request_status, a.status as action_status,
                   r.last_error_category
            from support_requests as r
            join outbound_actions as a using (request_id)
            where r.request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {
                "request_status": "queued",
                "action_status": "failed",
                "last_error_category": "worker_deadline",
            },
        )

    def test_temporary_model_failure_remains_retryable(self) -> None:
        accepted = self.accept_fixture("documented", "Ev-worker-model-timeout")

        def timeout(*args, **kwargs):
            raise TimeoutError("synthetic timeout")

        with self.assertRaises(WorkerTemporaryError):
            self.service("documented", FakeSlackClient(), timeout).process(
                accepted.request_id,
                WorkerDeadline.after(30),
            )

        row = self.fetchone(
            "select status, last_error_category from support_requests where request_id = %s",
            (accepted.request_id,),
        )
        self.assertEqual(
            row,
            {"status": "queued", "last_error_category": "model_temporary_failure"},
        )

    def _expire_claim(self, claim_token) -> None:
        with connect(self.database_url) as connection:
            connection.execute(
                """
                update support_request_claims
                set lease_expires_at = now() - interval '1 second'
                where claim_token = %s
                """,
                (claim_token,),
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
