"""Deterministic Pydantic AI model used by the fixture proof path."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RequestUsage,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .domain import SupportDocument


FixtureName = Literal[
    "documented",
    "unsupported",
    "sensitive",
    "conflicting",
    "prompt-injection",
    "invalid-evidence",
]

DOCUMENTED_EXCERPT = (
    "Employees may carry up to five unused days into the next holiday year "
    "with manager approval."
)


def fixture_model(fixture: FixtureName) -> FunctionModel:
    def respond(messages: Sequence[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        response_part = _next_part(fixture, returns, info)
        return ModelResponse(
            parts=[response_part],
            usage=RequestUsage(input_tokens=120, output_tokens=30),
            model_name="fixture",
            finish_reason="stop",
        )

    return FunctionModel(respond, model_name="fixture")


def _next_part(
    fixture: FixtureName,
    returns: list[ToolReturnPart],
    info: AgentInfo,
) -> ToolCallPart:
    if fixture in {"sensitive", "prompt-injection"}:
        reason_code = "sensitive" if fixture == "sensitive" else "unsupported"
        return _final(
            info,
            {
                "decision": "human_review",
                "reason": "This request cannot be answered safely from approved policy documents.",
                "reason_code": reason_code,
                "answer": None,
                "sources": [],
            },
        )

    if not returns:
        return ToolCallPart("list_support_documents", {})

    loaded_ids = []
    for part in returns:
        if part.tool_name != "get_support_document":
            continue
        if isinstance(part.content, SupportDocument):
            loaded_ids.append(part.content.document_id)
        elif isinstance(part.content, dict):
            loaded_ids.append(part.content.get("document_id"))

    if fixture in {"documented", "invalid-evidence"}:
        if "annual-leave-policy" not in loaded_ids:
            return ToolCallPart(
                "get_support_document",
                {"document_id": "annual-leave-policy"},
            )
        document = _loaded_document(returns, "annual-leave-policy")
        excerpt = DOCUMENTED_EXCERPT
        if fixture == "invalid-evidence":
            excerpt = "This sentence does not occur in the loaded document."
        return _final(
            info,
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
            },
        )

    if fixture == "conflicting":
        for document_id in ("annual-leave-policy", "conflicting-leave-policy"):
            if document_id not in loaded_ids:
                return ToolCallPart("get_support_document", {"document_id": document_id})
        return _final(
            info,
            {
                "decision": "human_review",
                "reason": "The active documents conflict, so HR must decide which rule applies.",
                "reason_code": "conflict",
                "answer": None,
                "sources": [],
            },
        )

    return _final(
        info,
        {
            "decision": "human_review",
            "reason": "No active policy document supports this request.",
            "reason_code": "unsupported",
            "answer": None,
            "sources": [],
        },
    )


def _loaded_document(returns: list[ToolReturnPart], document_id: str) -> dict[str, object]:
    for part in returns:
        if part.tool_name != "get_support_document":
            continue
        if isinstance(part.content, SupportDocument) and part.content.document_id == document_id:
            return part.content.model_dump()
        if isinstance(part.content, dict) and part.content.get("document_id") == document_id:
            return part.content
    raise ValueError(f"Fixture model expected loaded document {document_id}")


def _final(info: AgentInfo, content: dict[str, object]) -> ToolCallPart:
    return ToolCallPart(info.output_tools[0].name, content)
