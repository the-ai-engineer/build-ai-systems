"""Populate PostgreSQL with policy chunks and their embeddings."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from google import genai
from google.genai import types

from chunk_text import chunk_text


POLICY_DIR = Path(__file__).parents[2] / "policies"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"

@dataclass(frozen=True)
class SupportDocument:
    id: str
    title: str
    summary: str
    body: str
    content_hash: str


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    index: int
    content: str


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


def create_chunks(documents: list[SupportDocument]) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            id=f"{document.id}:{index:03d}",
            document_id=document.id,
            index=index,
            content=content,
        )
        for document in documents
        for index, content in enumerate(chunk_text(document.body))
    ]


def create_embeddings(texts: list[str]) -> list[list[float]]:
    project = required_environment("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    client = genai.Client(vertexai=True, project=project, location=location)
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    embeddings = [embedding.values or [] for embedding in response.embeddings or []]
    if len(embeddings) != len(texts):
        raise RuntimeError("Gemini returned a different number of embeddings than requested.")
    return embeddings


def populate_database(
    database_url: str,
    documents: list[SupportDocument],
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("Every chunk must have one embedding.")

    with psycopg.connect(database_url) as connection:
        connection.execute("delete from lesson_06.support_documents")

        for document in documents:
            connection.execute(
                """
                insert into lesson_06.support_documents
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
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            connection.execute(
                """
                insert into lesson_06.support_document_chunks
                    (id, document_id, chunk_index, content, embedding_model, embedding)
                values (%s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.index,
                    chunk.content,
                    EMBEDDING_MODEL,
                    vector_literal(embedding),
                ),
            )


def vector_literal(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding values.")
    return "[" + ",".join(str(value) for value in values) + "]"


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


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} in examples/.env before running this command.")
    return value


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    documents = load_documents()
    chunks = create_chunks(documents)
    titles = {document.id: document.title for document in documents}
    embedding_texts = [
        f"{titles[chunk.document_id]}\n{chunk.content}"
        for chunk in chunks
    ]
    embeddings = create_embeddings(embedding_texts)
    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    populate_database(database_url, documents, chunks, embeddings)
    print(f"Populated Postgres with {len(documents)} documents and {len(chunks)} chunks.")


if __name__ == "__main__":
    main()
