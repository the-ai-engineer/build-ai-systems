"""
File RAG

Load markdown policy files and pick a relevant document for a question.
This is intentionally local to the example.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import BaseModel


POLICY_DIR = Path(__file__).with_name("policies")


class SupportDocument(BaseModel):
    id: str
    title: str
    body: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 06A: simple file RAG.")
    parser.add_argument(
        "question",
        nargs="?",
        default="How many days of annual leave can I carry into next year?",
    )
    args = parser.parse_args()

    document = find_policy_document(args.question)
    if document is None:
        print("No matching policy document found.")
        return

    print(f"Question: {args.question}")
    print(f"Document: {document.title}")
    print()
    print(document.body[:800])


def find_policy_document(question: str) -> SupportDocument | None:
    query_terms = {token.strip(".,!?():").lower() for token in question.split()}

    scored = []
    for document in load_policy_documents():
        haystack = f"{document.title} {document.body}".lower()
        score = sum(1 for term in query_terms if len(term) > 3 and term in haystack)
        scored.append((score, document))

    score, document = max(scored, key=lambda row: row[0])
    if score == 0:
        return None

    return document


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


if __name__ == "__main__":
    main()
