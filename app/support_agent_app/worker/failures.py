"""How the worker decides whether another attempt can help.

Known exception to the dependency rules: this imports provider exception types
so it can map them to durable categories. See ARCHITECTURE.md.
"""

from __future__ import annotations

from google.auth.exceptions import DefaultCredentialsError
from google.genai.errors import APIError, ClientError, ServerError
from psycopg import Error as PostgresError
from pydantic import ValidationError

from .agent.agent import AgentRunLimitError, InvalidModelOutputError


class WorkerTemporaryError(RuntimeError):
    """A safe retry signal that deliberately carries no request content."""


def classify_workflow_failure(error: Exception) -> tuple[str, bool]:
    """Return a safe durable category and whether another attempt can help."""

    if isinstance(error, DefaultCredentialsError):
        return "model_configuration", False
    if isinstance(error, ClientError):
        retryable = error.code in {408, 409, 429}
        category = "model_provider_temporary" if retryable else "model_configuration"
        return category, retryable
    if isinstance(error, ServerError):
        return "model_provider_temporary", True
    if isinstance(error, (TimeoutError, APIError, PostgresError)):
        return "model_or_database_temporary", True
    if isinstance(error, (ValidationError, InvalidModelOutputError, AgentRunLimitError)):
        return "invalid_model_output", False
    if isinstance(error, ValueError):
        return "model_configuration", False
    return "model_or_database_temporary", True
