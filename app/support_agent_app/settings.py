"""Every environment value the application reads, declared in one place.

Separate classes so each runtime validates only what it needs. The worker needs
a database and a model; the future webhook needs a Slack signing secret and no
model credential at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "google-cloud:gemini-3.5-flash"
LOCAL_TASK_IDENTITY = "local-development-task"

# Two independent switches, because the model and Slack are two separate
# external systems. Coupling them meant "real model, no Slack workspace" was
# impossible, which is the most common local setup there is.
ModelSource = Literal["configured", "fixture"]
SlackSink = Literal["slack", "record"]

# Which queue the webhook hands work to. "local" is the in-process stand-in for
# development; "cloud-tasks" is the deployed one.
TaskQueueBackend = Literal["local", "cloud-tasks"]

# How the worker decides a caller may hand it a task. "google-oidc" verifies a
# Google-signed token from one service account and is the only one that proves
# anything; "static" is the local shared string, for a laptop with no Google
# identity to mint.
TaskAuthMode = Literal["google-oidc", "static"]

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
    authenticate requests without holding a database or model credential.
    """

    # Defaults to the real check, like the worker's other switches, so a
    # deployment that forgets to configure identity refuses to start rather
    # than quietly accepting a shared string from anyone who guesses it.
    worker_task_auth: TaskAuthMode = "google-oidc"

    # The OIDC audience the worker accepts. It is the worker's own base URL,
    # because that is what `api/task_queue.py` puts in the token it mints.
    worker_base_url: str = ""

    # The one identity allowed to enqueue work: the webhook's service account,
    # named by the same variable the webhook itself reads.
    task_oidc_service_account: str = ""

    # Only used when worker_task_auth is "static".
    worker_expected_task_identity: str = LOCAL_TASK_IDENTITY

    worker_deadline_seconds: float = 55.0

    @model_validator(mode="after")
    def _require_oidc_settings(self) -> Self:
        """Fail at startup rather than on the first task."""

        if self.worker_task_auth != "google-oidc":
            return self
        missing = sorted(
            name.upper()
            for name in ("worker_base_url", "task_oidc_service_account")
            if not getattr(self, name)
        )
        if missing:
            raise MissingConfiguration(
                f"WORKER_TASK_AUTH=google-oidc also needs: {', '.join(missing)}.\n"
                f"Set WORKER_TASK_AUTH=static for a local run without a Google identity."
            )
        return self


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

    # Where the queue delivers: the local worker, or the private Cloud Run
    # service. With Cloud Tasks this is also the OIDC audience.
    worker_base_url: str = "http://127.0.0.1:8081"

    # The static identity the local queue sends. Cloud Tasks sends an OIDC
    # token instead, so this is unused once the backend is "cloud-tasks".
    worker_task_identity: str = LOCAL_TASK_IDENTITY

    # Defaults to the local queue, unlike the worker's switches, because the
    # rest of this class already defaults to a worker on localhost. Cloud Tasks
    # has no sensible default project, region, or identity, so a deployment
    # sets all four or the process refuses to start.
    task_queue_backend: TaskQueueBackend = "local"
    task_queue_location: str = ""
    task_queue_name: str = "support-requests"
    google_cloud_project: str = ""

    # The identity Cloud Tasks mints the OIDC token for. It is the webhook's own
    # service account, and it is what the private worker must accept.
    task_oidc_service_account: str = ""

    @model_validator(mode="after")
    def _require_cloud_task_settings(self) -> Self:
        """Fail at startup rather than on the first Slack mention."""

        if self.task_queue_backend != "cloud-tasks":
            return self
        missing = sorted(
            name.upper()
            for name in ("google_cloud_project", "task_queue_location", "task_oidc_service_account")
            if not getattr(self, name)
        )
        if missing:
            raise MissingConfiguration(
                f"TASK_QUEUE_BACKEND=cloud-tasks also needs: {', '.join(missing)}."
            )
        return self

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
