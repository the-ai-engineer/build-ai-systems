"""Run the local policy workflow with synthetic fixtures."""

from __future__ import annotations

import argparse
import os

from .fake_model import FixtureName, fixture_model
from .fixtures import FIXTURE_QUESTIONS, POLICY_DIRECTORY, fixture_repository
from .pricing import estimate_run_cost, load_price_configuration
from .repositories import DirectoryPolicyRepository, PostgresPolicyRepository
from .workflow import DEFAULT_MODEL, run_support_workflow


FIXTURE_NAMES = tuple(FIXTURE_QUESTIONS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local HR policy support workflow.")
    parser.add_argument("--fixture", choices=FIXTURE_NAMES, default="documented")
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
    parser.add_argument("--model", default=os.getenv("SUPPORT_AGENT_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    fixture: FixtureName = args.fixture
    repository = _repository(args.repository, fixture)
    model = None if args.live_model else fixture_model(fixture)
    model_id = args.model if args.live_model else None

    outcome = run_support_workflow(
        FIXTURE_QUESTIONS[fixture],
        repository,
        model=model,
        model_id=model_id,
    )
    _print_outcome(outcome)


def _repository(name: str, fixture: FixtureName):
    if name == "postgres":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise SystemExit("Set DATABASE_URL to use the Postgres policy repository.")
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
    print(f"estimated_cost_usd: {estimate_run_cost(run, load_price_configuration()):.8f}")


if __name__ == "__main__":
    main()
