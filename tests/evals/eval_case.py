"""Shared setup for evals: tests that call the real model.

These are not unit tests. They are slow, cost money, and can disagree with
themselves between runs, because the thing under test is a model rather than a
function. They live apart so `unittest discover` stays free and offline.

They skip unless GOOGLE_CLOUD_PROJECT is set, the same way the Postgres tests
skip without DATABASE_URL.
"""

from __future__ import annotations

import os
import unittest

from support_agent_app.testing.fixtures import POLICY_DIRECTORY
from support_agent_app.testing.memory_repository import DirectoryPolicyRepository

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
EVAL_TIMEOUT_SECONDS = 60.0


@unittest.skipUnless(GOOGLE_CLOUD_PROJECT, "GOOGLE_CLOUD_PROJECT is required to run evals")
class EvalCase(unittest.TestCase):
    """A real agent run against the real policy set."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.repository = DirectoryPolicyRepository(POLICY_DIRECTORY)

    def run_question(self, text: str):
        from support_agent_app.application.domain import SupportQuestion
        from support_agent_app.worker.agent.agent import run_support_workflow

        return run_support_workflow(
            SupportQuestion(text=text),
            self.repository,
            model_timeout_seconds=EVAL_TIMEOUT_SECONDS,
        )
