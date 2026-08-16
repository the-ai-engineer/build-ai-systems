"""The only two capabilities the model is given, and the limits on them."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import RunContext

from ..application.domain import SupportDocument, SupportDocumentIndexItem
from ..application.protocols import PolicyRepository

MAX_LOADED_DOCUMENTS = 3


@dataclass
class WorkflowDependencies:
    repository: PolicyRepository
    loaded_documents: dict[str, SupportDocument] = field(default_factory=dict)


def list_support_documents(
    context: RunContext[WorkflowDependencies],
) -> list[SupportDocumentIndexItem]:
    """List the active policy index without exposing arbitrary database access."""
    return context.deps.repository.list_active_documents()


def get_support_document(
    context: RunContext[WorkflowDependencies],
    document_id: str,
) -> SupportDocument:
    """Load one active policy, up to the per-run document limit."""
    existing = context.deps.loaded_documents.get(document_id)
    if existing is not None:
        return existing
    if len(context.deps.loaded_documents) >= MAX_LOADED_DOCUMENTS:
        raise ValueError(f"A run may load at most {MAX_LOADED_DOCUMENTS} documents")

    document = context.deps.repository.get_active_document(document_id)
    if document is None:
        raise ValueError("The requested active support document does not exist")
    context.deps.loaded_documents[document_id] = document
    return document
