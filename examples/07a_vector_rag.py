"""
Vector RAG

Use Postgres and pgvector to store HR policy embeddings and retrieve the
most similar documents for an employee question.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


POLICY_DIR = Path(__file__).with_name("policies")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


CREATE_TABLE_SQL = f"""
create extension if not exists vector;

create table if not exists documents (
    id text primary key,
    title text not null,
    body text not null,
    keywords text[] not null default '{{}}',
    search_document tsvector generated always as (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', array_to_string(keywords, ' ')), 'B') ||
        setweight(to_tsvector('english', body), 'C')
    ) stored,
    embedding vector({EMBEDDING_DIMENSIONS}) not null,
    updated_at timestamptz not null default now()
);
"""


UPSERT_DOCUMENT_SQL = """
insert into documents (
    id,
    title,
    body,
    embedding,
    updated_at
)
values (%s, %s, %s, %s::vector, now())
on conflict (id) do update set
    title = excluded.title,
    body = excluded.body,
    embedding = excluded.embedding,
    updated_at = now();
"""


VECTOR_SEARCH_SQL = """
select
    id,
    title,
    1 - (embedding <=> %s::vector) as similarity
from documents
order by embedding <=> %s::vector
limit %s;
"""


class SupportDocument(BaseModel):
    id: str
    title: str
    body: str


class SearchResult(BaseModel):
    id: str
    title: str
    similarity: float


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))

    parser = argparse.ArgumentParser(description="Lesson 07A: vector RAG with Postgres.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Can I work remotely three days per week?",
    )
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Set DATABASE_URL to run this example against Postgres with pgvector.")
        print(
            "Example: DATABASE_URL='postgresql://localhost/build_ai_systems' "
            "uv run python examples/07a_vector_rag.py"
        )
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in examples/.env to create embeddings for this example.")
        return

    client = OpenAI()
    documents = load_policy_documents()

    with psycopg.connect(database_url) as conn:
        setup_database(conn)
        ingest_documents(conn, client, documents)
        results = search_documents(conn, client, args.question, args.limit)

    print(f"Question: {args.question}")
    print()
    for result in results:
        print(f"{result.similarity:.3f} {result.id}: {result.title}")


def setup_database(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)


def ingest_documents(
    conn: psycopg.Connection,
    client: OpenAI,
    documents: list[SupportDocument],
) -> None:
    with conn.cursor() as cur:
        for document in documents:
            embedding = embed(client, document.body)
            cur.execute(
                UPSERT_DOCUMENT_SQL,
                (
                    document.id,
                    document.title,
                    document.body,
                    to_pgvector(embedding),
                ),
            )


def search_documents(
    conn: psycopg.Connection,
    client: OpenAI,
    question: str,
    limit: int,
) -> list[SearchResult]:
    query_embedding = to_pgvector(embed(client, question))

    with conn.cursor() as cur:
        cur.execute(VECTOR_SEARCH_SQL, (query_embedding, query_embedding, limit))
        rows = cur.fetchall()

    return [
        SearchResult(id=row[0], title=row[1], similarity=float(row[2]))
        for row in rows
    ]


def load_policy_documents() -> list[SupportDocument]:
    documents = []

    for path in sorted(POLICY_DIR.glob("*.md")):
        if path.name == "README.md":
            continue

        body = path.read_text(encoding="utf-8").strip()
        documents.append(
            SupportDocument(
                id=path.stem,
                title=extract_title(body, path.stem),
                body=body,
            )
        )

    return documents


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()

    return fallback


def embed(client: OpenAI, text: str) -> list[float]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


if __name__ == "__main__":
    main()
