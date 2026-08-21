"""Run the Lesson 05 PostgreSQL policy agent from the command line."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner

from policy_agent.agent import DEFAULT_DATABASE_URL, build_agent


async def run_agent(question: str, database_url: str) -> str:
    runner = InMemoryRunner(agent=build_agent(database_url), app_name="policy_agent")
    try:
        events = await runner.run_debug(question, quiet=True)
    finally:
        await runner.close()
    for event in reversed(events):
        if event.is_final_response() and event.content is not None:
            return "".join(part.text or "" for part in event.content.parts or [])
    raise RuntimeError("ADK finished without a final response.")


def main() -> None:
    load_dotenv(Path(__file__).parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Let an agent choose and read a policy.")
    parser.add_argument(
        "question",
        nargs="?",
        default="How many days of annual leave can I carry into next year?",
    )
    args = parser.parse_args()

    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        raise RuntimeError("Set GOOGLE_CLOUD_PROJECT in examples/.env before running this command.")

    database_url = os.getenv("RAG_DATABASE_URL", DEFAULT_DATABASE_URL)
    print(asyncio.run(run_agent(args.question, database_url)))


if __name__ == "__main__":
    main()
