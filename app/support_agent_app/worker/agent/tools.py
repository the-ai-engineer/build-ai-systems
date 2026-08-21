"""The only two capabilities the model is given, and the limits on them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...application.domain import SupportDocument, SupportDocumentIndexItem
from ...application.protocols import PolicyRepository

MAX_LOADED_DOCUMENTS = 3


@dataclass
class WorkflowDependencies:
    repository: PolicyRepository
    loaded_documents: dict[str, SupportDocument] = field(default_factory=dict)


def list_support_documents(
    dependencies: WorkflowDependencies,
) -> list[SupportDocumentIndexItem]:
    """List the active policy index without exposing arbitrary database access."""
    return dependencies.repository.list_active_documents()


def get_support_document(
    dependencies: WorkflowDependencies,
    document_id: str,
) -> SupportDocument:
    """Load one active policy, up to the per-run document limit."""
    existing = dependencies.loaded_documents.get(document_id)
    if existing is not None:
        return existing
    if len(dependencies.loaded_documents) >= MAX_LOADED_DOCUMENTS:
        raise ValueError(f"A run may load at most {MAX_LOADED_DOCUMENTS} documents")

    document = dependencies.repository.get_active_document(document_id)
    if document is None:
        raise ValueError("The requested active support document does not exist")
    dependencies.loaded_documents[document_id] = document
    return document


def build_adk_tools(dependencies: WorkflowDependencies) -> list[Callable[..., object]]:
    """Bind the request-scoped repository to the two ADK function tools."""

    def list_support_documents_tool() -> list[dict[str, object]]:
        """List the active policy index before choosing policy evidence."""
        return [item.model_dump(mode="json") for item in list_support_documents(dependencies)]

    def get_support_document_tool(document_id: str) -> dict[str, object]:
        """Load one active policy document by its exact identifier."""
        try:
            document = get_support_document(dependencies, document_id)
        except ValueError as error:
            return {"error": str(error)}
        return document.model_dump(mode="json")

    list_support_documents_tool.__name__ = "list_support_documents"
    get_support_document_tool.__name__ = "get_support_document"
    return [list_support_documents_tool, get_support_document_tool]
