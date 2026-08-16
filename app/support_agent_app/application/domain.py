"""Typed inputs, policy records, verified decisions, and safe run metadata.

The application layer owns this vocabulary. The agent, database, and integration
adapters all import from here, so the dependency arrows point inwards.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HumanReviewReason = Literal[
    "off_topic",
    "unsupported",
    "sensitive",
    "conflict",
    "invalid_evidence",
]


class SupportQuestion(BaseModel):
    """A normalized support question with no Slack-specific fields."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_whitespace(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())
        return value


class SupportDocumentIndexItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    category: str
    summary: str
    keywords: tuple[str, ...]
    source_filename: str
    revision: str


class SupportDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    category: str
    summary: str
    keywords: tuple[str, ...]
    source_filename: str
    revision: str
    body: str
    is_active: bool = True

    def index_item(self) -> SupportDocumentIndexItem:
        return SupportDocumentIndexItem(
            document_id=self.document_id,
            title=self.title,
            category=self.category,
            summary=self.summary,
            keywords=self.keywords,
            source_filename=self.source_filename,
            revision=self.revision,
        )


class SourceCitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    title: str
    source_filename: str
    document_revision: str
    supporting_excerpt: str = Field(min_length=1, max_length=500)

    @field_validator("supporting_excerpt")
    @classmethod
    def require_visible_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("supporting_excerpt must contain visible text")
        return value


class AnswerDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: Literal["answer"] = "answer"
    answer: str = Field(min_length=1, max_length=800)
    reason: str = Field(min_length=1, max_length=500)
    sources: tuple[SourceCitation, ...] = Field(min_length=1, max_length=3)

    @field_validator("answer", mode="before")
    @classmethod
    def strip_answer(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class HumanReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: Literal["human_review"] = "human_review"
    answer: None = None
    reason: str = Field(min_length=1, max_length=500)
    reason_code: HumanReviewReason
    sources: tuple[()] = ()

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


SupportDecision = Annotated[
    AnswerDecision | HumanReviewDecision,
    Field(discriminator="decision"),
]


class LoadedDocumentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    revision: str


class AgentRunRecord(BaseModel):
    """Operational evidence that deliberately excludes question and policy text."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    model_location: str
    service_tier: str
    selected_documents: tuple[LoadedDocumentRecord, ...]
    input_tokens: int = Field(ge=0)
    retrieved_context_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    finish_reason: str
    tool_call_count: int = Field(ge=0)
    model_turn_count: int = Field(ge=0)


class WorkflowOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: SupportDecision
    run: AgentRunRecord
