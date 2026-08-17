"""Google Cloud model construction, kept out of the agent's own logic.

The agent knows it needs a model. Only this module knows the provider is Google
Cloud and that credentials arrive through Application Default Credentials.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from ..settings import ModelProviderSettings

GOOGLE_CLOUD_PREFIX = "google-cloud:"


def create_google_cloud_model(
    model_id: str | None = None,
    *,
    settings: ModelProviderSettings | None = None,
) -> Model:
    """Build the configured Google Cloud model with explicit ADC selection."""

    resolved_settings = settings or ModelProviderSettings.load()
    resolved_id = model_id or resolved_settings.model_name
    if not resolved_id.startswith(GOOGLE_CLOUD_PREFIX):
        raise ValueError(f"Model must use the {GOOGLE_CLOUD_PREFIX} provider prefix")

    if not resolved_settings.google_cloud_project or not resolved_settings.google_cloud_location:
        raise ValueError("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required")

    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google_cloud import GoogleCloudProvider

    provider = GoogleCloudProvider(
        project=resolved_settings.google_cloud_project,
        location=resolved_settings.google_cloud_location,
    )
    return GoogleModel(resolved_id.removeprefix(GOOGLE_CLOUD_PREFIX), provider=provider)
