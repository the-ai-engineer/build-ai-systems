"""Run the local policy workflow with synthetic fixtures.

uv run demo-workflow --fixture documented
"""

from __future__ import annotations

import argparse

from support_agent_app.application.domain import SupportQuestion
from support_agent_app.application.protocols import PolicyRepository
from support_agent_app.database.repositories.policy_repository import PostgresPolicyRepository
from support_agent_app.settings import WorkerSettings
from support_agent_app.testing.fake_model import FixtureName, fixture_model
from support_agent_app.testing.fixtures import (
    FIXTURE_NAMES,
    FIXTURE_QUESTIONS,
    POLICY_DIRECTORY,
    fixture_repository,
)
from support_agent_app.testing.memory_repository import DirectoryPolicyRepository
from support_agent_app.worker.agent.agent import DEFAULT_MODEL, run_support_workflow
from support_agent_app.worker.agent.pricing import estimate_run_cost, load_price_configuration


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local HR policy support workflow.")
    parser.add_argument("--fixture", choices=FIXTURE_NAMES, default="documented")
    parser.add_argument(
        "--question",
        default=None,
        help="Ask your own question instead of the fixture's. Needs --live-model to mean anything.",
    )
    parser.add_argument(
        "--live-model",
        action="store_true",
        help="Use the configured Google Cloud model instead of the deterministic fake.",
    )
    parser.add_argument(
        "--repository",
        choices=("files", "postgres"),
        default="files",
        help="Read policies from local fixtures or the Postgres support_documents table.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    fixture: FixtureName = args.fixture
    repository = _repository(args.repository, fixture)
    model = None if args.live_model else fixture_model(fixture)
    model_id = args.model if args.live_model else None

    question = SupportQuestion(text=args.question) if args.question else FIXTURE_QUESTIONS[fixture]
    if args.question and not args.live_model:
        print(
            "warning: the fixture model returns a canned decision and ignores your question.\n"
            "         add --live-model to actually ask it.\n"
        )

    print(f"question: {question.text}\n")
    outcome = run_support_workflow(
        question,
        repository,
        model=model,
        model_id=model_id,
    )
    _print_outcome(outcome)


def _repository(name: str, fixture: FixtureName) -> PolicyRepository:
    if name == "postgres":
        try:
            database_url = WorkerSettings.load().database_url
        except Exception as error:
            raise SystemExit("Set DATABASE_URL to use the Postgres policy repository.") from error
        return PostgresPolicyRepository(database_url)
    if fixture == "conflicting":
        return fixture_repository(fixture)
    return DirectoryPolicyRepository(POLICY_DIRECTORY)


def _print_outcome(outcome) -> None:
    result = outcome.result
    print(f"decision: {result.decision}")
    if result.decision == "answer":
        print(f"answer: {result.answer}")
        for source in result.sources:
            print(f"document_id: {source.document_id}")
            print(f"title: {source.title}")
            print(f"source: {source.source_filename}")
            print(f"revision: {source.document_revision}")
            print(f"excerpt: {source.supporting_excerpt}")
    else:
        print(f"reason_code: {result.reason_code}")
        print(f"reason: {result.reason}")

    run = outcome.run
    print(f"model: {run.model_id}")
    print(f"model_location: {run.model_location}")
    print(f"usage: input={run.input_tokens} output={run.output_tokens}")
    print(
        f"run: duration_ms={run.duration_ms} finish_reason={run.finish_reason} "
        f"tool_calls={run.tool_call_count} model_turns={run.model_turn_count}"
    )
    # How much of what you paid for was policy text the agent chose to load.
    # The rest is instructions, tool schemas, and the document index.
    share = (run.retrieved_context_tokens / run.input_tokens) if run.input_tokens else 0.0
    print(
        f"retrieved_context: {run.retrieved_context_tokens}/{run.input_tokens} "
        f"input tokens ({share:.0%}) were policy text"
    )
    print(f"estimated_cost_usd: {estimate_run_cost(run, load_price_configuration()):.8f}")


if __name__ == "__main__":
    main()
