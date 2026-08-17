"""The model-facing output schema, before deterministic evidence validation.

`AgentDecision` is untrusted. `evidence.verify_decision` turns it into an
application-owned `AnswerDecision` or `HumanReviewDecision`, and only those
reach the database or Slack.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ...application.domain import HumanReviewReason, SourceCitation


class AgentDecision(BaseModel):
    """The model-facing schema before deterministic evidence validation."""

    decision: Literal["answer", "human_review"]
    answer: str | None = Field(default=None, max_length=800)
    reason: str = Field(min_length=1, max_length=500)
    reason_code: HumanReviewReason | None = None
    sources: list[SourceCitation] = Field(default_factory=list, max_length=3)

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

    @model_validator(mode="after")
    def fields_match_decision(self) -> AgentDecision:
        if self.decision == "answer":
            if not self.answer or not self.sources or self.reason_code is not None:
                raise ValueError("answer decisions require an answer and sources only")
        elif self.answer is not None or self.sources or self.reason_code is None:
            raise ValueError(
                "human_review decisions require a reason code and no answer or sources"
            )
        return self
