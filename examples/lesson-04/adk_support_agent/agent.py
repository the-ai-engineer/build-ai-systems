"""Lesson 04.02: rebuild the hand-written support agent with Google ADK.

Run ADK Web from examples/lesson-04 to inspect the agent loop, tool calls,
results, and session events in a browser.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent
from pydantic import BaseModel

MODEL_NAME = os.getenv("SUPPORT_AGENT_MODEL", "gemini-3.5-flash")


class SupportDocument(BaseModel):
    id: str
    title: str
    summary: str
    body: str
    keywords: list[str]


SUPPORT_DOCUMENTS = [
    SupportDocument(
        id="refund-policy",
        title="Refund Policy",
        summary="Opened, unused items can usually be returned within 30 days.",
        body=(
            "Customers can return most items within 30 days of delivery. "
            "Opened items can be returned if they are complete, undamaged, "
            "and have only been inspected in a normal way."
        ),
        keywords=["refund", "return", "opened", "exchange"],
    ),
    SupportDocument(
        id="shipping-policy",
        title="Shipping Policy",
        summary="Standard shipping times and tracking guidance.",
        body=(
            "Standard shipping usually takes 3 to 5 business days in the UK "
            "and 7 to 14 business days for international orders."
        ),
        keywords=["shipping", "delivery", "tracking", "package"],
    ),
]


def list_support_documents() -> list[dict[str, str]]:
    """Return the policy index the agent should inspect before answering."""
    return [
        {
            "id": document.id,
            "title": document.title,
            "summary": document.summary,
        }
        for document in SUPPORT_DOCUMENTS
    ]


def find_support_document(query: str) -> dict[str, str | bool]:
    """Return the best matching policy document for a support question."""
    normalized_query = query.lower()

    for document in SUPPORT_DOCUMENTS:
        if any(keyword in normalized_query for keyword in document.keywords):
            return {
                "found": True,
                "id": document.id,
                "title": document.title,
                "body": document.body,
            }

    return {"found": False, "reason": "No matching support document was found."}


root_agent = Agent(
    name="support_agent",
    model=MODEL_NAME,
    description="Answers customer questions from approved support documents.",
    instruction=(
        "You are a customer support agent.\n"
        "Use list_support_documents before choosing a policy.\n"
        "Use find_support_document before answering.\n"
        "Answer only from the returned policy document.\n"
        "Do not perform refunds, change orders, or answer account-specific requests.\n"
        "Say a human should handle those requests even when a policy matches.\n"
        "If no policy matches, say a human should handle the message."
    ),
    tools=[list_support_documents, find_support_document],
)
