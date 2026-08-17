"""Reproducible model-cost estimates from versioned token prices."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...application.domain import AgentRunRecord

DEFAULT_PRICING_PATH = Path(__file__).with_name("prices") / "2026-08-14.json"


class ModelPrice(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    location_class: str
    service_tier: str
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal


class PriceConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    effective_date: str
    currency: Literal["USD"]
    source_url: str
    prices: tuple[ModelPrice, ...]


def load_price_configuration(path: Path = DEFAULT_PRICING_PATH) -> PriceConfiguration:
    return PriceConfiguration.model_validate(json.loads(path.read_text(encoding="utf-8")))


def estimate_run_cost(run: AgentRunRecord, prices: PriceConfiguration) -> Decimal:
    location_class = "global" if run.model_location == "global" else run.model_location
    if run.model_location not in {"global", "local"}:
        location_class = "non-global"
    price = next(
        (
            item
            for item in prices.prices
            if item.model_id == run.model_id
            and item.location_class == location_class
            and item.service_tier == run.service_tier
        ),
        None,
    )
    if price is None:
        raise ValueError(
            "No price is configured for "
            f"{run.model_id} in {location_class} at {run.service_tier} tier"
        )
    input_cost = Decimal(run.input_tokens) * price.input_usd_per_million_tokens
    output_cost = Decimal(run.output_tokens) * price.output_usd_per_million_tokens
    return (input_cost + output_cost) / Decimal(1_000_000)
