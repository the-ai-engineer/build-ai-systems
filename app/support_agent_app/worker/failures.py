"""How the worker decides whether another attempt can help.

Known exception to the dependency rules: this imports provider exception types
so it can map them to durable categories. See ARCHITECTURE.md.
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
