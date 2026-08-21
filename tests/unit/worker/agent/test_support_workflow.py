from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncGenerator
from decimal import Decimal
from unittest import mock

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.telemetry import tracing as adk_tracing
from google.genai import types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import ValidationError
from support_agent_app.application.domain import (
    AgentRunRecord,
    HumanReviewDecision,
    LoadedDocumentRecord,
    SourceCitation,
    SupportDocument,
    SupportQuestion,
)
from support_agent_app.settings import ModelProviderSettings
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
from support_agent_app.worker.agent.agent import (
    DEFAULT_MODEL,
    MAX_MODEL_TURNS,
    MAX_OUTPUT_TOKENS,
    MAX_TOOL_CALLS,
    MODEL_THINKING_LEVEL,
    MODEL_TIMEOUT_SECONDS,
    _run_agent,
    build_agent,
    run_support_workflow,
)
from support_agent_app.worker.agent.evidence import verify_decision
from support_agent_app.worker.agent.pricing import estimate_run_cost, load_price_configuration
from support_agent_app.worker.agent.prompts import INSTRUCTIONS, build_instructions
from support_agent_app.worker.agent.schemas import AgentDecision
from support_agent_app.worker.agent.tools import (
    MAX_LOADED_DOCUMENTS,
    WorkflowDependencies,
    get_support_document,
)
from support_agent_app.worker.model_provider import (
    GOOGLE_CLOUD_SERVICE_TIER,
    ModelSelection,
    create_google_cloud_model,
)


class SupportWorkflowTests(unittest.TestCase):
    """Wiring, limits, and the deterministic checks around the model.

    A scripted model here proves the plumbing holds and that our guardrails
    survive a model that misbehaves. It proves nothing about how a real model
    behaves; that belongs in tests/evals/.
    """

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
        self.assertEqual(outcome.run.model_id, "fixture")
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

    # The safety behaviour that used to be "tested" here now lives in
    # tests/evals/test_safety_eval.py. A scripted model cannot answer whether
    # the agent refuses a sensitive question: the script returns the refusal it
    # was written to return. Against the real model, two of the reason codes
    # this test asserted turned out to be wrong.

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
        with self.assertRaisesRegex(ValueError, "at most 3 documents"):
            get_support_document(dependencies, documents[3].document_id)

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

        class FourDocumentModel(BaseLlm):
            model: str = "parallel-fixture"

            async def generate_content_async(
                self,
                llm_request: LlmRequest,
                stream: bool = False,
            ) -> AsyncGenerator[LlmResponse, None]:
                del llm_request, stream
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="get_support_document",
                                args={"document_id": document.document_id},
                            )
                            for document in documents
                        ],
                    ),
                    finish_reason=types.FinishReason.STOP,
                )

        agent = build_agent(FourDocumentModel(), dependencies)
        with self.assertRaisesRegex(ValueError, "at most 3 documents"):
            asyncio.run(_run_agent(agent, "Load four documents."))

        self.assertEqual(len(dependencies.loaded_documents), MAX_LOADED_DOCUMENTS)

    def test_run_metadata_excludes_question_and_policy_text(self) -> None:
        outcome = self.run_fixture("documented")
        serialized = outcome.run.model_dump_json()

        self.assertNotIn(FIXTURE_QUESTIONS["documented"].text, serialized)
        self.assertNotIn(DOCUMENTED_EXCERPT, serialized)
        self.assertNotIn("answer", AgentRunRecord.model_fields)
        self.assertNotIn("question", AgentRunRecord.model_fields)

    def test_adk_telemetry_excludes_message_and_tool_content(self) -> None:
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("privacy-test")
        dependencies = WorkflowDependencies(repository=fixture_repository("documented"))
        question_canary = "PRIVATE-QUESTION-CANARY"

        with mock.patch.object(adk_tracing, "tracer", tracer):
            asyncio.run(
                _run_agent(
                    build_agent(fixture_model("documented"), dependencies),
                    question_canary,
                )
            )

        spans = exporter.get_finished_spans()
        self.assertGreater(len(spans), 0)
        attributes = "\n".join(str(dict(span.attributes)) for span in spans)
        self.assertNotIn(question_canary, attributes)
        self.assertNotIn(DOCUMENTED_EXCERPT, attributes)
        self.assertNotIn("You may carry up to five unused days", attributes)

    def test_cost_estimate_uses_versioned_token_prices(self) -> None:
        prices = load_price_configuration()
        run = AgentRunRecord(
            model_id=DEFAULT_MODEL,
            model_location="global",
            service_tier=GOOGLE_CLOUD_SERVICE_TIER,
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
        self.assertEqual(outcome.run.model_id, model.model)

        with self.assertRaisesRegex(ValueError, "does not match"):
            run_support_workflow(
                FIXTURE_QUESTIONS["unsupported"],
                self.repository,
                model=model,
                model_id=DEFAULT_MODEL,
            )

    def test_safety_latency_and_cost_limits_are_explicit(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "gemini-3.5-flash")
        self.assertEqual(MAX_MODEL_TURNS, 6)
        self.assertEqual(MAX_TOOL_CALLS, 5)
        self.assertEqual(MAX_OUTPUT_TOKENS, 500)
        self.assertEqual(MODEL_TIMEOUT_SECONDS, 20.0)
        self.assertEqual(MODEL_THINKING_LEVEL, types.ThinkingLevel.MINIMAL)
        dependencies = WorkflowDependencies(repository=self.repository)
        agent = build_agent(fixture_model("unsupported"), dependencies)
        self.assertIsNone(agent.generate_content_config.service_tier)
        self.assertEqual(
            agent.generate_content_config.thinking_config,
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        )
        deadline_agent = build_agent(
            fixture_model("unsupported"),
            dependencies,
            model_timeout_seconds=3.0,
        )
        self.assertEqual(deadline_agent.timeout, 3.0)

    def test_default_service_tier_is_recorded_and_priced_but_not_sent(self) -> None:
        """Agent Platform rejects an explicit ``standard`` service tier.

        Omitting the field selects the documented pay-as-you-go default. The
        run record and price table still name that default so cost metadata is
        explicit without sending an unsupported provider value.
        """
        selection = ModelSelection(
            model="gemini-3.5-flash",
            model_id="gemini-3.5-flash",
            location="global",
            service_tier=GOOGLE_CLOUD_SERVICE_TIER,
        )
        agent = build_agent(
            selection.model,
            WorkflowDependencies(repository=self.repository),
        )

        self.assertIsNone(agent.generate_content_config.service_tier)
        self.assertNotIn("service_tier", agent.generate_content_config.model_fields_set)

        priced = {price.service_tier for price in load_price_configuration().prices}
        self.assertIn(selection.service_tier, priced)

    def test_the_prompt_states_the_limit_the_tool_enforces(self) -> None:
        """A limit written as prose is a duplicate definition, and drifts."""
        self.assertIn(f"no more than {MAX_LOADED_DOCUMENTS} documents", INSTRUCTIONS)
        self.assertIn("no more than 7 documents", build_instructions(7))

    def test_workflow_timeout_bounds_the_complete_agent_run(self) -> None:
        class SlowModel(BaseLlm):
            model: str = "slow-fixture"

            async def generate_content_async(
                self,
                llm_request: LlmRequest,
                stream: bool = False,
            ) -> AsyncGenerator[LlmResponse, None]:
                del llm_request, stream
                await asyncio.sleep(0.05)
                yield LlmResponse(finish_reason=types.FinishReason.STOP)

        with self.assertRaises(TimeoutError):
            run_support_workflow(
                FIXTURE_QUESTIONS["unsupported"],
                self.repository,
                model=SlowModel(),
                model_timeout_seconds=0.001,
            )

    def test_live_model_boundary_requires_google_cloud_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "Gemini"):
            create_google_cloud_model("openai:gpt-test")

    def test_google_cloud_model_uses_agent_platform_and_adc_configuration(self) -> None:
        selection = create_google_cloud_model(
            settings=ModelProviderSettings(
                model_name="gemini-3.5-flash",
                google_cloud_project="course-project",
                google_cloud_location="global",
            )
        )

        self.assertEqual(selection.model_id, "gemini-3.5-flash")
        self.assertEqual(selection.location, "global")
        self.assertEqual(selection.service_tier, "standard")
        self.assertEqual(
            selection.model.client_kwargs,
            {
                "enterprise": True,
                "project": "course-project",
                "location": "global",
            },
        )


if __name__ == "__main__":
    unittest.main()
