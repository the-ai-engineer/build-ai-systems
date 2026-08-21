"""Deterministic Google ADK model used by the fixture proof path."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Literal

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel

FixtureName = Literal[
    "documented",
    "unsupported",
    "sensitive",
    "conflicting",
    "prompt-injection",
    "invalid-evidence",
]

DOCUMENTED_EXCERPT = (
    "Employees may carry up to five unused days into the next holiday year with manager approval."
)


class FixtureModel(BaseLlm):
    """Return scripted ADK function calls while exercising the real runner."""

    model: str = "fixture"
    fixture: FixtureName

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        returns = [
            part.function_response
            for content in llm_request.contents
            for part in content.parts or []
            if part.function_response is not None
        ]
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[_next_part(self.fixture, returns)],
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=120,
                candidates_token_count=30,
                total_token_count=150,
            ),
            model_version=self.model,
            finish_reason=types.FinishReason.STOP,
        )


def fixture_model(fixture: FixtureName) -> FixtureModel:
    return FixtureModel(fixture=fixture)


def _next_part(
    fixture: FixtureName,
    returns: list[types.FunctionResponse],
) -> types.Part:
    if fixture in {"sensitive", "prompt-injection"}:
        reason_code = "sensitive" if fixture == "sensitive" else "unsupported"
        return _final(
            {
                "decision": "human_review",
                "reason": "This request cannot be answered safely from approved policy documents.",
                "reason_code": reason_code,
                "answer": None,
                "sources": [],
            }
        )

    if not returns:
        return types.Part.from_function_call(name="list_support_documents", args={})

    loaded_ids = [
        _tool_result(response).get("document_id")
        for response in returns
        if response.name == "get_support_document"
    ]

    if fixture in {"documented", "invalid-evidence"}:
        if "annual-leave-policy" not in loaded_ids:
            return types.Part.from_function_call(
                name="get_support_document",
                args={"document_id": "annual-leave-policy"},
            )
        document = _loaded_document(returns, "annual-leave-policy")
        excerpt = DOCUMENTED_EXCERPT
        if fixture == "invalid-evidence":
            excerpt = "This sentence does not occur in the loaded document."
        return _final(
            {
                "decision": "answer",
                "answer": (
                    "You may carry up to five unused days into the next holiday year "
                    "with manager approval."
                ),
                "reason": "The active annual leave policy directly supports this answer.",
                "reason_code": None,
                "sources": [
                    {
                        "document_id": document["document_id"],
                        "title": document["title"],
                        "source_filename": document["source_filename"],
                        "document_revision": document["revision"],
                        "supporting_excerpt": excerpt,
                    }
                ],
            }
        )

    if fixture == "conflicting":
        for document_id in ("annual-leave-policy", "conflicting-leave-policy"):
            if document_id not in loaded_ids:
                return types.Part.from_function_call(
                    name="get_support_document",
                    args={"document_id": document_id},
                )
        return _final(
            {
                "decision": "human_review",
                "reason": "The active documents conflict, so HR must decide which rule applies.",
                "reason_code": "conflict",
                "answer": None,
                "sources": [],
            }
        )

    return _final(
        {
            "decision": "human_review",
            "reason": "No active policy document supports this request.",
            "reason_code": "unsupported",
            "answer": None,
            "sources": [],
        }
    )


def _loaded_document(
    returns: list[types.FunctionResponse],
    document_id: str,
) -> dict[str, object]:
    for response in returns:
        if response.name != "get_support_document":
            continue
        result = _tool_result(response)
        if result.get("document_id") == document_id:
            return result
    raise ValueError(f"Fixture model expected loaded document {document_id}")


def _tool_result(response: types.FunctionResponse) -> dict[str, object]:
    result = (response.response or {}).get("result", response.response)
    if isinstance(result, BaseModel):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {}


def _final(content: dict[str, object]) -> types.Part:
    return types.Part.from_function_call(name="set_model_response", args=content)
