"""Whole-document RAG with an index and a read tool.

The index tells an agent which trusted documents exist.
The read tool returns one complete document after the agent chooses its id.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent

POLICY_DIR = Path(__file__).parents[1] / "policies"
MODEL_NAME = "openai:gpt-5.6"


class PolicySummary(BaseModel):
    id: str
    title: str
    summary: str


POLICY_INDEX = [
    PolicySummary(
        id="annual-leave-policy",
        title="Annual Leave Policy",
        summary="Annual leave allowance, requests, and carrying unused days forward.",
    ),
    PolicySummary(
        id="expenses-policy",
        title="Expenses Policy",
        summary="Receipts, deadlines, and approval rules for business expenses.",
    ),
    PolicySummary(
        id="remote-working-policy",
        title="Remote Working Policy",
        summary="Remote working limits, manager agreement, and office attendance.",
    ),
]


def list_policy_documents() -> list[dict[str, str]]:
    """Return the small index the agent uses to choose a policy."""
    return [policy.model_dump() for policy in POLICY_INDEX]


def read_policy_document(document_id: str) -> dict[str, str | bool]:
    """Read one trusted policy by its id."""
    known_ids = {policy.id for policy in POLICY_INDEX}
    if document_id not in known_ids:
        return {"found": False, "reason": "Unknown policy document."}

    body = (POLICY_DIR / f"{document_id}.md").read_text(encoding="utf-8")
    return {"found": True, "document_id": document_id, "body": body}


policy_agent = Agent(
    MODEL_NAME,
    instructions=(
        "Answer employee questions from approved company policies. "
        "List the policy documents before choosing one. "
        "Read the chosen policy before answering. "
        "Cite the policy title. If the policy does not answer the question, say so."
    ),
    tools=[list_policy_documents, read_policy_document],
    defer_model_check=True,
)


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))

    parser = argparse.ArgumentParser(description="Whole-document RAG with two tools.")
    parser.add_argument(
        "question",
        nargs="?",
        default="How many days of annual leave can I carry into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in examples/.env to run the agent.")
        print("The available document index is:")
        for policy in list_policy_documents():
            print(f"- {policy['id']}: {policy['summary']}")
        return

    result = policy_agent.run_sync(args.question)
    print(result.output)


if __name__ == "__main__":
    main()
