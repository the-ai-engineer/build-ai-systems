"""Apply the repository's explicit SQL migrations in filename order."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MIGRATIONS_DIRECTORY = Path(__file__).parents[3] / "migrations"


def apply_migrations(
    database_url: str,
    migrations_directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> None:
    """Apply each migration once, with a database lock around the migration set."""

    if not database_url:
        raise ValueError("database_url is required")
    # An absent directory used to glob to nothing and report success, so a
    # command run where the repository files are not present, such as inside
    # the container image, said "up to date" over an empty schema.
    if not migrations_directory.is_dir():
        raise FileNotFoundError(f"no migrations directory at {migrations_directory}")

    from psycopg import connect

    with connect(database_url) as connection, connection.transaction():
        connection.execute("select pg_advisory_xact_lock(hashtext('support_agent_app_migrations'))")
        connection.execute(
            """
                create table if not exists support_schema_migrations (
                    version text primary key,
                    applied_at timestamptz not null default now()
                )
                """
        )
        applied = {
            row[0]
            for row in connection.execute(
                "select version from support_schema_migrations"
            ).fetchall()
        }
        for path in sorted(migrations_directory.glob("*.sql")):
            if path.name in applied:
                continue
            connection.execute(path.read_text(encoding="utf-8"), prepare=False)
            connection.execute(
                "insert into support_schema_migrations (version) values (%s)",
                (path.name,),
            )
