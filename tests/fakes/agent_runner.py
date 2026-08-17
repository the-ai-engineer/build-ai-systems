"""A stand-in for the agent, for tests that are not about the agent.

The worker's lifecycle tests are about claims, leases, retries, and duplicate
delivery. None of that involves a model, so none of it should invoke one. This
returns a fixed decision so those tests stay fast, free, offline, and honest
about what they cover.

It is not a fake model. It does not simulate tool calls or fabricate an answer
the way a scripted model would. It simply is not an agent.
"""

from __future__ import annotations

from support_agent_app.application.domain import (
    AgentRunRecord,
    AnswerDecision,
    HumanReviewDecision,
    SourceCitation,
    SupportDecision,
    WorkflowOutcome,
)


def run_record(**overrides) -> AgentRunRecord:
    values = {
        "model_id": "stub:none",
        "model_location": "local",
        "service_tier": "deterministic-test",
        "selected_documents": (),
        "input_tokens": 0,
        "retrieved_context_tokens": 0,
        "output_tokens": 0,
        "duration_ms": 1,
        "finish_reason": "stop",
        "tool_call_count": 0,
        "model_turn_count": 1,
    }
    values.update(overrides)
    return AgentRunRecord(**values)


def human_review_outcome(reason_code: str = "unsupported") -> WorkflowOutcome:
    return WorkflowOutcome(
        result=HumanReviewDecision(
            reason="A synthetic decision from the stub agent runner.",
            reason_code=reason_code,  # type: ignore[arg-type]
        ),
        run=run_record(),
    )


def answer_outcome(
    answer: str = "A synthetic answer from the stub agent runner.",
    source_filename: str = "annual-leave-policy.md",
) -> WorkflowOutcome:
    return WorkflowOutcome(
        result=AnswerDecision(
            answer=answer,
            reason="A synthetic decision from the stub agent runner.",
            sources=(
                SourceCitation(
                    document_id=source_filename.removesuffix(".md"),
                    title="Annual Leave Policy",
                    source_filename=source_filename,
                    document_revision="sha256:synthetic",
                    supporting_excerpt="A synthetic verified excerpt.",
                ),
            ),
        ),
        run=run_record(),
    )


class StubAgentRunner:
    """Return a fixed outcome and record how it was called."""

    def __init__(self, outcome: WorkflowOutcome | None = None) -> None:
        self.outcome = outcome or answer_outcome()
        self.calls = 0
        self.questions: list[str] = []
        self.model_timeouts: list[float] = []

    def __call__(
        self,
        question,
        repository,
        *,
        model=None,
        model_timeout_seconds: float = 20.0,
        **_: object,
    ) -> WorkflowOutcome:
        self.calls += 1
        self.questions.append(question.text)
        self.model_timeouts.append(model_timeout_seconds)
        return self.outcome


class FailingAgentRunner:
    """Raise a chosen error, for failure-classification tests."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def __call__(self, *_: object, **__: object) -> WorkflowOutcome:
        self.calls += 1
        raise self.error


__all__ = [
    "FailingAgentRunner",
    "StubAgentRunner",
    "SupportDecision",
    "answer_outcome",
    "human_review_outcome",
    "run_record",
]
