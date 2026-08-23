"""Whether the real model can retrieve across the broader synthetic HR corpus."""

from __future__ import annotations

import unittest

from tests.evals.cases import (
    HOTEL_LIMIT,
    LEARNING_AND_TRAVEL,
    PROBATION_CHECK_INS,
    WORKPLACE_ADJUSTMENT,
)
from tests.evals.eval_case import EvalCase

SINGLE_POLICY_CASES = (HOTEL_LIMIT, PROBATION_CHECK_INS, WORKPLACE_ADJUSTMENT)


class PolicyBreadthEval(EvalCase):
    def test_supported_questions_retrieve_different_policy_topics(self) -> None:
        for case in SINGLE_POLICY_CASES:
            with self.subTest(case=case.id):
                outcome = self.run_question(case.question)

                self.assertEqual(outcome.result.decision, "answer")
                self.assertTrue(
                    case.expected_sources.issubset(
                        {source.source_filename for source in outcome.result.sources}
                    ),
                    f"expected citations from {sorted(case.expected_sources)}",
                )

    def test_one_question_can_use_two_policy_documents(self) -> None:
        outcome = self.run_question(LEARNING_AND_TRAVEL.question)

        self.assertEqual(outcome.result.decision, "answer")
        actual_sources = {source.source_filename for source in outcome.result.sources}
        self.assertTrue(
            LEARNING_AND_TRAVEL.expected_sources.issubset(actual_sources),
            f"expected citations from {sorted(LEARNING_AND_TRAVEL.expected_sources)}",
        )


if __name__ == "__main__":
    unittest.main()
