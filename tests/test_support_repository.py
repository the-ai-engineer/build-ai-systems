from __future__ import annotations

from datetime import timedelta

from support_agent_app.domain import (
    AgentRunRecord,
    AnswerDecision,
    LoadedDocumentRecord,
    SourceCitation,
    WorkflowOutcome,
)
from support_agent_app.request_repository import IncomingSupportRequest
from tests.postgres_test_case import PostgresTestCase


class SupportRepositoryTests(PostgresTestCase):
    def test_replayed_slack_event_returns_existing_request(self) -> None:
        incoming = IncomingSupportRequest(
            slack_event_id="Ev-duplicate",
            slack_team_id="T-test",
            slack_channel_id="C-test",
            slack_message_ts="101.001",
            slack_thread_ts="101.001",
            slack_user_id="U-test",
            question_text="A synthetic retained question.",
        )

        first = self.repository.accept_request(incoming)
        replay = self.repository.accept_request(incoming)

        self.assertTrue(first.created)
        self.assertFalse(replay.created)
        self.assertEqual(replay.request_id, first.request_id)
        self.assertNotIn(incoming.question_text, repr(first))
        self.assertNotIn(incoming.question_text, repr(replay))
        row = self.fetchone(
            """
            select count(*) as request_count, min(question_text) as question_text,
                   min(content_expires_at) - min(created_at) as retention
            from support_requests
            where slack_event_id = %s
            """,
            (incoming.slack_event_id,),
        )
        self.assertEqual(row["request_count"], 1)
        self.assertEqual(row["question_text"], incoming.question_text)
        self.assertEqual(row["retention"], timedelta(days=30))

    def test_request_has_auditable_lifecycle_timestamps(self) -> None:
        accepted = self.accept_request("Ev-timestamps")
        claim_result = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        )

        row = self.fetchone(
            """
            select status, created_at, queued_at, processing_at, business_attempt_count
            from support_requests
            where request_id = %s
            """,
            (accepted.request_id,),
        )
        self.assertEqual(row["status"], "processing")
        self.assertIsNotNone(row["created_at"])
        self.assertIsNotNone(row["queued_at"])
        self.assertIsNotNone(row["processing_at"])
        self.assertEqual(row["business_attempt_count"], 1)
        self.assertEqual(claim_result.claim.business_attempt_number, 1)

    def test_workflow_result_keeps_safe_run_metadata_and_source_revision(self) -> None:
        accepted = self.accept_request("Ev-result")
        claim = self.repository.claim_request(
            accepted.request_id,
            timedelta(minutes=1),
        ).claim
        assert claim is not None
        source = SourceCitation(
            document_id="policy-1",
            title="Synthetic Policy",
            source_filename="synthetic-policy.md",
            document_revision="sha256:revision-1",
            supporting_excerpt="Synthetic supporting excerpt.",
        )
        outcome = WorkflowOutcome(
            result=AnswerDecision(
                answer="A synthetic answer.",
                reason="The synthetic source supports it.",
                sources=(source,),
            ),
            run=AgentRunRecord(
                model_id="function:test",
                model_location="local",
                service_tier="test",
                selected_documents=(
                    LoadedDocumentRecord(
                        document_id=source.document_id,
                        revision=source.document_revision,
                    ),
                ),
                input_tokens=10,
                retrieved_context_tokens=7,
                output_tokens=5,
                duration_ms=2,
                finish_reason="stop",
                tool_call_count=2,
                model_turn_count=3,
            ),
        )

        agent_run_id = self.repository.record_workflow_result(claim, outcome)

        run = self.fetchone(
            """
            select r.model_id, r.input_tokens, r.retrieved_context_tokens,
                   s.document_id, s.document_revision
            from agent_runs as r
            join agent_run_sources as s using (agent_run_id)
            where r.agent_run_id = %s
            """,
            (agent_run_id,),
        )
        self.assertEqual(run["model_id"], "function:test")
        self.assertEqual(run["input_tokens"], 10)
        self.assertEqual(run["retrieved_context_tokens"], 7)
        self.assertEqual(run["document_id"], "policy-1")
        self.assertEqual(run["document_revision"], "sha256:revision-1")
        serialized_run = str(run)
        self.assertNotIn("A synthetic policy question.", serialized_run)
        self.assertNotIn("A synthetic answer.", serialized_run)


if __name__ == "__main__":
    import unittest

    unittest.main()
