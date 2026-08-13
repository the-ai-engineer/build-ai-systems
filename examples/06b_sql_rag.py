"""SQL RAG for facts that already have a schema.

An agent can turn a question into the category and field arguments for this
tool. SQL retrieves the exact value. No embeddings are needed.
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Any


POLICY_FACTS = [
    ("annual_leave", "allowance_days", "25", "days", "annual-leave-policy"),
    ("annual_leave", "carry_over_days", "5", "days", "annual-leave-policy"),
    ("annual_leave", "carry_over_deadline", "3", "months", "annual-leave-policy"),
    ("expenses", "claim_deadline", "30", "days", "expenses-policy"),
    ("expenses", "approval_threshold", "250", "GBP", "expenses-policy"),
    ("remote_working", "weekly_limit", "3", "days", "remote-working-policy"),
]


def create_database() -> sqlite3.Connection:
    """Create a tiny in-memory database so the example has no setup."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        create table policy_facts (
            category text not null,
            field text not null,
            value text not null,
            unit text not null,
            source text not null,
            primary key (category, field)
        )
        """
    )
    connection.executemany(
        "insert into policy_facts values (?, ?, ?, ?, ?)",
        POLICY_FACTS,
    )
    return connection


def get_policy_fact(
    connection: sqlite3.Connection,
    category: str,
    field: str,
) -> dict[str, Any]:
    """Retrieve one approved fact using structured arguments."""
    row = connection.execute(
        """
        select category, field, value, unit, source
        from policy_facts
        where category = ? and field = ?
        """,
        (category, field),
    ).fetchone()

    if row is None:
        return {"found": False, "reason": "No approved policy fact matched."}

    return {"found": True, **dict(row)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve an exact policy fact with SQL.")
    parser.add_argument("--category", default="annual_leave")
    parser.add_argument("--field", default="carry_over_days")
    args = parser.parse_args()

    with create_database() as connection:
        result = get_policy_fact(connection, args.category, args.field)

    print(result)


if __name__ == "__main__":
    main()
