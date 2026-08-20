"""Load the approved policy set into Postgres.

Seeding no longer applies schema of its own. It calls `apply_migrations`, so
there is one migration history and one place the schema can change.

Both directories can be named on the command line, because the same command
runs from a checkout and from the container image, where the files sit at a
fixed path instead of beside the code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from psycopg import connect

from ..database.migrations import DEFAULT_MIGRATIONS_DIRECTORY, apply_migrations
from ..database.repositories.policy_repository import (
    DEFAULT_POLICY_DIRECTORY,
    load_policy_directory,
)
from ..settings import MissingConfiguration, WorkerSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="Load active policy fixtures into Postgres.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--policies-dir",
        type=Path,
        default=DEFAULT_POLICY_DIRECTORY,
        help="Where the policy Markdown files are. Defaults to the repository's policies/.",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIRECTORY,
        help="Where the .sql files are. Defaults to the repository's migrations/.",
    )
    args = parser.parse_args()

    try:
        database_url = args.database_url or WorkerSettings.load().database_url
    except MissingConfiguration as error:
        # An operator command should say what is missing, not print a stack trace.
        raise SystemExit(str(error)) from error
    count = seed_policy_documents(
        database_url,
        policies_directory=args.policies_dir,
        migrations_directory=args.migrations_dir,
    )
    print(f"Loaded {count} active support documents from {args.policies_dir}.")


def seed_policy_documents(
    database_url: str,
    *,
    policies_directory: Path = DEFAULT_POLICY_DIRECTORY,
    migrations_directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> int:
    """Load the synthetic policy set for local demos and integration tests."""

    if not database_url:
        raise ValueError("database_url is required")
    apply_migrations(database_url, migrations_directory)
    documents = load_policy_directory(policies_directory)
    with connect(database_url) as connection:
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
