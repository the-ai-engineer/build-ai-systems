"""Load and render the versioned instructions for the HR policy agent.

The prompt text is a package resource so it is readable on its own and ships in
the same wheel as the worker. Values enforced by code are still substituted
from their canonical constants instead of being copied into prose.
"""

from __future__ import annotations

from importlib.resources import files
from string import Template

from .tools import MAX_LOADED_DOCUMENTS

PROMPT_TEMPLATE = (
    files("support_agent_app.worker.agent")
    .joinpath("prompts", "support_agent.txt")
    .read_text(encoding="utf-8")
)


def build_instructions(max_documents: int = MAX_LOADED_DOCUMENTS) -> str:
    """Render instructions from the values the application enforces."""

    return Template(PROMPT_TEMPLATE).substitute(max_documents=max_documents)


INSTRUCTIONS = build_instructions()
