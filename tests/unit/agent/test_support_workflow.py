from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from support_agent_app.agent.agent import (
    DEFAULT_MODEL,
    MAX_MODEL_TURNS,
    MAX_OUTPUT_TOKENS,
    MAX_TOOL_CALLS,
    MODEL_TIMEOUT_SECONDS,
    build_agent,
    run_support_workflow,
)
from support_agent_app.agent.evidence import verify_decision
from support_agent_app.agent.schemas import AgentDecision
from support_agent_app.agent.tools import (
    MAX_LOADED_DOCUMENTS,
    WorkflowDependencies,
    get_support_document,
)
from support_agent_app.application.domain import (
    AgentRunRecord,
    HumanReviewDecision,
    LoadedDocumentRecord,
    SourceCitation,
    SupportDocument,
    SupportQuestion,
)
from support_agent_app.application.pricing import estimate_run_cost, load_price_configuration
from support_agent_app.integrations.model_provider import create_google_cloud_model
from support_agent_app.testing.fake_model import DOCUMENTED_EXCERPT, fixture_model
from support_agent_app.testing.fixtures import (
    FIXTURE_QUESTIONS,
    POLICY_DIRECTORY,
    fixture_repository,
)
from support_agent_app.testing.memory_repository import (
    DirectoryPolicyRepository,
    MemoryPolicyRepository,
)


class SupportWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = DirectoryPolicyRepository(POLICY_DIRECTORY)

    def run_fixture(self, name: str):
        return run_support_workflow(
            FIXTURE_QUESTIONS[name],
            fixture_repository(name),
            model=fixture_model(name),
        )

    def test_support_question_is_normalized_and_has_no_slack_fields(self) -> None:
        question = SupportQuestion(text="  Can\nI carry   leave?  ")

        self.assertEqual(question.text, "Can I carry leave?")
        self.assertEqual(set(SupportQuestion.model_fields), {"text"})

    def test_documented_fixture_returns_verified_source(self) -> None:
        outcome = self.run_fixture("documented")

        self.assertEqual(outcome.result.decision, "answer")
        self.assertIn("five unused days", outcome.result.answer)
        self.assertEqual(len(outcome.result.sources), 1)
        source = outcome.result.sources[0]
        self.assertEqual(source.document_id, "annual-leave-policy")
        self.assertEqual(source.source_filename, "annual-leave-policy.md")
        self.assertEqual(source.supporting_excerpt, DOCUMENTED_EXCERPT)
        document = self.repository.get_active_document(source.document_id)
        self.assertIsNotNone(document)
        assert document is not None
        self.assertEqual(source.document_revision, document.revision)
        self.assertIn(source.supporting_excerpt, document.body)
        self.assertEqual(outcome.run.tool_call_count, 2)
        self.assertEqual(outcome.run.model_turn_count, 3)
        self.assertEqual(outcome.run.finish_reason, "stop")
        self.assertEqual(outcome.run.model_id, "function:fixture")
        self.assertEqual(outcome.run.model_location, "local")
        self.assertGreater(outcome.run.retrieved_context_tokens, 0)
        self.assertEqual(
            outcome.run.selected_documents,
            (
                LoadedDocumentRecord(
                    document_id=document.document_id,
                    revision=document.revision,
                ),
            ),
        )

    def test_unsupported_fixture_returns_human_review_without_answer(self) -> None:
        outcome = self.run_fixture("unsupported")

        self.assertEqual(outcome.result.decision, "human_review")
        self.assertIsNone(outcome.result.answer)
        self.assertEqual(outcome.result.sources, ())
        self.assertEqual(outcome.result.reason_code, "unsupported")

    def test_sensitive_conflicting_and_prompt_injection_fixtures_are_referred(self) -> None:
        expected_codes = {
            "sensitive": "sensitive",
            "conflicting": "conflict",
            "prompt-injection": "unsupported",
        }
        for fixture, expected_code in expected_codes.items():
            with self.subTest(fixture=fixture):
                outcome = self.run_fixture(fixture)
                self.assertEqual(outcome.result.decision, "human_review")
                self.assertIsNone(outcome.result.answer)
                self.assertEqual(outcome.result.sources, ())
                self.assertEqual(outcome.result.reason_code, expected_code)

    def test_invalid_excerpt_is_converted_to_human_review(self) -> None:
        outcome = self.run_fixture("invalid-evidence")

        self.assertEqual(outcome.result.decision, "human_review")
        self.assertEqual(outcome.result.reason_code, "invalid_evidence")
        self.assertIsNone(outcome.result.answer)
        self.assertEqual(outcome.result.sources, ())

    def test_all_source_identity_fields_must_match_loaded_revision(self) -> None:
        document = self.repository.get_active_document("annual-leave-policy")
        assert document is not None
        valid_source = SourceCitation(
            document_id=document.document_id,
            title=document.title,
            source_filename=document.source_filename,
            document_revision=document.revision,
            supporting_excerpt=DOCUMENTED_EXCERPT,
        )
        cases = {
            "unloaded": valid_source.model_copy(update={"document_id": "expenses-policy"}),
            "title": valid_source.model_copy(update={"title": "Wrong title"}),
            "filename": valid_source.model_copy(update={"source_filename": "wrong.md"}),
            "revision": valid_source.model_copy(update={"document_revision": "sha256:wrong"}),
            "excerpt": valid_source.model_copy(update={"supporting_excerpt": "not present"}),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                decision = AgentDecision(
                    decision="answer",
                    answer="A proposed answer.",
                    reason="A proposed reason.",
                    sources=[source],
                )
                result = verify_decision(decision, {document.document_id: document})
                self.assertEqual(result.decision, "human_review")
                self.assertEqual(result.reason_code, "invalid_evidence")

    def test_whitespace_only_excerpt_is_rejected_by_schema_and_verifier(self) -> None:
        document = self.repository.get_active_document("annual-leave-policy")
        assert document is not None
        source_fields = {
            "document_id": document.document_id,
            "title": document.title,
            "source_filename": document.source_filename,
            "document_revision": document.revision,
            "supporting_excerpt": "\n",
        }
        with self.assertRaises(ValidationError):
            SourceCitation.model_validate(source_fields)

        unvalidated_source = SourceCitation.model_construct(**source_fields)
        decision = AgentDecision.model_construct(
            decision="answer",
            answer="An unsupported proposed answer.",
            reason="A proposed reason.",
            reason_code=None,
            sources=[unvalidated_source],
        )
        result = verify_decision(decision, {document.document_id: document})
        self.assertEqual(result.decision, "human_review")
        self.assertEqual(result.reason_code, "invalid_evidence")

    def test_human_review_schema_rejects_an_automated_answer(self) -> None:
        with self.assertRaises(ValidationError):
            HumanReviewDecision.model_validate(
                {
                    "decision": "human_review",
                    "answer": "This must not be accepted.",
                    "reason": "Needs a person.",
                    "reason_code": "unsupported",
                    "sources": [],
                }
            )

    def test_human_review_schema_rejects_whitespace_only_reason(self) -> None:
        with self.assertRaises(ValidationError):
            AgentDecision(
                decision="human_review",
                answer=None,
                reason="   ",
                reason_code="unsupported",
                sources=[],
            )
        with self.assertRaises(ValidationError):
            HumanReviewDecision(
                reason="\n",
                reason_code="unsupported",
            )

    def test_answer_schema_rejects_whitespace_only_text(self) -> None:
        document = self.repository.get_active_document("annual-leave-policy")
        assert document is not None
        source = SourceCitation(
            document_id=document.document_id,
            title=document.title,
            source_filename=document.source_filename,
            document_revision=document.revision,
            supporting_excerpt=DOCUMENTED_EXCERPT,
        )

        with self.assertRaises(ValidationError):
            AgentDecision(
                decision="answer",
                answer="   ",
                reason="The source supports it.",
                sources=[source],
            )

    def test_inactive_documents_are_not_listed_or_loaded(self) -> None:
        body = "# Inactive Policy\n\nThis policy is not approved."
        repository = MemoryPolicyRepository(
            [
                SupportDocument(
                    document_id="inactive-policy",
                    title="Inactive Policy",
                    category="test",
                    summary="Inactive.",
                    keywords=("inactive",),
                    source_filename="inactive-policy.md",
                    revision="sha256:test",
                    body=body,
                    is_active=False,
                )
            ]
        )

        self.assertEqual(repository.list_active_documents(), [])
        self.assertIsNone(repository.get_active_document("inactive-policy"))

    def test_document_tool_stops_before_loading_a_fourth_document(self) -> None:
        documents = [
            SupportDocument(
                document_id=f"policy-{index}",
                title=f"Policy {index}",
                category="test",
                summary="Test policy.",
                keywords=("test",),
                source_filename=f"policy-{index}.md",
                revision=f"sha256:{index}",
                body=f"Policy body {index}",
            )
            for index in range(MAX_LOADED_DOCUMENTS + 1)
        ]
        dependencies = WorkflowDependencies(
            repository=MemoryPolicyRepository(documents),
            loaded_documents={document.document_id: document for document in documents[:3]},
        )
        context = SimpleNamespace(deps=dependencies)

        with self.assertRaisesRegex(ValueError, "at most 3 documents"):
            get_support_document(context, documents[3].document_id)  # type: ignore[arg-type]

    def test_parallel_model_calls_cannot_bypass_document_limit(self) -> None:
        documents = [
            SupportDocument(
                document_id=f"policy-{index}",
                title=f"Policy {index}",
                category="test",
                summary="Test policy.",
                keywords=("test",),
                source_filename=f"policy-{index}.md",
                revision=f"sha256:{index}",
                body=f"Policy body {index}",
            )
            for index in range(MAX_LOADED_DOCUMENTS + 1)
        ]
        dependencies = WorkflowDependencies(repository=MemoryPolicyRepository(documents))

        def request_four_documents(messages, info):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "get_support_document",
                        {"document_id": document.document_id},
                    )
                    for document in documents
                ],
                model_name="parallel-fixture",
                finish_reason="stop",
            )

        agent = build_agent(FunctionModel(request_four_documents, model_name="parallel-fixture"))
        with self.assertRaisesRegex(ValueError, "at most 3 documents"):
            agent.run_sync("Load four documents.", deps=dependencies)

        self.assertEqual(len(dependencies.loaded_documents), MAX_LOADED_DOCUMENTS)

    def test_run_metadata_excludes_question_and_policy_text(self) -> None:
        outcome = self.run_fixture("documented")
        serialized = outcome.run.model_dump_json()

        self.assertNotIn(FIXTURE_QUESTIONS["documented"].text, serialized)
        self.assertNotIn(DOCUMENTED_EXCERPT, serialized)
        self.assertNotIn("answer", AgentRunRecord.model_fields)
        self.assertNotIn("question", AgentRunRecord.model_fields)

    def test_cost_estimate_uses_versioned_token_prices(self) -> None:
        prices = load_price_configuration()
        run = AgentRunRecord(
            model_id=DEFAULT_MODEL,
            model_location="global",
            service_tier="standard",
            selected_documents=(),
            input_tokens=1_000_000,
            retrieved_context_tokens=0,
            output_tokens=1_000_000,
            duration_ms=1,
            finish_reason="stop",
            tool_call_count=0,
            model_turn_count=1,
        )

        self.assertEqual(prices.effective_date, "2026-08-14")
        self.assertEqual(estimate_run_cost(run, prices), Decimal("10.50"))

        non_global_run = run.model_copy(update={"model_location": "europe-west4"})
        self.assertEqual(estimate_run_cost(non_global_run, prices), Decimal("11.55"))

    def test_injected_model_identity_is_derived_and_mismatch_is_rejected(self) -> None:
        model = fixture_model("unsupported")
        outcome = run_support_workflow(
            FIXTURE_QUESTIONS["unsupported"],
            self.repository,
            model=model,
        )
        self.assertEqual(outcome.run.model_id, model.model_id)

        with self.assertRaisesRegex(ValueError, "does not match"):
            run_support_workflow(
                FIXTURE_QUESTIONS["unsupported"],
                self.repository,
                model=model,
                model_id=DEFAULT_MODEL,
            )

    def test_safety_latency_and_cost_limits_are_explicit(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "google-cloud:gemini-3.5-flash")
        self.assertEqual(MAX_MODEL_TURNS, 6)
        self.assertEqual(MAX_TOOL_CALLS, 5)
        self.assertEqual(MAX_OUTPUT_TOKENS, 500)
        self.assertEqual(MODEL_TIMEOUT_SECONDS, 20.0)
        agent = build_agent(fixture_model("unsupported"))
        self.assertEqual(agent.model_settings["google_cloud_service_tier"], "on_demand")
        deadline_agent = build_agent(
            fixture_model("unsupported"),
            model_timeout_seconds=3.0,
        )
        self.assertEqual(deadline_agent.model_settings["timeout"], 3.0)

    def test_workflow_timeout_bounds_the_complete_agent_run(self) -> None:
        async def slow_model(messages, info):
            await asyncio.sleep(0.05)
            return ModelResponse(model_name="slow-fixture", finish_reason="stop")

        with self.assertRaises(TimeoutError):
            run_support_workflow(
                FIXTURE_QUESTIONS["unsupported"],
                self.repository,
                model=FunctionModel(slow_model, model_name="slow-fixture"),
                model_timeout_seconds=0.001,
            )

    def test_live_model_boundary_requires_google_cloud_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "google-cloud"):
            create_google_cloud_model("openai:gpt-test")


if __name__ == "__main__":
    unittest.main()
