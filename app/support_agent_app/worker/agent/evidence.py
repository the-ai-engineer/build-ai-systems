"""Deterministic verification that stands between the model and any side effect.

Nothing here calls a model. Every rule is checkable by reading the code, which
is the point: an answer survives only if its citations match documents the run
actually loaded.
"""

from __future__ import annotations

from ...application.domain import (
    AnswerDecision,
    HumanReviewDecision,
    SupportDocument,
)
from .schemas import AgentDecision


def verify_decision(
    decision: AgentDecision,
    loaded_documents: dict[str, SupportDocument],
) -> AnswerDecision | HumanReviewDecision:
    if decision.decision == "human_review":
        return HumanReviewDecision(
            reason=decision.reason,
            reason_code=decision.reason_code or "unsupported",
        )

    if not loaded_documents or not _sources_are_valid(decision, loaded_documents):
        return HumanReviewDecision(
            reason="The proposed answer did not contain verifiable policy evidence.",
            reason_code="invalid_evidence",
        )

    if decision.answer is None:
        # Unreachable: AgentDecision's validator rejects an answer decision with
        # no answer. Stated rather than papered over with `or ""`, which would
        # turn a logic error into a confusing schema error further downstream.
        raise ValueError("an answer decision must carry an answer")

    return AnswerDecision(
        answer=decision.answer,
        reason=decision.reason,
        sources=tuple(decision.sources),
    )


def _sources_are_valid(
    decision: AgentDecision,
    loaded_documents: dict[str, SupportDocument],
) -> bool:
    for source in decision.sources:
        # Only documents the run actually loaded count as evidence. A citation
        # of anything else is the model inventing a source.
        document = loaded_documents.get(source.document_id)
        if document is None:
            return False
        if source.title != document.title:
            return False
        if source.source_filename != document.source_filename:
            return False
        if source.document_revision != document.revision:
            return False
        if not source.supporting_excerpt.strip():
            return False
        # Exact substring on purpose. See ARCHITECTURE.md for what this costs in
        # answers refused when a model re-wraps or re-punctuates its excerpt.
        if source.supporting_excerpt not in document.body:
            return False
    return True
