"""Agentic search over complete policy documents stored in PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import os

from google.adk.runners import InMemoryRunner

from policy_agent.agent import root_agent


async def agentic_search(question: str) -> str:
    runner = InMemoryRunner(agent=root_agent, app_name="policy_agent")
    try:
        events = await runner.run_debug(question, quiet=True)
    finally:
        await runner.close()

    for event in reversed(events):
        if event.is_final_response() and event.content is not None:
            return "".join(part.text or "" for part in event.content.parts or [])
    raise RuntimeError("ADK finished without a final response.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Let an agent choose and read a policy.")
    parser.add_argument(
        "question",
        nargs="?",
        default="How many days of annual leave can I carry into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        raise RuntimeError("Set GOOGLE_CLOUD_PROJECT in examples/.env before running this command.")

    print(asyncio.run(agentic_search(args.question)))


if __name__ == "__main__":
    main()
