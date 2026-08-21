"""Whether the real model can retrieve across the broader synthetic HR corpus."""

from __future__ import annotations

import unittest

from tests.evals.eval_case import EvalCase

SINGLE_POLICY_CASES = (
    ("How much can I spend on a hotel outside London?", {"expenses-policy.md"}),
    ("What happens at my probation check-ins?", {"onboarding-and-probation-policy.md"}),
    (
        "How do I request different hours because of a health condition?",
        {"workplace-adjustments-policy.md"},
    ),
)
MULTI_POLICY_QUESTION = "Can I use my learning budget for a conference and claim the train fare?"
MULTI_POLICY_SOURCES = {"learning-and-development-policy.md", "expenses-policy.md"}


class PolicyBreadthEval(EvalCase):
    def test_supported_questions_retrieve_different_policy_topics(self) -> None:
        for question, expected_sources in SINGLE_POLICY_CASES:
            with self.subTest(expected_sources=expected_sources):
                outcome = self.run_question(question)

                self.assertEqual(outcome.result.decision, "answer")
                self.assertTrue(
                    expected_sources.issubset(
                        {source.source_filename for source in outcome.result.sources}
                    ),
                    f"expected citations from {sorted(expected_sources)}",
                )

    def test_one_question_can_use_two_policy_documents(self) -> None:
        outcome = self.run_question(MULTI_POLICY_QUESTION)

        self.assertEqual(outcome.result.decision, "answer")
        actual_sources = {source.source_filename for source in outcome.result.sources}
        self.assertTrue(
            MULTI_POLICY_SOURCES.issubset(actual_sources),
            f"expected citations from {sorted(MULTI_POLICY_SOURCES)}",
        )


if __name__ == "__main__":
    unittest.main()
