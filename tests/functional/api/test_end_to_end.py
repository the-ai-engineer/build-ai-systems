"""The whole chain, in one test: Slack event in, Slack reply out.

The webhook, the queue, and the worker run as three separate pieces against a
real Postgres, wired the way `api/main.py` and `worker/main.py` wire them. Only
the model and Slack are fakes, because those are the two boundaries the course
deliberately cannot call from a test.
"""

from __future__ import annotations

import json
import threading

from fastapi.testclient import TestClient
from pydantic import SecretStr
from support_agent_app.api.auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SlackSignatureVerifier,
)
from support_agent_app.api.main import create_app as create_webhook
from support_agent_app.api.task_queue import LocalTaskQueue
from support_agent_app.commands.seed_policies import seed_policy_documents
from support_agent_app.database.repositories.policy_repository import PostgresPolicyRepository
from support_agent_app.database.repositories.support_request_repository import (
    PostgresSupportRepository,
)
from support_agent_app.settings import ApiSettings, WorkerBoundarySettings
from support_agent_app.testing.fake_model import fixture_model
from support_agent_app.testing.fake_slack import FakeSlackClient
from support_agent_app.worker.agent.agent import run_support_workflow
from support_agent_app.worker.auth import LOCAL_TASK_IDENTITY, TASK_IDENTITY_HEADER
from support_agent_app.worker.deadlines import DEFAULT_WORKER_DEADLINE_SECONDS
from support_agent_app.worker.main import create_app as create_worker
from support_agent_app.worker.process_request import WorkerService
from uvicorn import Config, Server

from tests.fakes.postgres_test_case import PostgresTestCase

SECRET = "synthetic-signing-secret"
NOW = 1_700_000_000
TEAM = "T-e2e"
CHANNEL = "C-e2e"


class EndToEndTests(PostgresTestCase):
    def setUp(self) -> None:
        super().setUp()
        seed_policy_documents(self.database_url)
        self.slack = FakeSlackClient()

    def start_worker(self) -> tuple[Server, threading.Thread, str]:
        service = WorkerService(
            requests=PostgresSupportRepository(self.database_url),
            policies=PostgresPolicyRepository(self.database_url),
            model=fixture_model("documented"),
            slack=self.slack,
            workflow_runner=run_support_workflow,
        )
        config = Config(
            app=create_worker(
                service=service,
                # The local identity check, chosen explicitly: the deployed
                # default is Google OIDC and there is no Google identity here.
                boundary_settings=WorkerBoundarySettings(
                    worker_task_auth="static",
                    worker_base_url="http://127.0.0.1:8081",
                    worker_expected_task_identity=LOCAL_TASK_IDENTITY,
                    worker_deadline_seconds=DEFAULT_WORKER_DEADLINE_SECONDS,
                ),
                deadline_seconds=DEFAULT_WORKER_DEADLINE_SECONDS,
            ),
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

    def test_a_slack_mention_becomes_a_cited_thread_reply(self) -> None:
        server, thread, worker_url = self.start_worker()
        verifier = SlackSignatureVerifier(SECRET, clock=lambda: NOW)
        queue = LocalTaskQueue(
            worker_base_url=worker_url,
            task_identity=LOCAL_TASK_IDENTITY,
            identity_header=TASK_IDENTITY_HEADER,
        )
        queue.start()
        try:
            webhook = TestClient(
                create_webhook(
                    settings=ApiSettings(
                        database_url=self.database_url,
                        slack_signing_secret=SecretStr(SECRET),
                        slack_allowed_team_ids=TEAM,
                        slack_allowed_channel_ids=CHANNEL,
                        worker_base_url=worker_url,
                        worker_task_identity=LOCAL_TASK_IDENTITY,
                        task_queue_backend="local",
                        task_queue_name="support-requests",
                    ),
                    verifier=verifier,
                    requests=PostgresSupportRepository(self.database_url),
                    queue=queue,
                )
            )
            payload = {
                "type": "event_callback",
                "event_id": "Ev-e2e-1",
                "team_id": TEAM,
                "event": {
                    "type": "app_mention",
                    "channel": CHANNEL,
                    "user": "U-employee",
                    "ts": "1700000000.000100",
                    "text": ("<@U08BOTID99> Can unused annual leave be carried into next year?"),
                },
            }
            body = json.dumps(payload).encode("utf-8")
            response = webhook.post(
                "/slack/events",
                content=body,
                headers={
                    SIGNATURE_HEADER: verifier.signature_for(raw_body=body, timestamp=str(NOW)),
                    TIMESTAMP_HEADER: str(NOW),
                    "Content-Type": "application/json",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(queue.wait_until_delivered(timeout_seconds=30.0))
        finally:
            queue.stop()
            server.should_exit = True
            thread.join(timeout=10)

        # The employee got one cited reply in their own thread.
        self.assertEqual(len(self.slack.attempts), 1)
        attempt = self.slack.attempts[0]
        self.assertEqual(attempt.channel_id, CHANNEL)
        self.assertEqual(attempt.thread_ts, "1700000000.000100")
        self.assertIn("annual-leave-policy.md", attempt.text)

        row = self.fetchone(
            """
            select status, confirmed_task_name, business_attempt_count
            from support_requests where slack_event_id = %s
            """,
            ("Ev-e2e-1",),
        )
        assert row is not None
        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["confirmed_task_name"])
        self.assertEqual(row["business_attempt_count"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
