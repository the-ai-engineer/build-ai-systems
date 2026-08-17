"""Whether a real model's citations survive the deterministic evidence check.

This is the eval that can see issue #38. `verify_decision` requires the cited
excerpt to appear in the document body as an exact substring, and a real model
re-wraps and re-punctuates when it copies. A unit test with a scripted model
cannot detect that, because the script returns a byte-exact excerpt by
construction.

A failure here is not necessarily a model problem. It may mean the strictness is
set wrong, which is the decision issue #38 exists to make.
"""

from __future__ import annotations

import unittest

from support_agent_app.testing.fixtures import POLICY_DIRECTORY

from tests.evals.eval_case import EvalCase

DOCUMENTED = "Can unused annual leave be carried into next year?"


class GroundingEval(EvalCase):
    def test_a_supported_question_is_answered_with_a_verifiable_citation(self) -> None:
        outcome = self.run_question(DOCUMENTED)

        self.assertEqual(
            outcome.result.decision,
            "answer",
            "the model either refused a documented question or its citation failed "
            "verification; see ARCHITECTURE.md on excerpt strictness",
        )
        self.assertTrue(outcome.result.sources)

    def test_every_cited_excerpt_really_appears_in_its_source_file(self) -> None:
        outcome = self.run_question(DOCUMENTED)
        if outcome.result.decision != "answer":
            self.skipTest("the model did not produce an answer for this run")

        for source in outcome.result.sources:
            body = (POLICY_DIRECTORY / source.source_filename).read_text(encoding="utf-8")
            self.assertIn(
                source.supporting_excerpt,
                body,
                f"excerpt not found verbatim in {source.source_filename}",
            )

    def test_the_answer_does_not_invent_a_source(self) -> None:
        outcome = self.run_question(DOCUMENTED)
        if outcome.result.decision != "answer":
            self.skipTest("the model did not produce an answer for this run")

        on_disk = {path.name for path in POLICY_DIRECTORY.glob("*.md")}
        for source in outcome.result.sources:
            self.assertIn(source.source_filename, on_disk)


if __name__ == "__main__":
    unittest.main()
