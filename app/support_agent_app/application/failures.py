"""How the system decides whether another attempt can help.

Send failures are split three ways on purpose. A clear failure means Slack did
not accept the reply. An uncertain failure means the worker cannot know, so it
must never blindly retry and risk replying twice to one employee.

Known exception to the dependency rules: `classify_workflow_failure` imports
provider exception types. See ARCHITECTURE.md.
"""

from __future__ import annotations

from psycopg import Error as PostgresError
from pydantic import ValidationError
from pydantic_ai.exceptions import (
    ConcurrencyLimitExceeded,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)


class WorkerTemporaryError(RuntimeError):
    """A safe retry signal that deliberately carries no request content."""


class SlackSendError(RuntimeError):
    """A known send failure for which Slack did not accept the reply."""

    def __init__(self, category: str, *, retryable: bool) -> None:
        super().__init__(category)
        self.category = category
        self.retryable = retryable


class SlackSendUncertainError(RuntimeError):
    """A send began, but the caller cannot know whether Slack accepted it."""

    def __init__(self, category: str = "send_uncertain") -> None:
        super().__init__(category)
        self.category = category


def classify_workflow_failure(error: Exception) -> tuple[str, bool]:
    """Return a safe durable category and whether another attempt can help."""

    if isinstance(error, ModelHTTPError):
        retryable = error.status_code in {408, 409, 429} or error.status_code >= 500
        category = "model_provider_temporary" if retryable else "model_configuration"
        return category, retryable
    if isinstance(
        error,
        (TimeoutError, ModelAPIError, ConcurrencyLimitExceeded, PostgresError),
    ):
        return "model_or_database_temporary", True
    if isinstance(error, (ValidationError, UnexpectedModelBehavior, UsageLimitExceeded)):
        return "invalid_model_output", False
    if isinstance(error, (UserError, ValueError)):
        return "model_configuration", False
    return "model_or_database_temporary", True
