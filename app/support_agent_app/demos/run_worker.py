"""Run one stored synthetic request through the complete local worker.

DATABASE_URL=... uv run demo-worker --fixture documented
"""

from __future__ import annotations

import argparse
from typing import Literal
from uuid import uuid4

from support_agent_app.application.lifecycle import IncomingSupportRequest
from support_agent_app.commands.seed_policies import seed_policy_documents
from support_agent_app.database.repositories.policy_repository import PostgresPolicyRepository
from support_agent_app.database.repositories.support_request_repository import (
    PostgresSupportRepository,
)
from support_agent_app.settings import WorkerSettings
from support_agent_app.testing.fake_model import fixture_model
from support_agent_app.testing.fake_slack import FakeSlackClient
from support_agent_app.testing.fixtures import FIXTURE_QUESTIONS
from support_agent_app.worker.agent.agent import run_support_workflow
from support_agent_app.worker.deadlines import (
    DEFAULT_WORKER_DEADLINE_SECONDS,
    WorkerDeadline,
)
from support_agent_app.worker.process_request import WorkerService

WorkerFixture = Literal["documented", "human-review", "uncertain-send"]
FIXTURES: tuple[WorkerFixture, ...] = ("documented", "human-review", "uncertain-send")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local stored-request worker.")
    parser.add_argument("--fixture", choices=FIXTURES, default="documented")
    parser.add_argument(
        "--question",
        default=None,
        help="Store your own question instead of the fixture's.",
    )
    parser.add_argument(
        "--live-model",
        action="store_true",
        help="Use the configured Google Cloud model instead of the deterministic fake.",
    )
    args = parser.parse_args()

    try:
        database_url = WorkerSettings.load().database_url
    except Exception as error:
        raise SystemExit("DATABASE_URL is required") from error

    fixture: WorkerFixture = args.fixture
    model_fixture = "unsupported" if fixture == "human-review" else "documented"
    slack_behavior = "uncertain" if fixture == "uncertain-send" else "success"
    question_text = args.question or FIXTURE_QUESTIONS[model_fixture].text
    if args.question and not args.live_model:
        print(
            "warning: the fixture model returns a canned decision and ignores your question.\n"
            "         add --live-model to actually ask it.\n"
        )

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
            question_text=question_text,
        )
    )
    requests.mark_queued(accepted.request_id)

    slack = FakeSlackClient(slack_behavior)
    service = WorkerService(
        requests=requests,
        policies=PostgresPolicyRepository(database_url),
        model=None if args.live_model else fixture_model(model_fixture),
        slack=slack,
        workflow_runner=run_support_workflow,
    )
    result = service.process(
        accepted.request_id,
        WorkerDeadline.after(DEFAULT_WORKER_DEADLINE_SECONDS),
    )

    print(f"question: {question_text}")
    print(f"request_id: {result.request_id}")
    print(f"outcome: {result.outcome}")
    print(f"send_attempts: {len(slack.attempts)}")
    if fixture != "uncertain-send" and slack.attempts:
        print("fake Slack thread reply:")
        print(slack.attempts[0].text)


if __name__ == "__main__":
    main()
