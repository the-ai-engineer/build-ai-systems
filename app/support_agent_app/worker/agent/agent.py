"""Agent construction and one constrained run, with usage limits enforced."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import perf_counter

from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from ...application.domain import (
    AgentRunRecord,
    LoadedDocumentRecord,
    SupportQuestion,
    WorkflowOutcome,
)
from ...application.protocols import PolicyRepository
from ..model_provider import ModelSelection
from .evidence import verify_decision
from .prompts import INSTRUCTIONS
from .schemas import AgentDecision
from .tools import WorkflowDependencies, get_support_document, list_support_documents

DEFAULT_MODEL = "google-cloud:gemini-3.5-flash"
MAX_MODEL_TURNS = 6
MAX_TOOL_CALLS = 5
MODEL_TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_TOKENS = 500


def build_agent(
    model: Model | str,
    *,
    model_timeout_seconds: float = MODEL_TIMEOUT_SECONDS,
    provider_settings: dict[str, object] | None = None,
) -> Agent[WorkflowDependencies, AgentDecision]:
    """Build the agent with limits that hold for any model.

    Provider-specific settings arrive from `model_provider`, so this function
    never names a vendor. Passing them for a model that does not understand
    them would be meaningless, so a fake model simply gets none.
    """

    if model_timeout_seconds <= 0:
        raise ValueError("model_timeout_seconds must be positive")
    settings: dict[str, object] = {
        # Per request. See run_support_workflow for the second, total budget.
        "timeout": min(MODEL_TIMEOUT_SECONDS, model_timeout_seconds),
        "max_tokens": MAX_OUTPUT_TOKENS,
        "parallel_tool_calls": False,
    }
    settings.update(provider_settings or {})
    return Agent(
        model,
        deps_type=WorkflowDependencies,
        output_type=AgentDecision,
        instructions=INSTRUCTIONS,
        tools=[
            Tool(list_support_documents, sequential=True),
            Tool(get_support_document, sequential=True),
        ],
        model_settings=settings,  # type: ignore[arg-type]
        retries=1,
    )


def run_support_workflow(
    question: SupportQuestion,
    repository: PolicyRepository,
    *,
    model: Model | str | None = None,
    model_id: str | None = None,
    context_token_counter: Callable[[str], int] | None = None,
    model_timeout_seconds: float = MODEL_TIMEOUT_SECONDS,
) -> WorkflowOutcome:
    dependencies = WorkflowDependencies(repository=repository)
    selection = _resolve_model(model, model_id)
    started = perf_counter()
    agent = build_agent(
        selection.model,
        model_timeout_seconds=model_timeout_seconds,
        provider_settings=selection.provider_settings,
    )
    # Two budgets, deliberately. `model_settings["timeout"]` bounds one request;
    # this `wait_for` bounds the whole run. Without it, six turns at a 20 second
    # per-request timeout can legitimately take two minutes and blow the worker
    # deadline. `agent.run_sync()` would collapse this back to one budget.
    result = asyncio.run(
        asyncio.wait_for(
            agent.run(
                question.text,
                deps=dependencies,
                usage_limits=UsageLimits(
                    request_limit=MAX_MODEL_TURNS,
                    tool_calls_limit=MAX_TOOL_CALLS,
                    output_tokens_limit=MAX_OUTPUT_TOKENS * MAX_MODEL_TURNS,
                ),
            ),
            timeout=model_timeout_seconds,
        )
    )
    duration_ms = max(0, round((perf_counter() - started) * 1_000))

    decision = verify_decision(result.output, dependencies.loaded_documents)
    model_responses = [
        message for message in result.all_messages() if isinstance(message, ModelResponse)
    ]
    finish_reason = model_responses[-1].finish_reason or "unknown"
    usage = result.usage
    count_context_tokens = context_token_counter or estimate_context_tokens
    run = AgentRunRecord(
        model_id=selection.model_id,
        model_location=selection.location,
        service_tier=selection.service_tier,
        selected_documents=tuple(
            LoadedDocumentRecord(document_id=document.document_id, revision=document.revision)
            for document in dependencies.loaded_documents.values()
        ),
        input_tokens=usage.input_tokens,
        retrieved_context_tokens=sum(
            count_context_tokens(document.body)
            for document in dependencies.loaded_documents.values()
        ),
        output_tokens=usage.output_tokens,
        duration_ms=duration_ms,
        finish_reason=finish_reason,
        tool_call_count=usage.tool_calls,
        model_turn_count=usage.requests,
    )
    return WorkflowOutcome(result=decision, run=run)


def estimate_context_tokens(text: str) -> int:
    """Return a visible local estimate when a provider tokenizer is unavailable."""

    return (len(text.encode("utf-8")) + 3) // 4


def _resolve_model(model: Model | str | None, model_id: str | None) -> ModelSelection:
    """Pick the model to run, and describe it for the run record."""

    if model is None:
        from ..model_provider import create_google_cloud_model

        return create_google_cloud_model(model_id)

    actual_id = model if isinstance(model, str) else model.model_id
    if model_id is not None and model_id != actual_id:
        raise ValueError(f"Injected model ID {actual_id!r} does not match model_id {model_id!r}")
    if isinstance(model, Model) and model.system == "function":
        # A scripted model. No provider settings, because there is no provider.
        return ModelSelection(
            model=model,
            model_id=actual_id,
            location="local",
            service_tier="deterministic-test",
        )
    return ModelSelection(
        model=model,
        model_id=actual_id,
        location="unknown",
        service_tier="unknown",
    )
