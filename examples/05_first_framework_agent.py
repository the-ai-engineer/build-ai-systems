"""
First Framework Agent

Move the document lookup tools from the hand-built loop into Pydantic AI.

The framework owns the provider-specific request format and agent loop.
Our instructions and business tools stay the same when the model changes.

This makes provider changes easier, not automatic. Native provider tools,
model settings, and supported features can still require code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent

load_dotenv(Path(__file__).with_name(".env"))


OPENAI_MODEL = "openai:gpt-5.6"
CLAUDE_MODEL = "anthropic:claude-sonnet-4-6"

def normalize_model_name(model_name: str) -> str:
    """Accept Pydantic AI names and the old provider/model course format."""
    if model_name.startswith(("openai/", "anthropic/")):
        provider, model = model_name.split("/", maxsplit=1)
        return f"{provider}:{model}"
    return model_name


# Change this setting, not the agent loop, to use another supported provider.
MODEL_NAME = normalize_model_name(os.getenv("AI_ARCHITECT_MODEL", OPENAI_MODEL))


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


support_agent = Agent(
    MODEL_NAME,
    instructions=(
        "You are a customer support agent.\n"
        "Use list_support_documents before choosing a policy.\n"
        "Use find_support_document before answering.\n"
        "Answer only from the returned policy document.\n"
        "If no policy matches, say a human should handle the message."
    ),
    tools=[list_support_documents, find_support_document],
    defer_model_check=True,
)


def required_api_key(model_name: str) -> str:
    if model_name.startswith("anthropic:"):
        return "ANTHROPIC_API_KEY"
    return "OPENAI_API_KEY"


def main() -> None:
    print(f"Pydantic AI model: {MODEL_NAME}")
    print(f"Try Claude with: AI_ARCHITECT_MODEL={CLAUDE_MODEL}")

    api_key_name = required_api_key(MODEL_NAME)
    if not os.getenv(api_key_name):
        print(f"Set {api_key_name} in examples/.env to run the agent.")
        return

    result = support_agent.run_sync(
        "Can I return a backpack if I opened the box but have not used it?"
    )
    print("\nFinal:")
    print(result.output)


if __name__ == "__main__":
    main()
