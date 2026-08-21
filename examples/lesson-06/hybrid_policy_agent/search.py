"""Hybrid PostgreSQL retrieval shared by the Lesson 06 CLI and ADK agent."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg
from google import genai
from google.genai import types


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"


@dataclass(frozen=True)
class HybridResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    keyword_rank: int | None
    vector_rank: int | None


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


def retrieve_rankings(
    database_url: str,
    question: str,
    query_embedding: list[float],
    candidate_limit: int = 10,
) -> tuple[list[str], list[str], dict[str, dict[str, str]]]:
    embedding = vector_literal(query_embedding)
    with psycopg.connect(database_url) as connection:
        keyword_rows = connection.execute(
            """
            select c.id
            from lesson_06.support_document_chunks c
            where c.search_vector @@ websearch_to_tsquery('english', %s)
            order by ts_rank_cd(
                c.search_vector,
                websearch_to_tsquery('english', %s)
            ) desc
            limit %s
            """,
            (question, question, candidate_limit),
        ).fetchall()
        vector_rows = connection.execute(
            """
            select c.id
            from lesson_06.support_document_chunks c
            order by c.embedding <=> %s::vector
            limit %s
            """,
            (embedding, candidate_limit),
        ).fetchall()

        chunk_ids = list(
            dict.fromkeys([row[0] for row in keyword_rows] + [row[0] for row in vector_rows])
        )
        details: dict[str, dict[str, str]] = {}
        if chunk_ids:
            detail_rows = connection.execute(
                """
                select
                    c.id as chunk_id,
                    d.id as document_id,
                    d.title,
                    c.content
                from lesson_06.support_document_chunks c
                join lesson_06.support_documents d on d.id = c.document_id
                where c.id = any(%s)
                """,
                (chunk_ids,),
            ).fetchall()
            details = {
                row[0]: {
                    "chunk_id": row[0],
                    "document_id": row[1],
                    "title": row[2],
                    "content": row[3],
                }
                for row in detail_rows
            }

    return (
        [row[0] for row in keyword_rows],
        [row[0] for row in vector_rows],
        details,
    )


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    smoothing: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (smoothing + rank)
    return scores


def hybrid_search(
    database_url: str,
    question: str,
    query_embedding: list[float],
    limit: int = 5,
) -> list[HybridResult]:
    keyword, vector, details = retrieve_rankings(database_url, question, query_embedding)
    scores = reciprocal_rank_fusion([keyword, vector])
    ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:limit]
    return [
        HybridResult(
            **details[chunk_id],
            score=scores[chunk_id],
            keyword_rank=rank_of(chunk_id, keyword),
            vector_rank=rank_of(chunk_id, vector),
        )
        for chunk_id in ranked_ids
    ]


def rank_of(chunk_id: str, ranking: list[str]) -> int | None:
    try:
        return ranking.index(chunk_id) + 1
    except ValueError:
        return None


def vector_literal(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding values.")
    return "[" + ",".join(str(value) for value in values) + "]"
