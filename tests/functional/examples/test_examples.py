from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

EXPECTED_POLICY_IDS = {
    "annual-leave-policy",
    "bereavement-and-compassionate-leave-policy",
    "employee-data-and-records-policy",
    "expenses-policy",
    "family-leave-policy",
    "flexible-working-policy",
    "learning-and-development-policy",
    "onboarding-and-probation-policy",
    "pay-and-benefits-policy",
    "remote-working-policy",
    "sickness-absence-policy",
    "working-hours-policy",
    "workplace-adjustments-policy",
    "workplace-conduct-policy",
}


def load_example(filename: str) -> ModuleType:
    path = Path("examples") / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class LessonExamplesTest(unittest.TestCase):
    def test_repository_contract_exists(self) -> None:
        for path in [
            Path("brief.md"),
            Path("MEMORY.md"),
            Path("docs/course-code-map.md"),
            Path("docs/final-agent-spec.md"),
            Path("docs/rag/README.md"),
            Path("docs/rag/postgres-document-store.md"),
            Path("docs/rag/postgres-and-pgvector.md"),
            Path("docs/rag/vector-search.md"),
            Path("docs/rag/keyword-search.md"),
            Path("docs/rag/hybrid-search.md"),
            Path("docs/rag/agentic-search.md"),
            Path("docs/resources/deploy-with-codex-prompt.md"),
            Path("docs/resources/hr-policy-demo-questions.md"),
        ]:
            self.assertTrue(path.is_file(), msg=str(path))

    def test_standalone_examples_do_not_import_shared_application_code(self) -> None:
        for path in sorted(Path("examples").rglob("*.py")):
            source = path.read_text(encoding="utf-8")

            self.assertNotIn("from support_agent", source, msg=str(path))
            self.assertNotIn("import support_agent", source, msg=str(path))
            self.assertNotIn("from support_agent_app", source, msg=str(path))
            self.assertNotIn("import support_agent_app", source, msg=str(path))

    def test_retrieval_examples_have_local_policy_data(self) -> None:
        policy_paths = sorted(Path("policies").glob("*.md"))

        self.assertEqual({path.stem for path in policy_paths}, EXPECTED_POLICY_IDS)

    def test_lesson_five_uses_a_complete_document_store(self) -> None:
        sql = Path("examples/lesson-05/01_setup.sql").read_text(encoding="utf-8")

        self.assertIn("lesson_05.support_documents", sql)
        self.assertNotIn("support_document_chunks", sql)
        self.assertNotIn("vector", sql.lower())
        source = Path("examples/lesson-05/agentic_search.py").read_text(encoding="utf-8")
        self.assertIn("lesson_05.support_documents", source)

    def test_lesson_five_has_one_visible_agentic_search_command(self) -> None:
        example = load_example("lesson-05/agentic_search.py")

        with patch.dict(os.environ, {}, clear=True):
            agent = example.build_agent("postgresql://unused")
        self.assertEqual(agent.name, "policy_agent")
        self.assertEqual(agent.model, "gemini-3.7-flash")
        self.assertEqual(
            [tool.__name__ for tool in agent.tools],
            ["list_support_documents", "read_support_document"],
        )
        self.assertTrue(callable(example.agentic_search))
        self.assertFalse(Path("examples/lesson-05/policy_agent/__init__.py").exists())

        command = subprocess.run(
            [sys.executable, "examples/lesson-05/agentic_search.py", "--help"],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(command.returncode, 0, msg=command.stderr)
        self.assertIn("Let an agent choose and read a policy.", command.stdout)

    def test_lesson_five_allows_a_model_override(self) -> None:
        example = load_example("lesson-05/agentic_search.py")

        with patch.dict(os.environ, {"SUPPORT_AGENT_MODEL": "review-override"}):
            agent = example.build_agent("postgresql://unused")

        self.assertEqual(agent.model, "review-override")

    def test_lesson_six_uses_pgvector_and_full_text_search(self) -> None:
        sql = Path("examples/lesson-06/01_setup.sql").read_text(encoding="utf-8")

        self.assertIn("create extension if not exists vector", sql.lower())
        self.assertIn("lesson_06.support_documents", sql)
        self.assertIn("lesson_06.support_document_chunks", sql)
        self.assertIn("using gin", sql.lower())
        self.assertIn("using hnsw", sql.lower())
        for filename in ["vector_search.py", "keyword_search.py"]:
            source = (Path("examples/lesson-06") / filename).read_text(encoding="utf-8")
            self.assertIn("lesson_06.support_document", source, msg=filename)

        hybrid_source = Path("examples/lesson-06/hybrid_search.py").read_text(encoding="utf-8")
        self.assertIn("from keyword_search import keyword_search", hybrid_source)
        self.assertIn("from vector_search import vector_search", hybrid_source)

    def test_lesson_six_exposes_the_teaching_steps_directly(self) -> None:
        chunker = load_example("lesson-06/chunk_text.py")
        vector = load_example("lesson-06/vector_search.py")
        keyword = load_example("lesson-06/keyword_search.py")
        hybrid = load_example("lesson-06/hybrid_search.py")

        self.assertTrue(callable(chunker.chunk_text))
        self.assertTrue(callable(vector.vector_search))
        self.assertTrue(callable(keyword.keyword_search))
        self.assertTrue(callable(hybrid.hybrid_search))
        self.assertFalse(Path("examples/lesson-06/hybrid_policy_agent/__init__.py").exists())

        for filename in [
            "chunk_text.py",
            "vector_search.py",
            "keyword_search.py",
            "hybrid_search.py",
        ]:
            command = subprocess.run(
                [sys.executable, f"examples/lesson-06/{filename}", "--help"],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(command.returncode, 0, msg=f"{filename}: {command.stderr}")

    def test_retrieval_examples_default_to_local_postgres_socket(self) -> None:
        for path in [
            Path("examples/lesson-05/populate_database.py"),
            Path("examples/lesson-05/agentic_search.py"),
            Path("examples/lesson-06/populate_database.py"),
            Path("examples/lesson-06/vector_search.py"),
            Path("examples/lesson-06/keyword_search.py"),
            Path("examples/lesson-06/hybrid_search.py"),
        ]:
            source = path.read_text(encoding="utf-8")

            self.assertIn('DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"', source)
            self.assertNotIn("localhost:5433", source)

        self.assertFalse(Path("examples/lesson-05/compose.yaml").exists())
        self.assertFalse(Path("examples/lesson-06/compose.yaml").exists())
        environment_sample = Path("examples/.env.sample").read_text(encoding="utf-8")
        self.assertNotIn("\nRAG_DATABASE_URL=", environment_sample)

    def test_lesson_five_population_loads_the_canonical_policies(self) -> None:
        example = load_example("lesson-05/populate_database.py")

        documents = example.load_documents()

        self.assertEqual({document.id for document in documents}, EXPECTED_POLICY_IDS)
        self.assertTrue(
            all(document.summary.startswith("This policy covers") for document in documents)
        )
        self.assertTrue(any("five unused days" in document.body for document in documents))

    def test_lesson_six_population_chunks_the_canonical_policies(self) -> None:
        example = load_example("lesson-06/populate_database.py")

        documents = example.load_documents()
        chunks = example.create_chunks(documents)

        self.assertEqual({document.id for document in documents}, EXPECTED_POLICY_IDS)
        self.assertEqual(len({chunk.id for chunk in chunks}), len(chunks))
        self.assertGreaterEqual(len(chunks), len(documents) * 3)
        self.assertTrue(
            all(document.summary.startswith("This policy covers") for document in documents)
        )
        self.assertTrue(any("five unused days" in chunk.content for chunk in chunks))

    def test_chunk_text_is_a_pure_paragraph_split(self) -> None:
        example = load_example("lesson-06/chunk_text.py")

        chunks = example.chunk_text("# Policy\n\nFirst line.\nSecond line.\n\nFinal paragraph.")

        self.assertEqual(chunks, ["First line. Second line.", "Final paragraph."])

    def test_population_replaces_the_lesson_document_store(self) -> None:
        example = load_example("lesson-05/populate_database.py")
        document = example.load_documents()[0]
        connection_context = MagicMock()
        connection = connection_context.__enter__.return_value

        with patch.object(example.psycopg, "connect", return_value=connection_context):
            example.populate_database("postgresql://unused", [document])

        first_query = connection.execute.call_args_list[0].args[0]
        self.assertEqual(first_query, "delete from lesson_05.support_documents")

    def test_vector_examples_require_the_schema_embedding_size(self) -> None:
        vector = load_example("lesson-06/vector_search.py")

        literal = vector.vector_literal([0.0] * 768)

        self.assertTrue(literal.startswith("["))
        self.assertTrue(literal.endswith("]"))
        with self.assertRaises(ValueError):
            vector.vector_literal([0.0])

    def test_vector_search_embeds_the_question_and_returns_ranked_chunks(self) -> None:
        example = load_example("lesson-06/vector_search.py")
        connection_context = MagicMock()
        connection = connection_context.__enter__.return_value
        connection.execute.return_value.fetchall.return_value = [
            (
                "annual-leave-policy:003",
                "annual-leave-policy",
                "Annual Leave Policy",
                "Employees may carry up to five unused days.",
                0.91,
            )
        ]

        with (
            patch.object(example, "create_query_embedding", return_value=[0.0] * 768) as embed,
            patch.object(example.psycopg, "connect", return_value=connection_context),
        ):
            results = example.vector_search("unused holiday", "postgresql://unused", limit=3)

        embed.assert_called_once_with("unused holiday")
        self.assertEqual(results[0].chunk_id, "annual-leave-policy:003")
        self.assertEqual(results[0].similarity, 0.91)
        self.assertEqual(connection.execute.call_args.args[1][2], 3)

    def test_keyword_search_returns_postgres_ranked_chunks(self) -> None:
        example = load_example("lesson-06/keyword_search.py")
        connection_context = MagicMock()
        connection = connection_context.__enter__.return_value
        connection.execute.return_value.fetchall.return_value = [
            (
                "annual-leave-policy:003",
                "annual-leave-policy",
                "Annual Leave Policy",
                "Employees may carry up to five unused days.",
                0.42,
            )
        ]

        with patch.object(example.psycopg, "connect", return_value=connection_context):
            results = example.keyword_search("unused holiday", "postgresql://unused", limit=4)

        self.assertEqual(results[0].chunk_id, "annual-leave-policy:003")
        self.assertEqual(results[0].score, 0.42)
        self.assertEqual(
            connection.execute.call_args.args[1], ("unused holiday", "unused holiday", 4)
        )

    def test_hybrid_rag_fuses_keyword_and_vector_rankings(self) -> None:
        example = load_example("lesson-06/hybrid_search.py")

        scores = example.reciprocal_rank_fusion(
            [
                ["annual-leave-policy:001", "expenses-policy:001"],
                ["annual-leave-policy:001", "remote-working-policy:001"],
            ]
        )

        self.assertGreater(scores["annual-leave-policy:001"], scores["expenses-policy:001"])
        self.assertGreater(scores["annual-leave-policy:001"], scores["remote-working-policy:001"])

    def test_hybrid_search_composes_the_two_plain_search_functions(self) -> None:
        example = load_example("lesson-06/hybrid_search.py")
        shared = SimpleNamespace(
            chunk_id="annual-leave-policy:001",
            document_id="annual-leave-policy",
            title="Annual Leave Policy",
            content="Employees may carry unused leave forward.",
        )
        keyword_only = SimpleNamespace(
            chunk_id="expenses-policy:001",
            document_id="expenses-policy",
            title="Expenses Policy",
            content="Submit claims within 30 days.",
        )

        with (
            patch.object(example, "keyword_search", return_value=[shared, keyword_only]) as keyword,
            patch.object(example, "vector_search", return_value=[shared]) as vector,
        ):
            results = example.hybrid_search("unused holiday", "postgresql://unused", limit=2)

        keyword.assert_called_once_with("unused holiday", "postgresql://unused", 2)
        vector.assert_called_once_with("unused holiday", "postgresql://unused", 2)
        self.assertEqual(results[0].chunk_id, shared.chunk_id)

    def test_lesson_four_keeps_hand_built_and_adk_agents(self) -> None:
        hand_built = Path("examples/lesson-04/01_agent_by_hand.py")
        adk_package = Path("examples/lesson-04/adk_support_agent")
        source = (adk_package / "agent.py").read_text(encoding="utf-8")

        self.assertTrue(hand_built.is_file())
        self.assertTrue((adk_package / "__init__.py").is_file())
        self.assertIn("from google.adk.agents import Agent", source)
        self.assertIn('MODEL_NAME = os.getenv("SUPPORT_AGENT_MODEL", "gemini-3.5-flash")', source)
        self.assertIn("root_agent = Agent(", source)
        self.assertIn("tools=[list_support_documents, find_support_document]", source)

    def test_lesson_four_adk_fallback_does_not_promise_a_handoff(self) -> None:
        example = load_example("lesson-04/adk_support_agent/agent.py")

        result = example.find_support_document("Hello!")

        self.assertFalse(result["found"])
        self.assertEqual(result["reply"], example.UNSUPPORTED_REPLY)
        self.assertEqual(
            example.UNSUPPORTED_REPLY,
            "I can only answer questions covered by the available support policies.",
        )
        self.assertIn(
            f"reply exactly: {example.UNSUPPORTED_REPLY}",
            example.root_agent.instruction,
        )
        self.assertIn(
            "Do not claim that you can connect, transfer, escalate, contact, or notify anyone.",
            example.root_agent.instruction,
        )

    def test_slack_contract_contains_every_design_criterion(self) -> None:
        source = Path("docs/final-agent-spec.md").read_text(encoding="utf-8")

        for prefix, count in [("AC", 12), ("INV", 9)]:
            for number in range(1, count + 1):
                self.assertIn(f"`{prefix}-{number}`", source)

    def test_canonical_docs_use_the_slack_contract(self) -> None:
        paths = [
            Path("AGENTS.md"),
            Path("README.md"),
            Path("docs/course-code-map.md"),
            Path("docs/final-agent-spec.md"),
            Path("docs/resources/deploy-with-codex-prompt.md"),
        ]

        for path in paths:
            source = path.read_text(encoding="utf-8").lower()
            self.assertIn("slack", source, msg=str(path))
            self.assertNotIn("gmail", source, msg=str(path))
            self.assertNotIn("pub/sub", source, msg=str(path))

    def test_memory_has_required_sections_and_privacy_warning(self) -> None:
        source = Path("MEMORY.md").read_text(encoding="utf-8")

        for heading in [
            "## Decisions",
            "## Implementation Log",
            "## Manual Setup",
            "## Commands and Checks",
            "## Teaching Notes",
            "## Unresolved Questions",
        ]:
            self.assertIn(heading, source)

        self.assertIn("must never be recorded", source)

    def test_repository_boundary_is_documented(self) -> None:
        lesson_source = "/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/"

        for path in [Path("AGENTS.md"), Path("README.md"), Path("MEMORY.md")]:
            source = path.read_text(encoding="utf-8")

            self.assertIn(lesson_source, source, msg=str(path))
            self.assertIn("ai-engineer-curriculum", source, msg=str(path))

        memory = Path("MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("not a source of truth", memory)
        self.assertFalse(Path("docs/course-outline.md").exists())

    def test_development_deployment_seam_is_documented(self) -> None:
        for path in [Path("MEMORY.md"), Path("docs/final-agent-spec.md")]:
            source = path.read_text(encoding="utf-8")

            self.assertIn("HTTP handler", source, msg=str(path))
            self.assertIn("request_id", source, msg=str(path))
            self.assertIn("development Cloud Run", source, msg=str(path))
            self.assertIn("gcloud run services proxy", source, msg=str(path))
            self.assertIn("Cloud Tasks", source, msg=str(path))
            self.assertIn("OIDC", source, msg=str(path))

    def test_finished_app_uses_gemini_with_application_default_credentials(self) -> None:
        for path in [
            Path("AGENTS.md"),
            Path("README.md"),
            Path("MEMORY.md"),
            Path("docs/final-agent-spec.md"),
        ]:
            source = path.read_text(encoding="utf-8")

            self.assertIn("gemini-3.5-flash", source, msg=str(path))
            self.assertIn("Application Default Credentials", source, msg=str(path))
            self.assertIn("separate Gemini API key", source, msg=str(path))

    def test_model_cost_teaching_contract_is_documented(self) -> None:
        for path in [Path("MEMORY.md"), Path("docs/final-agent-spec.md")]:
            source = path.read_text(encoding="utf-8")

            self.assertIn("smallest model", source, msg=str(path))
            self.assertIn("input tokens", source, msg=str(path))
            self.assertIn("tool-call count", source, msg=str(path))
            self.assertIn("dated price configuration", source, msg=str(path))
            self.assertIn("cost per request", source, msg=str(path))


if __name__ == "__main__":
    unittest.main()
