"""Step 2: Populate the Lesson 05 document store with approved policies."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv


POLICY_DIR = Path(__file__).parents[2] / "policies"
DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"


@dataclass(frozen=True)
class SupportDocument:
    id: str
    title: str
    summary: str
    body: str
    content_hash: str


def load_documents() -> list[SupportDocument]:
    documents = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8").strip()
        documents.append(
            SupportDocument(
                id=path.stem,
                title=extract_title(body, path.stem),
                summary=extract_summary(body),
                body=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
            )
        )
    return documents


def populate_database(database_url: str, documents: list[SupportDocument]) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute("delete from lesson_05.support_documents")

        for document in documents:
            connection.execute(
                """
                insert into lesson_05.support_documents
                    (id, title, summary, body, content_hash)
                values (%s, %s, %s, %s, %s)
                """,
                (
                    document.id,
                    document.title,
                    document.summary,
                    document.body,
                    document.content_hash,
                ),
            )


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def extract_summary(markdown: str) -> str:
    for paragraph in re.split(r"\n\s*\n", markdown):
        if not paragraph.startswith("#"):
            return " ".join(paragraph.split())
    return "Approved company policy."


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    documents = load_documents()
    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    populate_database(database_url, documents)
    print(f"Loaded {len(documents)} complete documents into Postgres.")


if __name__ == "__main__":
    main()
