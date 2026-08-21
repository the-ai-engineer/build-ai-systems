"""Google Cloud ADK model construction, kept out of the agent's logic."""

from __future__ import annotations

from dataclasses import dataclass

from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini

from ..settings import ModelProviderSettings

# Agent Platform defaults to pay-as-you-go routing when no service tier is sent.
# Keep that default's billing label separate from the provider request: the
# Enterprise API rejects the Gen AI SDK's explicit ``standard`` enum value.
GOOGLE_CLOUD_SERVICE_TIER = "standard"


@dataclass(frozen=True)
class ModelSelection:
    """The ADK model and the safe metadata recorded for each run."""

    model: BaseLlm | str
    model_id: str
    location: str
    service_tier: str


def create_google_cloud_model(
    model_id: str | None = None,
    *,
    settings: ModelProviderSettings | None = None,
) -> ModelSelection:
    """Build Gemini through Google Cloud Agent Platform using ADC."""

    resolved_settings = settings or ModelProviderSettings.load()
    resolved_id = model_id or resolved_settings.model_name
    if not resolved_id.startswith("gemini-"):
        raise ValueError("The configured ADK model must be a Gemini model")

    project = resolved_settings.google_cloud_project
    location = resolved_settings.google_cloud_location
    if not project or not location:
        raise ValueError("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required")

    model = Gemini(
        model=resolved_id,
        client_kwargs={
            "enterprise": True,
            "project": project,
            "location": location,
        },
    )
    return ModelSelection(
        model=model,
        model_id=resolved_id,
        location=location,
        service_tier=GOOGLE_CLOUD_SERVICE_TIER,
    )
