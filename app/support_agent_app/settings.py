"""Every environment value the application reads, declared in one place.

Separate classes so each runtime validates only what it needs. The worker needs
a database and a model; the future webhook needs a Slack signing secret and no
model credential at all.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "google-cloud:gemini-3.5-flash"
LOCAL_TASK_IDENTITY = "local-development-task"

AdapterMode = Literal["configured", "local-fixtures"]


class _BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    @classmethod
    def load(cls) -> Self:
        """Read and validate this runtime's configuration from the environment.

        Prefer this over calling the class directly: every field is populated
        from the environment, which a type checker cannot see.
        """
        return cls()  # pyright: ignore[reportCallIssue]


class ModelProviderSettings(_BaseAppSettings):
    """Model provider selection, resolved through Application Default Credentials."""

    model_name: str = Field(default=DEFAULT_MODEL, validation_alias="SUPPORT_AGENT_MODEL")
    google_cloud_project: str = ""
    google_cloud_location: str = ""


class WorkerBoundarySettings(_BaseAppSettings):
    """What the worker's HTTP boundary needs, and nothing more.

    Deliberately separate from `WorkerSettings`: an application can serve and
    authenticate requests without holding a database or model credential, and
    keeping this class free of required fields lets route tests build the app
    without any environment at all.
    """

    worker_expected_task_identity: str = LOCAL_TASK_IDENTITY
    worker_deadline_seconds: float = 55.0


class WorkerSettings(_BaseAppSettings):
    """What the worker needs to actually do the work."""

    database_url: str

    worker_adapter_mode: AdapterMode = "configured"
    worker_fake_fixture: str = "documented"

    slack_bot_token: SecretStr = SecretStr("")


class ApiSettings(_BaseAppSettings):
    """Configuration for the public Slack webhook runtime.

    Defined now because the ingress lesson adds `api/` against this contract.
    The webhook verifies Slack signatures and writes to the database; it never
    holds a model credential.
    """

    database_url: str
    slack_signing_secret: SecretStr = SecretStr("")
