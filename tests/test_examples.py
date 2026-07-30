from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pydantic_ai.models import infer_model


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

    def test_vector_examples_use_postgres(self) -> None:
        for path in [Path("examples/07a_vector_rag.py"), Path("examples/07b_hybrid_rag.py")]:
            source = path.read_text(encoding="utf-8")

            self.assertIn("psycopg.connect", source, msg=str(path))
            self.assertIn("create extension if not exists vector", source, msg=str(path))
            self.assertIn("create table if not exists documents", source, msg=str(path))
            self.assertIn("<=>", source, msg=str(path))
            self.assertNotIn("cosine_similarity", source, msg=str(path))

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

    def test_sql_rag_uses_the_support_document_shape(self) -> None:
        source = Path("examples/06b_sql_rag.py").read_text(encoding="utf-8")

        self.assertIn("category", source)
        self.assertIn("keywords", source)
        self.assertIn("is_active = true", source)


if __name__ == "__main__":
    unittest.main()
