from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType


def load_example(filename: str) -> ModuleType:
    path = Path("examples") / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LessonExamplesTest(unittest.TestCase):
    def test_repository_contract_exists(self) -> None:
        for path in [
            Path("brief.md"),
            Path("MEMORY.md"),
            Path("docs/course-code-map.md"),
            Path("docs/final-agent-spec.md"),
            Path("docs/resources/deploy-with-codex-prompt.md"),
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

        self.assertEqual(len(policy_paths), 3)

    def test_whole_document_rag_exposes_an_index_and_read_tool(self) -> None:
        example = load_example("lesson-05/01_file_rag.py")

        index = example.list_policy_documents()
        document = example.read_policy_document("annual-leave-policy")

        self.assertEqual(len(index), 3)
        self.assertTrue(document["found"])
        self.assertIn("five unused days", document["body"])

    def test_sql_rag_retrieves_an_exact_structured_fact(self) -> None:
        example = load_example("lesson-05/02_sql_rag.py")

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
        example = load_example("lesson-05/03_vector_rag.py")

        self.assertAlmostEqual(example.cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(example.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_hybrid_rag_fuses_keyword_and_vector_rankings(self) -> None:
        example = load_example("lesson-05/04_hybrid_rag.py")

        scores = example.reciprocal_rank_fusion(
            [
                ["annual-leave-policy", "expenses-policy"],
                ["annual-leave-policy", "remote-working-policy"],
            ]
        )

        self.assertGreater(scores["annual-leave-policy"], scores["expenses-policy"])
        self.assertGreater(scores["annual-leave-policy"], scores["remote-working-policy"])

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
