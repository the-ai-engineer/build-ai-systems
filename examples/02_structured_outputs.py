"""
Structured Outputs

Classify support emails with Pydantic models and the OpenAI Responses API.
Structured outputs turn model responses into typed data your application can trust.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv(Path(__file__).with_name(".env"))


if not os.getenv("OPENAI_API_KEY"):
    print("Set OPENAI_API_KEY in examples/.env to run this example.")
    raise SystemExit(0)


client = OpenAI()

# =============================================================================
# Support Email Classification
# =============================================================================


class Classification(BaseModel):
    category: Literal["refund", "shipping", "account", "other"]
    urgent: bool


def classify(email: str) -> Classification:
    response = client.responses.parse(
        model="gpt-5.6",
        instructions="Classify the customer support email.",
        input=email,
        text_format=Classification,
    )
    return response.output_parsed


emails = [
    "Can I return a backpack if I opened the box but have not used it?",
    "My order was due yesterday. When will it arrive?",
    "I cannot sign in and need access before my trip tomorrow.",
]

for email in emails:
    print(f"\nEmail: {email}")
    print(f"Classification: {classify(email)}")

# =============================================================================
# Nested Structured Output
# =============================================================================


class Customer(BaseModel):
    name: str
    email: str


class SupportRequest(BaseModel):
    customer: Customer
    summary: str
    order_number: str


def extract_request(email: str) -> SupportRequest:
    response = client.responses.parse(
        model="gpt-5.6",
        instructions="Extract the customer and support request from the email.",
        input=email,
        text_format=SupportRequest,
    )
    return response.output_parsed


email = (
    "Hi, I am Maya Chen (maya@example.com). "
    "Can you tell me whether order NS-1029 has shipped yet?"
)

request = extract_request(email)
print(f"\nNested request: {request}")
