"""Whole-document RAG with an index and a read tool.

The index tells an agent which trusted documents exist.
The read tool returns one complete document after the agent chooses its id.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from pydantic import BaseModel

load_dotenv(Path(__file__).parents[1] / ".env")

POLICY_DIR = Path(__file__).parents[2] / "policies"
MODEL_NAME = os.getenv("SUPPORT_AGENT_MODEL", "gemini-3.5-flash")


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
    name="policy_agent",
    model=MODEL_NAME,
    instruction=(
        "Answer employee questions from approved company policies. "
        "List the policy documents before choosing one. "
        "Read the chosen policy before answering. "
        "Cite the policy title. If the policy does not answer the question, say so."
    ),
    tools=[list_policy_documents, read_policy_document],
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Whole-document RAG with two tools.")
    parser.add_argument(
        "question",
        nargs="?",
        default="How many days of annual leave can I carry into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("Set GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION to run the ADK agent.")
        print("The available document index is:")
        for policy in list_policy_documents():
            print(f"- {policy['id']}: {policy['summary']}")
        return

    print(asyncio.run(run_agent(args.question)))


async def run_agent(question: str) -> str:
    runner = InMemoryRunner(agent=policy_agent, app_name="policy_agent")
    try:
        events = await runner.run_debug(question, quiet=True)
    finally:
        await runner.close()
    for event in reversed(events):
        if event.is_final_response() and event.content is not None:
            return "".join(part.text or "" for part in event.content.parts or [])
    raise RuntimeError("ADK finished without a final response")


if __name__ == "__main__":
    main()
