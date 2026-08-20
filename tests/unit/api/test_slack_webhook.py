from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient
from pydantic import SecretStr
from support_agent_app.api.auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SlackSignatureVerifier,
)
from support_agent_app.api.main import create_app
from support_agent_app.settings import ApiSettings

from tests.fakes.intake import FakeIntake, FakeQueue

SECRET = "synthetic-signing-secret"
NOW = 1_700_000_000


def settings() -> ApiSettings:
    return ApiSettings(
        database_url="postgresql://unused",
        slack_signing_secret=SecretStr(SECRET),
        slack_allowed_team_ids="T-allowed",
        slack_allowed_channel_ids="C-allowed",
        worker_base_url="http://127.0.0.1:8081",
        worker_task_identity="local-development-task",
        task_queue_backend="local",
        task_queue_name="support-requests",
    )


def mention_payload(event_id: str = "Ev-1", **event_overrides) -> dict:
    event = {
        "type": "app_mention",
        "channel": "C-allowed",
        "user": "U-employee",
        "ts": "1700000000.000100",
        "text": "<@U08BOTID99> Can unused annual leave be carried into next year?",
    }
    event.update(event_overrides)
    return {
        "type": "event_callback",
        "event_id": event_id,
        "team_id": "T-allowed",
        "event": event,
    }


class SlackWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests = FakeIntake()
        self.queue = FakeQueue()
        self.verifier = SlackSignatureVerifier(SECRET, clock=lambda: NOW)
        self.client = TestClient(
            create_app(
                settings=settings(),
                verifier=self.verifier,
                requests=self.requests,
                queue=self.queue,
            )
        )

    def post(self, payload: dict, *, sign: bool = True, timestamp: str = str(NOW)):
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if sign:
            headers[SIGNATURE_HEADER] = self.verifier.signature_for(
                raw_body=body, timestamp=timestamp
            )
            headers[TIMESTAMP_HEADER] = timestamp
        return self.client.post("/slack/events", content=body, headers=headers)

    def test_accepts_a_signed_mention_and_queues_it(self) -> None:
        response = self.post(mention_payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.queue.names), 1)
        self.assertEqual(len(self.requests.by_event_id), 1)

    def test_rejects_an_unsigned_request_before_doing_any_work(self) -> None:
        response = self.post(mention_payload(), sign=False)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.requests.accepted, [])
        self.assertEqual(self.queue.names, [])

    def test_answers_the_url_verification_challenge(self) -> None:
        response = self.post({"type": "url_verification", "challenge": "abc123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "abc123")
        self.assertEqual(self.requests.accepted, [])

    def test_acknowledges_events_it_will_never_act_on(self) -> None:
        """2xx stops Slack retrying something this app deliberately ignores."""
        ignored = {
            "a message that is not a mention": mention_payload(type="message"),
            "a mention in another channel": mention_payload(channel="C-other"),
            "the bot's own message": mention_payload(bot_id="B-self"),
        }
        for name, payload in ignored.items():
            with self.subTest(name):
                self.assertEqual(self.post(payload).status_code, 200)

        self.assertEqual(self.queue.names, [])
        self.assertEqual(self.requests.accepted, [])

    def test_a_slack_retry_does_not_create_a_second_task(self) -> None:
        first = self.post(mention_payload())
        replay = self.post(mention_payload())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(len(self.requests.by_event_id), 1)
        self.assertEqual(len(self.queue.names), 1)

    def test_returns_503_when_the_queue_refuses_so_slack_retries(self) -> None:
        client = TestClient(
            create_app(
                settings=settings(),
                verifier=self.verifier,
                requests=self.requests,
                queue=FakeQueue(fail_with=RuntimeError("queue down")),
            )
        )
        body = json.dumps(mention_payload()).encode("utf-8")
        response = client.post(
            "/slack/events",
            content=body,
            headers={
                SIGNATURE_HEADER: self.verifier.signature_for(raw_body=body, timestamp=str(NOW)),
                TIMESTAMP_HEADER: str(NOW),
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(response.status_code, 503)
        # Stored anyway, so the retry converges instead of starting over.
        self.assertEqual(len(self.requests.by_event_id), 1)

    def test_rejects_a_malformed_body_that_carries_a_valid_signature(self) -> None:
        body = b"not json"
        response = self.client.post(
            "/slack/events",
            content=body,
            headers={
                SIGNATURE_HEADER: self.verifier.signature_for(raw_body=body, timestamp=str(NOW)),
                TIMESTAMP_HEADER: str(NOW),
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
