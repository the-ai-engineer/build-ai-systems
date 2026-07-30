"""
SQL RAG

Turn markdown support policies into rows that can be stored in Postgres.
This file only prints the insert shape.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


POLICY_DIR = Path(__file__).with_name("policies")


UPSERT_DOCUMENT_SQL = """
insert into support_documents (
    id,
    title,
    category,
    summary,
    body,
    keywords,
    updated_at
)
values (%s, %s, %s, %s, %s, %s, now())
on conflict (id) do update set
    title = excluded.title,
    category = excluded.category,
    summary = excluded.summary,
    body = excluded.body,
    keywords = excluded.keywords,
    is_active = true,
    updated_at = now();
"""


class SupportDocument(BaseModel):
    id: str
    title: str
    category: str
    summary: str
    body: str
    keywords: list[str]


def main() -> None:
    documents = load_policy_documents()

    print("Lesson 06B: SQL RAG")
    print()
    print("In production these markdown files become rows in Postgres.")
    print(f"Policy directory: {POLICY_DIR}")
    print(f"Documents parsed: {len(documents)}")
    print()
    print("Example row:")
    print(
        {
            "id": documents[0].id,
            "title": documents[0].title,
            "category": documents[0].category,
            "summary": documents[0].summary,
            "keywords": documents[0].keywords,
            "body": documents[0].body[:120] + "...",
        }
    )
    print()
    print("Upsert shape:")
    print(UPSERT_DOCUMENT_SQL.strip())


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
                category=path.stem.removesuffix("-policy"),
                summary=extract_summary(body),
                body=body,
                keywords=extract_keywords(path.stem),
            )
        )

    return documents


def extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()

    return fallback


def extract_summary(markdown: str) -> str:
    paragraph = []

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("Last updated:"):
            if paragraph:
                break
            continue

        paragraph.append(stripped)

    return " ".join(paragraph)


def extract_keywords(document_id: str) -> list[str]:
    keyword_map = {
        "annual-leave-policy": ["annual leave", "holiday", "carry", "days"],
        "expenses-policy": ["expenses", "receipt", "claim", "approval"],
        "remote-working-policy": ["remote", "home", "office", "manager"],
    }
    return keyword_map.get(document_id, document_id.split("-"))


if __name__ == "__main__":
    main()
