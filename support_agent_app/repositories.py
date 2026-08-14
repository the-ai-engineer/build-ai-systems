"""Read-only policy repository adapters."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol

from .domain import SupportDocument, SupportDocumentIndexItem


class PolicyRepository(Protocol):
    """The complete knowledge capability exposed to the workflow."""

    def list_active_documents(self) -> list[SupportDocumentIndexItem]: ...

    def get_active_document(self, document_id: str) -> SupportDocument | None: ...


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


class PostgresPolicyRepository:
    """Retrieve only active documents with fixed, parameterized SQL."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url

    def list_active_documents(self) -> list[SupportDocumentIndexItem]:
        from psycopg import connect
        from psycopg.rows import dict_row

        with connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                """
                select id, title, category, summary, keywords, source_file, revision
                from support_documents
                where is_active = true
                order by id
                """
            ).fetchall()
        return [
            SupportDocumentIndexItem(
                document_id=row["id"],
                title=row["title"],
                category=row["category"],
                summary=row["summary"],
                keywords=tuple(row["keywords"]),
                source_filename=row["source_file"],
                revision=row["revision"],
            )
            for row in rows
        ]

    def get_active_document(self, document_id: str) -> SupportDocument | None:
        from psycopg import connect
        from psycopg.rows import dict_row

        with connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                select id, title, category, summary, keywords, source_file,
                       revision, body, is_active
                from support_documents
                where id = %s and is_active = true
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return SupportDocument(
            document_id=row["id"],
            title=row["title"],
            category=row["category"],
            summary=row["summary"],
            keywords=tuple(row["keywords"]),
            source_filename=row["source_file"],
            revision=row["revision"],
            body=row["body"],
            is_active=row["is_active"],
        )


def load_policy_directory(policy_directory: Path) -> list[SupportDocument]:
    documents = []
    for path in sorted(policy_directory.glob("*.md")):
        body = path.read_text(encoding="utf-8").strip()
        document_id = path.stem
        documents.append(
            SupportDocument(
                document_id=document_id,
                title=_title(body, document_id),
                category=document_id.removesuffix("-policy").replace("-", "_"),
                summary=_summary(body),
                keywords=tuple(document_id.split("-")),
                source_filename=path.name,
                revision=revision_for(body),
                body=body,
            )
        )
    return documents


def revision_for(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback.replace("-", " ").title()


def _summary(body: str) -> str:
    paragraphs = re.split(r"\n\s*\n", body)
    for paragraph in paragraphs:
        if not paragraph.startswith("#"):
            return " ".join(paragraph.split())
    return "Approved company policy."
