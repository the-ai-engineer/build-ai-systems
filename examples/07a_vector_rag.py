"""Vector RAG with OpenAI embeddings and an in-memory search.

This example keeps storage out of the way so the retrieval mechanism is clear:
embed the documents, embed the question, then rank by cosine similarity.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

POLICY_DIR = Path(__file__).parents[1] / "policies"
EMBEDDING_MODEL = "text-embedding-3-small"


class SupportDocument(BaseModel):
    id: str
    title: str
    body: str


class SearchResult(BaseModel):
    document: SupportDocument
    score: float


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


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_length = math.sqrt(sum(value * value for value in left))
    right_length = math.sqrt(sum(value * value for value in right))
    if left_length == 0 or right_length == 0:
        return 0.0
    return dot_product / (left_length * right_length)


def search_documents(
    client: OpenAI,
    documents: list[SupportDocument],
    question: str,
) -> list[SearchResult]:
    document_vectors = embed_texts(client, [document.body for document in documents])
    query_vector = embed_texts(client, [question])[0]

    results = [
        SearchResult(
            document=document,
            score=cosine_similarity(query_vector, document_vector),
        )
        for document, document_vector in zip(documents, document_vectors, strict=True)
    ]
    return sorted(results, key=lambda result: result.score, reverse=True)


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))

    parser = argparse.ArgumentParser(description="Rank policy documents by meaning.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I take unused holiday into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in examples/.env to create embeddings.")
        return

    results = search_documents(OpenAI(), load_policy_documents(), args.question)

    print(f"Question: {args.question}")
    for result in results:
        print(f"{result.score:.3f}  {result.document.title}")


if __name__ == "__main__":
    main()
