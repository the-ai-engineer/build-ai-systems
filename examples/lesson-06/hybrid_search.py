"""Combine keyword and vector rankings with Reciprocal Rank Fusion."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from keyword_search import keyword_search
from vector_search import vector_search


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
    question: str,
    database_url: str,
    limit: int = 5,
) -> list[HybridResult]:
    keyword_results = keyword_search(question, database_url, limit)
    vector_results = vector_search(question, database_url, limit)

    keyword_ranks = {
        result.chunk_id: rank for rank, result in enumerate(keyword_results, start=1)
    }
    vector_ranks = {result.chunk_id: rank for rank, result in enumerate(vector_results, start=1)}
    scores = reciprocal_rank_fusion([list(keyword_ranks), list(vector_ranks)])
    details = {result.chunk_id: result for result in [*keyword_results, *vector_results]}

    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return [
        HybridResult(
            chunk_id=chunk_id,
            document_id=details[chunk_id].document_id,
            title=details[chunk_id].title,
            content=details[chunk_id].content,
            score=scores[chunk_id],
            keyword_rank=keyword_ranks.get(chunk_id),
            vector_rank=vector_ranks.get(chunk_id),
        )
        for chunk_id in ranked_ids
    ]


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Fuse keyword and vector search rankings.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I carry unused holiday into next year?",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    results = hybrid_search(args.question, database_url, args.limit)

    print(f"Question: {args.question}")
    for result in results:
        print(
            f"{result.score:.4f}  {result.title}  {result.chunk_id} "
            f"(keyword={result.keyword_rank}, vector={result.vector_rank})"
        )
        print(f"        {result.content}")


if __name__ == "__main__":
    main()
