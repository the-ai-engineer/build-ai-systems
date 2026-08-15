"""Run one stored synthetic request through the complete local worker."""

from __future__ import annotations

import argparse
import os
from typing import Literal
from uuid import uuid4

from .fake_model import fixture_model
from .fixtures import FIXTURE_QUESTIONS
from .migrations import apply_migrations
from .repositories import PostgresPolicyRepository
from .request_repository import IncomingSupportRequest, PostgresSupportRepository
from .seed_policies import seed_policy_documents
from .slack_actions import FakeSlackClient
from .worker_service import DEFAULT_WORKER_DEADLINE_SECONDS, WorkerDeadline, WorkerService


WorkerFixture = Literal["documented", "human-review", "uncertain-send"]
FIXTURES: tuple[WorkerFixture, ...] = ("documented", "human-review", "uncertain-send")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local stored-request worker.")
    parser.add_argument("--fixture", choices=FIXTURES, default="documented")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    fixture: WorkerFixture = args.fixture
    model_fixture = "unsupported" if fixture == "human-review" else "documented"
    slack_behavior = "uncertain" if fixture == "uncertain-send" else "success"

    apply_migrations(database_url)
    seed_policy_documents(database_url)
    requests = PostgresSupportRepository(database_url)
    accepted = requests.accept_request(
        IncomingSupportRequest(
            slack_event_id=f"Ev-worker-demo-{uuid4()}",
            slack_team_id="T-demo",
            slack_channel_id="C-demo",
            slack_message_ts="700.001",
            slack_thread_ts="700.001",
            slack_user_id="U-demo",
            question_text=FIXTURE_QUESTIONS[model_fixture].text,
        )
    )
    requests.mark_queued(accepted.request_id)

    slack = FakeSlackClient(slack_behavior)
    service = WorkerService(
        requests=requests,
        policies=PostgresPolicyRepository(database_url),
        model=fixture_model(model_fixture),
        slack=slack,
    )
    result = service.process(
        accepted.request_id,
        WorkerDeadline.after(DEFAULT_WORKER_DEADLINE_SECONDS),
    )

    print(f"request_id: {result.request_id}")
    print(f"outcome: {result.outcome}")
    print(f"send_attempts: {len(slack.attempts)}")
    if fixture != "uncertain-send" and slack.attempts:
        print("fake Slack thread reply:")
        print(slack.attempts[0].text)


if __name__ == "__main__":
    main()
