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

    return AnswerDecision(
        answer=decision.answer or "",
        reason=decision.reason,
        sources=tuple(decision.sources),
    )


def _sources_are_valid(
    decision: AgentDecision,
    loaded_documents: dict[str, SupportDocument],
) -> bool:
    for source in decision.sources:
        document = loaded_documents.get(source.document_id)
        if document is None or not document.is_active:
            return False
        if source.title != document.title:
            return False
        if source.source_filename != document.source_filename:
            return False
        if source.document_revision != document.revision:
            return False
        if not source.supporting_excerpt.strip():
            return False
        if source.supporting_excerpt not in document.body:
            return False
    return True
