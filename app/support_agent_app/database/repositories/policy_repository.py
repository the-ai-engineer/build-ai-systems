"""Postgres policy retrieval and the Markdown loader that seeds it.

`PolicyRepository` itself is owned by `application/protocols.py`. Deterministic
in-memory and directory-backed repositories live in `testing/`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from psycopg.rows import dict_row

from ...application.domain import SupportDocument, SupportDocumentIndexItem
from ..connection import connect_with_timeout

DEFAULT_POLICY_DIRECTORY = Path(__file__).parents[4] / "policies"


class PostgresPolicyRepository:
    """Retrieve only active documents with fixed, parameterized SQL."""

    def __init__(
        self,
        database_url: str,
        *,
        timeout_provider: Callable[[], float] | None = None,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._timeout_provider = timeout_provider

    def _connect(self):
        timeout_seconds = None if self._timeout_provider is None else self._timeout_provider()
        return connect_with_timeout(
            self._database_url,
            row_factory=dict_row,
            timeout_seconds=timeout_seconds,
        )

    def with_timeout_provider(
        self,
        timeout_provider: Callable[[], float],
    ) -> PostgresPolicyRepository:
        return PostgresPolicyRepository(
            self._database_url,
            timeout_provider=timeout_provider,
        )

    def list_active_documents(self) -> list[SupportDocumentIndexItem]:
        with self._connect() as connection:
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
        with self._connect() as connection:
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
    # Same reason as the migrations directory: seeding nothing is a failure to
    # find the policies, not an approved policy set of size zero.
    if not policy_directory.is_dir():
        raise FileNotFoundError(f"no policy directory at {policy_directory}")

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
