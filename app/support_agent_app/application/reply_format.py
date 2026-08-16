"""Turn a verified decision into the exact text sent to Slack.

Only a validated decision reaches this function, never raw model output.
"""

from __future__ import annotations

from .domain import SupportDecision

HUMAN_REVIEW_REPLY = (
    "I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team."
)
OFF_TOPIC_REPLY = "I can only help with questions about company HR policies."


def format_slack_reply(decision: SupportDecision) -> str:
    """Format only a validated decision, never raw model output."""

    if decision.decision == "human_review":
        if decision.reason_code == "off_topic":
            return OFF_TOPIC_REPLY
        return HUMAN_REVIEW_REPLY

    source_lines = "\n".join(f"- {source.source_filename}" for source in decision.sources)
    return f"{decision.answer}\n\nSources\n{source_lines}"
