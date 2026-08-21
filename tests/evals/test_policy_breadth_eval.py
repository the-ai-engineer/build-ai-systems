"""Whether the real model can retrieve across the broader synthetic HR corpus."""

from __future__ import annotations

import unittest

from tests.evals.eval_case import EvalCase

SUPPORTED_CASES = (
    ("How much can I spend on a hotel outside London?", "expenses-policy.md"),
    ("What happens at my probation check-ins?", "onboarding-and-probation-policy.md"),
    (
        "How do I request different hours because of a health condition?",
        "workplace-adjustments-policy.md",
    ),
)


class PolicyBreadthEval(EvalCase):
    def test_supported_questions_retrieve_different_policy_topics(self) -> None:
        for question, expected_source in SUPPORTED_CASES:
            with self.subTest(expected_source=expected_source):
                outcome = self.run_question(question)

                self.assertEqual(outcome.result.decision, "answer")
                self.assertIn(
                    expected_source,
                    {source.source_filename for source in outcome.result.sources},
                )


if __name__ == "__main__":
    unittest.main()
