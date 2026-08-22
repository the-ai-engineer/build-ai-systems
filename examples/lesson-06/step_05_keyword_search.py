"""Step 5: Search policy chunks with PostgreSQL full-text search."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv


DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"


@dataclass(frozen=True)
class KeywordResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float


def keyword_search(
    question: str,
    database_url: str,
    limit: int = 5,
) -> list[KeywordResult]:
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            select
                c.id as chunk_id,
                d.id as document_id,
                d.title,
                c.content,
                ts_rank_cd(
                    c.search_vector,
                    websearch_to_tsquery('english', %s)
                ) as score
            from lesson_06.support_document_chunks c
            join lesson_06.support_documents d on d.id = c.document_id
            where c.search_vector @@ websearch_to_tsquery('english', %s)
            order by score desc
            limit %s
            """,
            (question, question, limit),
        ).fetchall()

    return [
        KeywordResult(
            chunk_id=row[0],
            document_id=row[1],
            title=row[2],
            content=row[3],
            score=float(row[4]),
        )
        for row in rows
    ]


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Search policy chunks by exact words.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I carry unused holiday into next year?",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    results = keyword_search(args.question, database_url, args.limit)

    print(f"Question: {args.question}")
    for result in results:
        print(f"{result.score:.3f}  {result.title}  {result.chunk_id}")
        print(f"       {result.content}")


if __name__ == "__main__":
    main()
