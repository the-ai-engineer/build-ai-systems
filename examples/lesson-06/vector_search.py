"""Vector search over policy chunks stored in PostgreSQL with pgvector."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from google import genai
from google.genai import types


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"


@dataclass(frozen=True)
class VectorResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    similarity: float


def create_query_embedding(question: str) -> list[float]:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("Set GOOGLE_CLOUD_PROJECT in examples/.env before running this command.")

    client = genai.Client(
        vertexai=True,
        project=project,
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
    )
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=question,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    if not response.embeddings or response.embeddings[0].values is None:
        raise RuntimeError("Gemini returned an empty query embedding.")
    return response.embeddings[0].values


def vector_search(
    question: str,
    database_url: str,
    limit: int = 5,
) -> list[VectorResult]:
    embedding = vector_literal(create_query_embedding(question))
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            select
                c.id as chunk_id,
                d.id as document_id,
                d.title,
                c.content,
                1 - (c.embedding <=> %s::vector) as similarity
            from lesson_06.support_document_chunks c
            join lesson_06.support_documents d on d.id = c.document_id
            order by c.embedding <=> %s::vector
            limit %s
            """,
            (embedding, embedding, limit),
        ).fetchall()

    return [
        VectorResult(
            chunk_id=row[0],
            document_id=row[1],
            title=row[2],
            content=row[3],
            similarity=float(row[4]),
        )
        for row in rows
    ]


def vector_literal(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding values.")
    return "[" + ",".join(str(value) for value in values) + "]"


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Search policy chunks by meaning.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I take unused holiday into next year?",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    results = vector_search(args.question, database_url, args.limit)

    print(f"Question: {args.question}")
    for result in results:
        print(f"{result.similarity:.3f}  {result.title}  {result.chunk_id}")
        print(f"       {result.content}")


if __name__ == "__main__":
    main()
