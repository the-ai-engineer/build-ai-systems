"""Apply pending schema migrations as a deliberate operator action.

Migrations are never applied automatically at process startup. An operator runs
this, sees what it did, and can stop before it touches a live database.
"""

from __future__ import annotations

import argparse

from ..database.migrations import apply_migrations
from ..settings import MissingConfiguration, WorkerSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations in order.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    try:
        database_url = args.database_url or WorkerSettings.load().database_url
    except MissingConfiguration as error:
        # An operator command should say what is missing, not print a stack trace.
        raise SystemExit(str(error)) from error
    apply_migrations(database_url)
    print("Migrations are up to date.")


if __name__ == "__main__":
    main()
