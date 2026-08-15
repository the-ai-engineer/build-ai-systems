"""Create the policy table and load the synthetic Markdown policies."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from psycopg import connect

from .fixtures import POLICY_DIRECTORY
from .repositories import load_policy_directory


SCHEMA_PATH = Path(__file__).with_name("sql") / "001_support_documents.sql"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load active policy fixtures into Postgres.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("Set DATABASE_URL or pass --database-url.")

    count = seed_policy_documents(args.database_url)
    print(f"Loaded {count} active support documents.")


def seed_policy_documents(database_url: str) -> int:
    """Load the synthetic policy set for local demos and integration tests."""

    if not database_url:
        raise ValueError("database_url is required")
    documents = load_policy_directory(POLICY_DIRECTORY)
    with connect(database_url) as connection:
        statements = SCHEMA_PATH.read_text(encoding="utf-8").split(";")
        for statement in statements:
            if statement.strip():
                connection.execute(statement)
        for document in documents:
            connection.execute(
                """
                insert into support_documents (
                    id, source_file, title, category, summary, keywords,
                    body, content_hash, revision, is_active
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                on conflict (id) do update set
                    source_file = excluded.source_file,
                    title = excluded.title,
                    category = excluded.category,
                    summary = excluded.summary,
                    keywords = excluded.keywords,
                    body = excluded.body,
                    content_hash = excluded.content_hash,
                    revision = excluded.revision,
                    is_active = true,
                    updated_at = now()
                """,
                (
                    document.document_id,
                    document.source_filename,
                    document.title,
                    document.category,
                    document.summary,
                    list(document.keywords),
                    document.body,
                    document.revision.removeprefix("sha256:"),
                    document.revision,
                ),
            )
    return len(documents)


if __name__ == "__main__":
    main()
