from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import patch

from pydantic_ai.models import infer_model


def load_example(filename: str) -> ModuleType:
    path = Path("examples") / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LessonExamplesTest(unittest.TestCase):
    def test_repository_starts_without_a_finished_application(self) -> None:
        self.assertTrue(Path("brief.md").is_file())
        self.assertFalse(Path("support_agent_app/__init__.py").exists())
        self.assertFalse(Path("remotion-chart/package.json").exists())
        self.assertFalse(Path("Dockerfile").exists())

    def test_standalone_examples_do_not_import_shared_application_code(self) -> None:
        for path in sorted(Path("examples").glob("*.py")):
            source = path.read_text(encoding="utf-8")

            self.assertNotIn("from support_agent", source, msg=str(path))
            self.assertNotIn("import support_agent", source, msg=str(path))

    def test_retrieval_examples_have_local_policy_data(self) -> None:
        policy_paths = sorted(Path("examples/policies").glob("*.md"))

        self.assertEqual(len(policy_paths), 3)

    def test_whole_document_rag_exposes_an_index_and_read_tool(self) -> None:
        example = load_example("06a_file_rag.py")

        index = example.list_policy_documents()
        document = example.read_policy_document("annual-leave-policy")

        self.assertEqual(len(index), 3)
        self.assertTrue(document["found"])
        self.assertIn("five unused days", document["body"])

    def test_sql_rag_retrieves_an_exact_structured_fact(self) -> None:
        example = load_example("06b_sql_rag.py")

        with example.create_database() as connection:
            fact = example.get_policy_fact(
                connection,
                category="annual_leave",
                field="carry_over_days",
            )

        self.assertEqual(fact["value"], "5")
        self.assertEqual(fact["unit"], "days")
        self.assertEqual(fact["source"], "annual-leave-policy")

    def test_vector_rag_uses_cosine_similarity(self) -> None:
        example = load_example("07a_vector_rag.py")

        self.assertAlmostEqual(example.cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(example.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_hybrid_rag_fuses_keyword_and_vector_rankings(self) -> None:
        example = load_example("07b_hybrid_rag.py")

        scores = example.reciprocal_rank_fusion(
            [
                ["annual-leave-policy", "expenses-policy"],
                ["annual-leave-policy", "remote-working-policy"],
            ]
        )

        self.assertGreater(scores["annual-leave-policy"], scores["expenses-policy"])
        self.assertGreater(scores["annual-leave-policy"], scores["remote-working-policy"])

    def test_first_framework_agent_uses_direct_providers(self) -> None:
        source = Path("examples/05_first_framework_agent.py").read_text(encoding="utf-8")

        self.assertIn("from pydantic_ai import Agent", source)
        self.assertIn('OPENAI_MODEL = "openai:gpt-5.6"', source)
        self.assertIn('CLAUDE_MODEL = "anthropic:claude-sonnet-4-6"', source)
        self.assertIn("support_agent = Agent(", source)
        self.assertIn("tools=[list_support_documents, find_support_document]", source)
        self.assertIn("defer_model_check=True", source)

    def test_pydantic_ai_resolves_openai_and_anthropic_models(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"},
        ):
            openai_model = infer_model("openai:gpt-5.6")
            anthropic_model = infer_model("anthropic:claude-sonnet-4-6")

        self.assertEqual(type(openai_model).__name__, "OpenAIResponsesModel")
        self.assertEqual(type(anthropic_model).__name__, "AnthropicModel")

if __name__ == "__main__":
    unittest.main()
