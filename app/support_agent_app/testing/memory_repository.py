"""Deterministic policy repositories for local runs, demos, and tests.

These are not part of any production composition. `worker/main.py` only builds
them when local fixture mode is explicitly requested.
"""

from __future__ import annotations

from pathlib import Path

from ..application.domain import SupportDocument, SupportDocumentIndexItem
from ..database.repositories.policy_repository import load_policy_directory


class MemoryPolicyRepository:
    """Small deterministic repository used by local fixtures and tests."""

    def __init__(self, documents: list[SupportDocument]) -> None:
        self._documents = {document.document_id: document for document in documents}

    def list_active_documents(self) -> list[SupportDocumentIndexItem]:
        return [
            document.index_item()
            for document in sorted(self._documents.values(), key=lambda item: item.document_id)
            if document.is_active
        ]

    def get_active_document(self, document_id: str) -> SupportDocument | None:
        document = self._documents.get(document_id)
        if document is None or not document.is_active:
            return None
        return document


class DirectoryPolicyRepository(MemoryPolicyRepository):
    """Load the synthetic local policy set from Markdown files."""

    def __init__(self, policy_directory: Path) -> None:
        super().__init__(load_policy_directory(policy_directory))
