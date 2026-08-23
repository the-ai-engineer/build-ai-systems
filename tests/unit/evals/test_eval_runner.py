"""Deterministic checks for the live-eval runner."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from support_agent_app.application.domain import (
    AgentRunRecord,
    AnswerDecision,
    HumanReviewDecision,
    SourceCitation,
    WorkflowOutcome,
)
from support_agent_app.worker.agent.agent import MAX_MODEL_TURNS, MAX_TOOL_CALLS

from tests.evals.cases import GROUNDING, PERSONAL_PAY, PROMPT_INJECTION, SupportEvalCase
from tests.evals.run_evals import _require_google_cloud_settings, evaluate_outcome


def run_record(
    *,
    model_turns: int = 2,
    tool_calls: int = 2,
) -> AgentRunRecord:
    return AgentRunRecord(
        model_id="fixture",
        model_location="local",
        service_tier="deterministic-test",
        selected_documents=(),
        input_tokens=100,
        retrieved_context_tokens=50,
        output_tokens=20,
        duration_ms=10,
        finish_reason="stop",
        tool_call_count=tool_calls,
        model_turn_count=model_turns,
    )


class EvalRunnerTest(unittest.TestCase):
    def test_supported_answer_passes_all_deterministic_checks(self) -> None:
        outcome = WorkflowOutcome(
            result=AnswerDecision(
                answer="Employees may carry up to five unused days with manager approval.",
                reason="Supported by the annual leave policy.",
                sources=(
                    SourceCitation(
                        document_id="annual-leave-policy",
                        title="Annual Leave Policy",
                        source_filename="annual-leave-policy.md",
                        document_revision="test-revision",
                        supporting_excerpt=(
                            "Employees may carry up to five unused days into the next holiday "
                            "year with manager approval."
                        ),
                    ),
                ),
            ),
            run=run_record(),
        )

        self.assertEqual(evaluate_outcome(GROUNDING, outcome), ())

    def test_human_review_passes_without_an_answer_or_sources(self) -> None:
        outcome = WorkflowOutcome(
            result=HumanReviewDecision(
                reason="This needs a person to review it.",
                reason_code="sensitive",
            ),
            run=run_record(),
        )

        self.assertEqual(evaluate_outcome(PERSONAL_PAY, outcome), ())

    def test_failures_name_wrong_decisions_leaks_and_exceeded_budgets(self) -> None:
        outcome = WorkflowOutcome(
            result=HumanReviewDecision(
                reason="The policy says employees may carry up to five unused days.",
                reason_code="unsupported",
            ),
            run=run_record(
                model_turns=MAX_MODEL_TURNS + 1,
                tool_calls=MAX_TOOL_CALLS + 1,
            ),
        )

        failures = evaluate_outcome(PROMPT_INJECTION, outcome)

        self.assertIn("forbidden_text[0] found in result", failures)
        self.assertNotIn("carry up to five unused days", "\n".join(failures))
        self.assertIn(
            f"used {MAX_MODEL_TURNS + 1} model turns; limit is {MAX_MODEL_TURNS}",
            failures,
        )
        self.assertIn(
            f"used {MAX_TOOL_CALLS + 1} tool calls; limit is {MAX_TOOL_CALLS}",
            failures,
        )

    def test_missing_expected_source_is_reported(self) -> None:
        outcome = WorkflowOutcome(
            result=AnswerDecision(
                answer="The policy supports this answer.",
                reason="Supported.",
                sources=(
                    SourceCitation(
                        document_id="annual-leave-policy",
                        title="Annual Leave Policy",
                        source_filename="annual-leave-policy.md",
                        document_revision="test-revision",
                        supporting_excerpt="The holiday year runs from 1 January to 31 December.",
                    ),
                ),
            ),
            run=run_record(),
        )

        failures = evaluate_outcome(
            SupportEvalCase(
                id="wrong-source",
                category="supported",
                question="A synthetic question.",
                expected_decision="answer",
                expected_sources=frozenset({"expenses-policy.md"}),
            ),
            outcome,
        )

        self.assertEqual(failures, ("missing sources: expenses-policy.md",))

    def test_live_runner_names_missing_google_cloud_settings(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                SystemExit,
                "Set GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION before running live evals",
            ):
                _require_google_cloud_settings()

    def test_live_runner_accepts_complete_google_cloud_settings(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLOUD_PROJECT": "example-project",
                "GOOGLE_CLOUD_LOCATION": "global",
            },
            clear=True,
        ):
            _require_google_cloud_settings()


if __name__ == "__main__":
    unittest.main()
