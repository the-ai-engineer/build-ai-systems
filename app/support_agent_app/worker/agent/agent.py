"""Google ADK agent construction and one bounded policy workflow run."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.adk.telemetry import ContentCapturingMode, TelemetryConfig
from google.genai import types
from pydantic import ValidationError

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
from .tools import WorkflowDependencies, build_adk_tools

DEFAULT_MODEL = "gemini-3.5-flash"
MAX_MODEL_TURNS = 6
MAX_TOOL_CALLS = 5
MODEL_TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_TOKENS = 500
MODEL_THINKING_LEVEL = types.ThinkingLevel.MINIMAL
APP_NAME = "support_agent"
PRIVATE_RUN_CONFIG = RunConfig(
    telemetry=TelemetryConfig(
        capture_message_content=ContentCapturingMode.NO_CONTENT,
    )
)


class AgentRunLimitError(RuntimeError):
    """The model exceeded a deterministic request or tool-call limit."""


class InvalidModelOutputError(RuntimeError):
    """ADK finished without a valid AgentDecision."""


@dataclass
class _RunCounters:
    model_turns: int = 0
    tool_calls: int = 0


def build_agent(
    model: BaseLlm | str,
    dependencies: WorkflowDependencies,
    *,
    counters: _RunCounters | None = None,
    model_timeout_seconds: float = MODEL_TIMEOUT_SECONDS,
) -> Agent:
    """Build one request-scoped ADK agent with deterministic limits."""

    if model_timeout_seconds <= 0:
        raise ValueError("model_timeout_seconds must be positive")
    run_counters = counters or _RunCounters()

    def before_model_callback(callback_context, llm_request):
        del callback_context, llm_request
        run_counters.model_turns += 1
        if run_counters.model_turns > MAX_MODEL_TURNS:
            raise AgentRunLimitError(f"A run may use at most {MAX_MODEL_TURNS} model turns")
        return None

    def before_tool_callback(tool, args, tool_context):
        del args, tool_context
        if tool.name == "set_model_response":
            return None
        run_counters.tool_calls += 1
        if run_counters.tool_calls > MAX_TOOL_CALLS:
            raise AgentRunLimitError(f"A run may call at most {MAX_TOOL_CALLS} tools")
        return None

    return Agent(
        name=APP_NAME,
        description="Answers employee questions from approved HR policy documents.",
        model=model,
        instruction=INSTRUCTIONS,
        tools=build_adk_tools(dependencies),
        output_schema=AgentDecision,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_level=MODEL_THINKING_LEVEL,
            ),
        ),
        before_model_callback=before_model_callback,
        before_tool_callback=before_tool_callback,
        timeout=model_timeout_seconds,
    )


def run_support_workflow(
    question: SupportQuestion,
    repository: PolicyRepository,
    *,
    model: BaseLlm | str | None = None,
    model_id: str | None = None,
    context_token_counter: Callable[[str], int] | None = None,
    model_timeout_seconds: float = MODEL_TIMEOUT_SECONDS,
) -> WorkflowOutcome:
    """Run ADK once and turn its untrusted result into an application outcome."""

    dependencies = WorkflowDependencies(repository=repository)
    selection = _resolve_model(model, model_id)
    counters = _RunCounters()
    agent = build_agent(
        selection.model,
        dependencies,
        counters=counters,
        model_timeout_seconds=model_timeout_seconds,
    )
    started = perf_counter()
    events = asyncio.run(
        asyncio.wait_for(
            _run_agent(agent, question.text),
            timeout=model_timeout_seconds,
        )
    )
    duration_ms = max(0, round((perf_counter() - started) * 1_000))

    decision = verify_decision(_read_decision(events), dependencies.loaded_documents)
    input_tokens, output_tokens = _token_usage(events)
    count_context_tokens = context_token_counter or estimate_context_tokens
    run = AgentRunRecord(
        model_id=selection.model_id,
        model_location=selection.location,
        service_tier=selection.service_tier,
        selected_documents=tuple(
            LoadedDocumentRecord(document_id=document.document_id, revision=document.revision)
            for document in dependencies.loaded_documents.values()
        ),
        input_tokens=input_tokens,
        retrieved_context_tokens=sum(
            count_context_tokens(document.body)
            for document in dependencies.loaded_documents.values()
        ),
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        finish_reason=_finish_reason(events),
        tool_call_count=counters.tool_calls,
        model_turn_count=counters.model_turns,
    )
    return WorkflowOutcome(result=decision, run=run)


async def _run_agent(agent: Agent, question: str) -> list[Event]:
    session_id = str(uuid4())
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id="worker",
        session_id=session_id,
    )
    events: list[Event] = []
    try:
        async for event in runner.run_async(
            user_id="worker",
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=question)],
            ),
            run_config=PRIVATE_RUN_CONFIG,
        ):
            events.append(event)
    finally:
        await runner.close()
    return events


def _read_decision(events: list[Event]) -> AgentDecision:
    for event in reversed(events):
        structured = getattr(event.actions, "set_model_response", None)
        if structured is not None:
            try:
                return AgentDecision.model_validate(structured)
            except ValidationError as error:
                raise InvalidModelOutputError("ADK returned an invalid decision") from error

    final_text = _final_text(events)
    try:
        return AgentDecision.model_validate_json(final_text)
    except (ValidationError, ValueError) as error:
        raise InvalidModelOutputError("ADK did not return a valid decision") from error


def _final_text(events: list[Event]) -> str:
    for event in reversed(events):
        if not event.is_final_response() or event.content is None:
            continue
        text = "".join(part.text or "" for part in event.content.parts or [])
        if text:
            return text
    return ""


def _token_usage(events: list[Event]) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for event in events:
        usage = event.usage_metadata
        if usage is None:
            continue
        input_tokens += usage.prompt_token_count or 0
        output_tokens += usage.candidates_token_count or 0
    return input_tokens, output_tokens


def _finish_reason(events: list[Event]) -> str:
    for event in reversed(events):
        if event.finish_reason is not None:
            return event.finish_reason.value.lower()
    return "unknown"


def estimate_context_tokens(text: str) -> int:
    """Return a visible local estimate when a provider tokenizer is unavailable."""

    return (len(text.encode("utf-8")) + 3) // 4


def _resolve_model(model: BaseLlm | str | None, model_id: str | None) -> ModelSelection:
    """Pick the ADK model to run, and describe it for the run record."""

    if model is None:
        from ..model_provider import create_google_cloud_model

        return create_google_cloud_model(model_id)

    actual_id = model if isinstance(model, str) else model.model
    if model_id is not None and model_id != actual_id:
        raise ValueError(f"Injected model ID {actual_id!r} does not match model_id {model_id!r}")
    if actual_id == "fixture":
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
