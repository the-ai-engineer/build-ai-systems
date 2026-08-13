"""Hybrid RAG with keyword search, vector search, and rank fusion.

Keyword search rewards exact words. Vector search rewards similar meaning.
Reciprocal Rank Fusion combines their rankings without mixing raw scores.
"""

from __future__ import annotations

import argparse
import math
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


POLICY_DIR = Path(__file__).with_name("policies")
EMBEDDING_MODEL = "text-embedding-3-small"


class SupportDocument(BaseModel):
    id: str
    title: str
    body: str


class HybridResult(BaseModel):
    document: SupportDocument
    score: float
    vector_rank: int | None
    keyword_rank: int | None


def load_policy_documents() -> list[SupportDocument]:
    documents = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8").strip()
        documents.append(
            SupportDocument(
                id=path.stem,
                title=extract_title(body, path.stem),
                body=body,
            )
        )
    return documents


def keyword_ranking(
    documents: list[SupportDocument],
    question: str,
) -> list[str]:
    query_terms = tokenise(question)
    scored = []
    for document in documents:
        document_terms = tokenise(f"{document.title} {document.body}")
        score = len(query_terms & document_terms)
        if score > 0:
            scored.append((score, document.id))
    return [document_id for _, document_id in sorted(scored, reverse=True)]


def vector_ranking(
    client: OpenAI,
    documents: list[SupportDocument],
    question: str,
) -> list[str]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[question, *[document.body for document in documents]],
    )
    query_vector = response.data[0].embedding
    document_vectors = [item.embedding for item in response.data[1:]]
    scored = [
        (cosine_similarity(query_vector, vector), document.id)
        for document, vector in zip(documents, document_vectors, strict=True)
    ]
    return [document_id for _, document_id in sorted(scored, reverse=True)]


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    smoothing: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, document_id in enumerate(ranking, start=1):
            scores[document_id] = scores.get(document_id, 0.0) + 1 / (smoothing + rank)
    return scores


def hybrid_search(
    client: OpenAI,
    documents: list[SupportDocument],
    question: str,
) -> list[HybridResult]:
    keyword = keyword_ranking(documents, question)
    vector = vector_ranking(client, documents, question)
    scores = reciprocal_rank_fusion([keyword, vector])

    document_by_id = {document.id: document for document in documents}
    return [
        HybridResult(
            document=document_by_id[document_id],
            score=score,
            vector_rank=rank_of(document_id, vector),
            keyword_rank=rank_of(document_id, keyword),
        )
        for document_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def tokenise(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9£-]+", text.lower()) if len(token) > 2}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_length = math.sqrt(sum(value * value for value in left))
    right_length = math.sqrt(sum(value * value for value in right))
    if left_length == 0 or right_length == 0:
        return 0.0
    return dot_product / (left_length * right_length)


def rank_of(document_id: str, ranking: list[str]) -> int | None:
    try:
        return ranking.index(document_id) + 1
    except ValueError:
        return None


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))

    parser = argparse.ArgumentParser(description="Combine exact and semantic retrieval.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I carry unused holiday into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in examples/.env to create embeddings.")
        return

    results = hybrid_search(OpenAI(), load_policy_documents(), args.question)

    print(f"Question: {args.question}")
    for result in results:
        print(
            f"{result.score:.4f}  {result.document.title} "
            f"(keyword rank={result.keyword_rank}, vector rank={result.vector_rank})"
        )


if __name__ == "__main__":
    main()
