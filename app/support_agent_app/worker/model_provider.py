"""Google Cloud model construction, kept out of the agent's own logic.

The agent knows it needs a model. Only this module knows the provider is Google
Cloud, that credentials arrive through Application Default Credentials, and
which service tier the request asks for.

That last one matters more than it looks. The tier the request asks for and the
tier written into the run record must be the same value, or the cost estimate
prices a request that never happened. So it is defined once, here, and travels
with the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.models import Model

from ..settings import ModelProviderSettings

GOOGLE_CLOUD_PREFIX = "google-cloud:"

# The pay-as-you-go tier. This value is both sent to the provider and recorded
# in the run, and must match a `service_tier` in the price table.
GOOGLE_CLOUD_SERVICE_TIER = "on_demand"


@dataclass(frozen=True)
class ModelSelection:
    """A model, plus everything the run record needs in order to describe it.

    Returned instead of a tuple so a caller cannot silently swap two of the
    strings, which all describe the model but mean different things.
    """

    model: Model | str
    model_id: str
    location: str
    service_tier: str
    provider_settings: dict[str, Any] = field(default_factory=dict)


def create_google_cloud_model(
    model_id: str | None = None,
    *,
    settings: ModelProviderSettings | None = None,
) -> ModelSelection:
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
    return ModelSelection(
        model=GoogleModel(resolved_id.removeprefix(GOOGLE_CLOUD_PREFIX), provider=provider),
        model_id=resolved_id,
        location=resolved_settings.google_cloud_location,
        service_tier=GOOGLE_CLOUD_SERVICE_TIER,
        provider_settings={"google_cloud_service_tier": GOOGLE_CLOUD_SERVICE_TIER},
    )
