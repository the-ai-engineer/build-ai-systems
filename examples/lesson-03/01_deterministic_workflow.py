"""
Deterministic Workflows

A workflow is a fixed sequence of steps.
The model can classify or draft, but your code owns the control flow.
"""

import os
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv(Path(__file__).parents[1] / ".env")


if not os.getenv("OPENAI_API_KEY"):
    print("Set OPENAI_API_KEY in examples/.env to run this example.")
    raise SystemExit(0)


client = OpenAI()

# =============================================================================
# Types
# =============================================================================


class Email(BaseModel):
    sender: str
    subject: str
    body: str


class Action(str, Enum):
    ANSWER = "answer"
    HUMAN_NEEDED = "human_needed"


class Classification(BaseModel):
    action: Action
    reason: str


class PolicyDocument(BaseModel):
    id: str
    title: str
    body: str
    keywords: list[str]


class LabelDecision(BaseModel):
    label: str
    reason: str


# =============================================================================
# Local Data
# =============================================================================


POLICY_DOCUMENTS = [
    PolicyDocument(
        id="refund-policy",
        title="Refund Policy",
        body=(
            "Customers can return most items within 30 days of delivery. "
            "Opened items can be returned if they are complete, undamaged, "
            "and have only been inspected in a normal way."
        ),
        keywords=["refund", "return", "opened", "exchange"],
    ),
    PolicyDocument(
        id="shipping-policy",
        title="Shipping Policy",
        body=(
            "Standard shipping usually takes 3 to 5 business days in the UK "
            "and 7 to 14 business days for international orders."
        ),
        keywords=["shipping", "delivery", "tracking", "package"],
    ),
]


# =============================================================================
# Workflow Steps
# =============================================================================


def classify(email: Email) -> Classification:
    response = client.responses.parse(
        model="gpt-5.6",
        instructions="Decide if the support email can be answered from public policy docs.",
        input=f"Subject: {email.subject}\n\n{email.body}",
        text_format=Classification,
    )
    return response.output_parsed


def find_policy_document(email: Email) -> PolicyDocument | None:
    query = f"{email.subject} {email.body}".lower()

    for document in POLICY_DOCUMENTS:
        if any(keyword in query for keyword in document.keywords):
            return document

    return None


def draft_reply(email: Email, document: PolicyDocument) -> str:
    response = client.responses.create(
        model="gpt-5.6",
        instructions="Answer the customer using only the support policy document.",
        input=f"Customer email:\n{email.body}\n\nPolicy document:\n{document.body}",
    )
    return response.output_text


def decide_label(answerable: bool, reason: str) -> LabelDecision:
    if answerable:
        return LabelDecision(label="AI Answered", reason=reason)

    return LabelDecision(label="Human Needed", reason=reason)


# =============================================================================
# Workflow
# =============================================================================


email = Email(
    sender="customer@example.com",
    subject="Return question",
    body="Can I return a backpack if I opened the box but have not used it?",
)

classification = classify(email)

if classification.action == Action.HUMAN_NEEDED:
    print(decide_label(answerable=False, reason=classification.reason))
    raise SystemExit(0)

document = find_policy_document(email)

if document is None:
    print(decide_label(answerable=False, reason="No matching policy document was found."))
    raise SystemExit(0)

reply = draft_reply(email, document)

print(reply)
print()
print(decide_label(answerable=True, reason=f"Answered from {document.id}"))
