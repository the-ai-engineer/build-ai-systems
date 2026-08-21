"""Google ADK agentic RAG over complete policy documents in PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from google.adk.agents import Agent


DEFAULT_DATABASE_URL = "postgresql:///rag_lesson"


def create_document_tools(database_url: str) -> list[Any]:
    def list_support_documents() -> list[dict[str, str]]:
        """List the id, title, and summary of every approved support document."""
        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                select id, title, summary
                from lesson_05.support_documents
                order by title
                """
            ).fetchall()
        return [{"id": row[0], "title": row[1], "summary": row[2]} for row in rows]

    def read_support_document(document_id: str) -> dict[str, str | bool]:
        """Read one approved support document after choosing its exact id."""
        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                """
                select id, title, body
                from lesson_05.support_documents
                where id = %s
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return {"found": False, "reason": "Unknown support document."}
        return {"found": True, "id": row[0], "title": row[1], "body": row[2]}

    return [list_support_documents, read_support_document]


def build_agent(database_url: str) -> Agent:
    return Agent(
        name="policy_agent",
        model=os.getenv("SUPPORT_AGENT_MODEL", "gemini-3.5-flash"),
        description="Answers employee questions from approved company policies in PostgreSQL.",
        instruction=(
            "Answer employee questions from approved company policies. "
            "First list the available support documents. Choose the most relevant id, "
            "then read that document before answering. Cite the document title. "
            "If no approved document answers the question, say that you could not find "
            "an approved policy. Do not claim that you will contact or connect a person."
        ),
        tools=create_document_tools(database_url),
    )


load_dotenv(Path(__file__).parents[2] / ".env")
root_agent = build_agent(os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL))
