"""The worker's wire contract.

The task payload carries a request ID and nothing else. The employee's question
stays in the database, so the queue never holds sensitive content.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID


class ProcessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    outcome: str
    send_attempted: bool
