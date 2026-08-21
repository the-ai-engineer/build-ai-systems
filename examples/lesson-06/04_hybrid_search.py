"""Run Lesson 06 hybrid policy search from the command line."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from hybrid_policy_agent.search import (
    DEFAULT_DATABASE_URL,
    create_query_embedding,
    hybrid_search,
)


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Combine exact words with semantic search.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I carry unused holiday into next year?",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    results = hybrid_search(
        database_url,
        args.question,
        create_query_embedding(args.question),
        args.limit,
    )

    print(f"Question: {args.question}")
    for result in results:
        print(
            f"{result.score:.4f}  {result.title}  {result.chunk_id} "
            f"(keyword={result.keyword_rank}, vector={result.vector_rank})"
        )
        print(f"        {result.content}")


if __name__ == "__main__":
    main()
