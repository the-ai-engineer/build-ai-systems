"""Every environment value the application reads, declared in one place.

Separate classes so each runtime validates only what it needs. The worker needs
a database and a model; the future webhook needs a Slack signing secret and no
model credential at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "google-cloud:gemini-3.5-flash"
LOCAL_TASK_IDENTITY = "local-development-task"

# Two independent switches, because the model and Slack are two separate
# external systems. Coupling them meant "real model, no Slack workspace" was
# impossible, which is the most common local setup there is.
ModelSource = Literal["configured", "fixture"]
SlackSink = Literal["slack", "record"]

# The repository root, found from this file rather than from the current
# directory. A relative ".env" is resolved against the process's working
# directory, so it is only found when a command happens to be run from the root.
# Anchoring it here means `uv run seed-policies` works from anywhere in the tree.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The root file first, a directory-local one second. Later files win, so a
# deliberate .env beside the command still overrides the shared one.
ENV_FILES = (PROJECT_ROOT / ".env", Path(".env"))


class MissingConfiguration(RuntimeError):
    """Required configuration is absent, named plainly rather than as a stack trace."""


class _BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
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
        try:
            return cls()  # pyright: ignore[reportCallIssue]
        except ValidationError as error:
            missing = sorted(
                str(item["loc"][0]).upper()
                for item in error.errors()
                if item["type"] == "missing" and item["loc"]
            )
            if not missing:
                raise
            raise MissingConfiguration(
                f"{cls.__name__} is missing: {', '.join(missing)}.\n"
                f"Set them in the environment, or copy .env.example to "
                f"{PROJECT_ROOT / '.env'} and fill them in."
            ) from error


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

    # Both default to the real thing, so a misconfigured deployment fails loudly
    # instead of quietly answering from a canned model or dropping the reply.
    worker_model_source: ModelSource = "configured"
    worker_slack_sink: SlackSink = "slack"
    worker_fake_fixture: str = "documented"

    slack_bot_token: SecretStr = SecretStr("")


class ApiSettings(_BaseAppSettings):
    """Configuration for the public Slack webhook runtime.

    It verifies Slack signatures, writes to the database, and enqueues work. It
    holds no model credential and no Slack bot token, because it neither calls a
    model nor posts a reply. Only the worker does those.
    """

    database_url: str
    slack_signing_secret: SecretStr

    # Comma separated. A valid Slack signature does not prove the event came
    # from the workspace or channel this deployment serves, so both are checked.
    slack_allowed_team_ids: str = ""
    slack_allowed_channel_ids: str = ""

    # Where the local queue adapter delivers. Cloud Tasks replaces this.
    worker_base_url: str = "http://127.0.0.1:8081"
    worker_task_identity: str = LOCAL_TASK_IDENTITY

    def allowed_team_ids(self) -> frozenset[str]:
        return _split_ids(self.slack_allowed_team_ids)

    def allowed_channel_ids(self) -> frozenset[str]:
        return _split_ids(self.slack_allowed_channel_ids)


def _split_ids(value: str) -> frozenset[str]:
    """Parse a comma separated allowlist.

    Kept as a plain string field rather than a list so a stray space or a
    trailing comma in a deployment variable cannot fail a process at startup.
    """

    return frozenset(item.strip() for item in value.split(",") if item.strip())
