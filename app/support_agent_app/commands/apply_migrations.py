"""Apply pending schema migrations as a deliberate operator action.

Migrations are never applied automatically at process startup. An operator runs
this, sees what it did, and can stop before it touches a live database.

`--migrations-dir` exists because the same command runs from two places. In a
checkout the migrations sit beside the code and the default finds them; in the
container image they are copied to a fixed path that no relative resolution
would reach. Naming the directory is an operator's choice, so it is an argument
rather than a guess made at import time.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..database.migrations import DEFAULT_MIGRATIONS_DIRECTORY, apply_migrations
from ..settings import MissingConfiguration, WorkerSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations in order.")
    parser.add_argument("--database-url", default=None)
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
    apply_migrations(database_url, args.migrations_dir)
    print(f"Migrations are up to date, from {args.migrations_dir}.")


if __name__ == "__main__":
    main()
