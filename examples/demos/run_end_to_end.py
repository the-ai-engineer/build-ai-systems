"""Drive the whole system locally, from a Slack event to a Slack reply.

    DATABASE_URL=... uv run python -m examples.demos.run_end_to_end

This runs the webhook, the local queue, and the worker in one process so you can
watch a single mention move through every stage. The model and Slack are the
deterministic fakes, so it needs no credentials and sends nothing.

Running them together is a convenience for reading the output, not the shape of
the real system. In production the webhook and worker are separate services, and
`LocalTaskQueue` is replaced by Cloud Tasks. Use `run_worker.py` and a second
process when you want to see that separation.
"""

from __future__ import annotations

import json
import threading
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from support_agent_app.agent.agent import run_support_workflow
from support_agent_app.api.auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SlackSignatureVerifier,
)
from support_agent_app.api.main import create_app as create_webhook
from support_agent_app.application.process_request import WorkerService
from support_agent_app.commands.seed_policies import seed_policy_documents
from support_agent_app.database.repositories.policy_repository import PostgresPolicyRepository
from support_agent_app.database.repositories.support_request_repository import (
    PostgresSupportRepository,
)
from support_agent_app.integrations.task_queue import LocalTaskQueue
from support_agent_app.settings import ApiSettings, WorkerSettings
from support_agent_app.testing.fake_model import fixture_model
from support_agent_app.testing.fake_slack import FakeSlackClient
from support_agent_app.worker.auth import LOCAL_TASK_IDENTITY, TASK_IDENTITY_HEADER
from support_agent_app.worker.main import create_app as create_worker
from uvicorn import Config, Server

SIGNING_SECRET = "synthetic-signing-secret"
TEAM_ID = "T-local"
CHANNEL_ID = "C-local"
QUESTION = "Can unused annual leave be carried into next year?"


def main() -> None:
    try:
        database_url = WorkerSettings.load().database_url
    except Exception as error:
        raise SystemExit("DATABASE_URL is required") from error

    seed_policy_documents(database_url)
    slack = FakeSlackClient()

    print("1. starting the private worker")
    worker, worker_thread, worker_url = _start_worker(database_url, slack)

    print(f"2. starting the local queue, delivering to {worker_url}")
    queue = LocalTaskQueue(
        worker_base_url=worker_url,
        task_identity=LOCAL_TASK_IDENTITY,
        identity_header=TASK_IDENTITY_HEADER,
    )
    queue.start()

    try:
        verifier = SlackSignatureVerifier(SIGNING_SECRET)
        webhook = TestClient(
            create_webhook(
                settings=ApiSettings(
                    database_url=database_url,
                    slack_signing_secret=SIGNING_SECRET,
                    slack_allowed_team_ids=TEAM_ID,
                    slack_allowed_channel_ids=CHANNEL_ID,
                ),
                verifier=verifier,
                requests=PostgresSupportRepository(database_url),
                queue=queue,
            )
        )

        print("3. posting a signed app_mention to the webhook")
        response = _post_mention(webhook, verifier)
        print(f"   webhook answered {response.status_code} without calling a model")

        print("4. waiting for the queue to deliver the request ID to the worker")
        delivered = queue.wait_until_delivered(timeout_seconds=60.0)
        print(f"   delivered: {delivered}")
    finally:
        queue.stop()
        worker.should_exit = True
        worker_thread.join(timeout=10)

    print("5. the reply the employee would see in the thread")
    if not slack.attempts:
        raise SystemExit("no Slack reply was attempted")
    attempt = slack.attempts[0]
    print(f"   channel: {attempt.channel_id}")
    print(f"   thread : {attempt.thread_ts}")
    print("   ---")
    for line in attempt.text.splitlines():
        print(f"   {line}")


def _start_worker(
    database_url: str,
    slack: FakeSlackClient,
) -> tuple[Server, threading.Thread, str]:
    service = WorkerService(
        requests=PostgresSupportRepository(database_url),
        policies=PostgresPolicyRepository(database_url),
        model=fixture_model("documented"),
        slack=slack,
        workflow_runner=run_support_workflow,
    )
    config = Config(
        app=create_worker(service=service),
        host="127.0.0.1",
        port=0,
        log_level="warning",
    )
    server = Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        threading.Event().wait(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, f"http://127.0.0.1:{port}"


def _post_mention(webhook: TestClient, verifier: SlackSignatureVerifier):
    message_ts = "1700000000.000100"
    payload = {
        "type": "event_callback",
        "event_id": f"Ev-local-{uuid4()}",
        "team_id": TEAM_ID,
        "event": {
            "type": "app_mention",
            "channel": CHANNEL_ID,
            "user": "U-employee",
            "ts": message_ts,
            "text": f"<@U08BOTID99> {QUESTION}",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    return webhook.post(
        "/slack/events",
        content=body,
        headers={
            SIGNATURE_HEADER: verifier.signature_for(raw_body=body, timestamp=timestamp),
            TIMESTAMP_HEADER: timestamp,
            "Content-Type": "application/json",
        },
    )


if __name__ == "__main__":
    main()
