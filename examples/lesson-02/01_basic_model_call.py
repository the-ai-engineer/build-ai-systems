"""
Basic Model Calls

Call an OpenAI model with the Responses API.
The model is just one software component in the larger support system.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parents[1] / ".env")


if not os.getenv("OPENAI_API_KEY"):
    print("Set OPENAI_API_KEY in examples/.env to run this example.")
    raise SystemExit(0)


client = OpenAI()

# =============================================================================
# Basic Text Response
# =============================================================================


response = client.responses.create(
    model="gpt-5.6",
    instructions="You explain AI systems in simple, practical language.",
    input="Explain what a customer support AI agent does in one sentence.",
)

print(response.output_text)

# =============================================================================
# Domain-Specific Response
# =============================================================================


support_question = "Can I return an opened item?"

response = client.responses.create(
    model="gpt-5.6",
    instructions="Answer like a helpful customer support assistant.",
    input=support_question,
)

print()
print(response.output_text)
