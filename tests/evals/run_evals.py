"""Run the shared product cases against the real policy workflow.

Run one inexpensive case while learning:

    uv run python -m tests.evals.run_evals --case hotel_limit

Omit ``--case`` to run the complete set. The command prints identifiers and
safe run metadata, never questions, answers, or policy text.
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from support_agent_app.application.domain import SupportQuestion, WorkflowOutcome
from support_agent_app.testing.fixtures import POLICY_DIRECTORY
from support_agent_app.testing.memory_repository import DirectoryPolicyRepository
from support_agent_app.worker.agent.agent import (
    DEFAULT_MODEL,
    MAX_MODEL_TURNS,
    MAX_TOOL_CALLS,
    run_support_workflow,
)
from support_agent_app.worker.agent.pricing import estimate_run_cost, load_price_configuration

from tests.evals.cases import EVAL_CASES, SupportEvalCase


def evaluate_outcome(
    case: SupportEvalCase,
    outcome: WorkflowOutcome,
    *,
    policy_directory: Path = POLICY_DIRECTORY,
) -> tuple[str, ...]:
    """Return concrete reasons the outcome failed its product expectations."""

    failures: list[str] = []
    result = outcome.result
    actual_sources = frozenset(source.source_filename for source in result.sources)

    if result.decision != case.expected_decision:
        failures.append(f"expected decision {case.expected_decision}, got {result.decision}")

    missing_sources = case.expected_sources - actual_sources
    if missing_sources:
        failures.append(f"missing sources: {', '.join(sorted(missing_sources))}")

    if result.decision == "human_review":
        if result.answer is not None:
            failures.append("human_review included an answer")
        if result.sources:
            failures.append("human_review included sources")
    else:
        for source in result.sources:
            source_path = policy_directory / source.source_filename
            if not source_path.is_file():
                failures.append(
                    f"source is not in the approved policy set: {source.source_filename}"
                )
                continue
            body = source_path.read_text(encoding="utf-8")
            if source.supporting_excerpt not in body:
                failures.append(f"excerpt is not verbatim in {source.source_filename}")

    visible_result_text = "\n".join(
        text for text in (result.answer, result.reason) if text is not None
    ).casefold()
    for index, forbidden in enumerate(case.forbidden_text):
        if forbidden.casefold() in visible_result_text:
            failures.append(f"forbidden_text[{index}] found in result")

    if outcome.run.model_turn_count > MAX_MODEL_TURNS:
        failures.append(
            f"used {outcome.run.model_turn_count} model turns; limit is {MAX_MODEL_TURNS}"
        )
    if outcome.run.tool_call_count > MAX_TOOL_CALLS:
        failures.append(f"used {outcome.run.tool_call_count} tool calls; limit is {MAX_TOOL_CALLS}")

    return tuple(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live HR policy assistant evals.")
    parser.add_argument(
        "--case",
        choices=tuple(case.id for case in EVAL_CASES),
        help="Run one named case. Omit this option to run every case.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to evaluate. Default: {DEFAULT_MODEL}",
    )
    return parser.parse_args()


def _estimate_cost(outcome: WorkflowOutcome) -> Decimal | None:
    try:
        return estimate_run_cost(outcome.run, load_price_configuration())
    except ValueError:
        return None


def _require_google_cloud_settings() -> None:
    missing = tuple(
        name for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION") if not os.getenv(name)
    )
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} before running live evals.")


def main() -> int:
    args = _parse_args()
    _require_google_cloud_settings()

    selected_cases = tuple(case for case in EVAL_CASES if args.case is None or case.id == args.case)
    repository = DirectoryPolicyRepository(POLICY_DIRECTORY)
    category_results: dict[str, list[bool]] = defaultdict(list)
    passed_count = 0
    must_pass_failures: list[str] = []
    total_cost = Decimal(0)
    cost_is_complete = True

    print(f"model: {args.model}")
    print(f"cases: {len(selected_cases)}\n")

    for case in selected_cases:
        outcome = run_support_workflow(
            SupportQuestion(text=case.question),
            repository,
            model_id=args.model,
            model_timeout_seconds=60.0,
        )
        failures = evaluate_outcome(case, outcome)
        passed = not failures
        passed_count += int(passed)
        category_results[case.category].append(passed)
        if case.must_pass and not passed:
            must_pass_failures.append(case.id)

        cost = _estimate_cost(outcome)
        if cost is None:
            cost_is_complete = False
        else:
            total_cost += cost

        result = outcome.result
        actual_sources = sorted(source.source_filename for source in result.sources)
        status = "PASS" if passed else "FAIL"
        must_pass_label = " must-pass" if case.must_pass else ""
        cost_label = f"${cost:.6f}" if cost is not None else "n/a"
        print(
            f"{status} {case.id} [{case.category}{must_pass_label}] "
            f"decision={result.decision} sources={actual_sources} "
            f"turns={outcome.run.model_turn_count} tools={outcome.run.tool_call_count} "
            f"tokens={outcome.run.input_tokens + outcome.run.output_tokens} "
            f"duration_ms={outcome.run.duration_ms} cost={cost_label}"
        )
        for failure in failures:
            print(f"  - {failure}")

    print(f"\nresult: {passed_count}/{len(selected_cases)} passed")
    for category, results in sorted(category_results.items()):
        print(f"{category}: {sum(results)}/{len(results)} passed")
    if must_pass_failures:
        print(f"must-pass failures: {', '.join(must_pass_failures)}")
    else:
        print("must-pass failures: none")
    print(
        f"estimated total cost: ${total_cost:.6f}"
        if cost_is_complete
        else "estimated total cost: n/a"
    )

    return 0 if passed_count == len(selected_cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
