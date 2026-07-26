from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from support_agent_app.api import app, slack_app
from support_agent_app.integrations.slack import post_slack_message, verify_slack_signature

SIGNING_SECRET = "test-signing-secret"
BOT_TOKEN = "xoxb-test-token"


def signed_headers(body: bytes, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    base_string = b"v0:" + timestamp.encode("utf-8") + b":" + body
    signature = "v0=" + hmac.new(
        SIGNING_SECRET.encode("utf-8"),
        base_string,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/json",
    }


class SlackSignatureTest(unittest.TestCase):
    def test_accepts_a_valid_recent_signature(self) -> None:
        body = b'{"type":"event_callback"}'
        now = 1_700_000_000
        timestamp = str(now)
        headers = signed_headers(body, timestamp)

        self.assertTrue(
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=headers["X-Slack-Signature"],
                signing_secret=SIGNING_SECRET,
                now=now,
            )
        )

    def test_rejects_a_stale_signature(self) -> None:
        body = b'{"type":"event_callback"}'
        timestamp = "1699999000"
        headers = signed_headers(body, timestamp)

        self.assertFalse(
            verify_slack_signature(
                body=body,
                timestamp=timestamp,
                signature=headers["X-Slack-Signature"],
                signing_secret=SIGNING_SECRET,
                now=1_700_000_000,
            )
        )


class SlackWebApiTest(unittest.TestCase):
    @patch("support_agent_app.integrations.slack.urlopen")
    def test_posts_a_threaded_message_with_the_bot_token(self, urlopen) -> None:
        response = MagicMock()
        response.read.return_value = b'{"ok":true}'
        urlopen.return_value.__enter__.return_value = response

        post_slack_message(
            bot_token=BOT_TOKEN,
            channel="C123",
            text="Echo: hello",
            thread_ts="1700000000.000100",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2)
        self.assertEqual(request.full_url, "https://slack.com/api/chat.postMessage")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {BOT_TOKEN}")
        self.assertEqual(
            json.loads(request.data),
            {
                "channel": "C123",
                "text": "Echo: hello",
                "thread_ts": "1700000000.000100",
            },
        )

    @patch("support_agent_app.integrations.slack.urlopen")
    def test_raises_when_slack_rejects_the_message(self, urlopen) -> None:
        response = MagicMock()
        response.read.return_value = b'{"ok":false,"error":"invalid_auth"}'
        urlopen.return_value.__enter__.return_value = response

        with self.assertRaisesRegex(RuntimeError, "invalid_auth"):
            post_slack_message(
                bot_token=BOT_TOKEN,
                channel="C123",
                text="Echo: hello",
                thread_ts="1700000000.000100",
            )


class SlackEventsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.env_patcher = patch.dict(
            os.environ,
            {
                "SLACK_SIGNING_SECRET": SIGNING_SECRET,
                "SLACK_BOT_TOKEN": BOT_TOKEN,
            },
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def post_event(self, payload: dict[str, object], headers: dict[str, str] | None = None):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self.client.post(
            "/slack/events",
            content=body,
            headers=headers or signed_headers(body),
        )

    def test_answers_slack_url_verification(self) -> None:
        response = self.post_event(
            {
                "type": "url_verification",
                "challenge": "course-challenge",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"challenge": "course-challenge"})

    def test_rejects_an_invalid_signature(self) -> None:
        response = self.post_event(
            {"type": "event_callback", "event": {}},
            headers={
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid",
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(response.status_code, 401)

    @patch("support_agent_app.api.post_slack_message")
    def test_echoes_an_app_mention_in_the_same_thread(self, post_message) -> None:
        response = self.post_event(
            {
                "type": "event_callback",
                "event_id": "Ev123",
                "event": {
                    "type": "app_mention",
                    "user": "U123",
                    "text": "<@U999> hello factory",
                    "channel": "C123",
                    "ts": "1700000000.000100",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        post_message.assert_called_once_with(
            bot_token=BOT_TOKEN,
            channel="C123",
            text="Echo: hello factory",
            thread_ts="1700000000.000100",
        )

    @patch("support_agent_app.api.post_slack_message")
    def test_echoes_a_direct_message_in_the_same_thread(self, post_message) -> None:
        response = self.post_event(
            {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "user": "U123",
                    "text": "hello assistant",
                    "channel": "D123",
                    "channel_type": "im",
                    "ts": "1700000000.000150",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        post_message.assert_called_once_with(
            bot_token=BOT_TOKEN,
            channel="D123",
            text="Echo: hello assistant",
            thread_ts="1700000000.000150",
        )

    @patch("support_agent_app.api.post_slack_message")
    def test_ignores_bot_messages(self, post_message) -> None:
        response = self.post_event(
            {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "subtype": "bot_message",
                    "bot_id": "B123",
                    "text": "Echo: hello",
                    "channel": "C123",
                    "channel_type": "im",
                    "ts": "1700000000.000200",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        post_message.assert_not_called()

    def test_requires_a_bot_token_before_accepting_a_user_message(self) -> None:
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": ""}):
            response = self.post_event(
                {
                    "type": "event_callback",
                    "event": {
                        "type": "app_mention",
                        "text": "<@U999> hello",
                        "channel": "C123",
                        "ts": "1700000000.000300",
                    },
                }
            )

        self.assertEqual(response.status_code, 503)

    def test_rejects_a_message_with_missing_required_fields(self) -> None:
        response = self.post_event(
            {
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "text": "<@U999> hello",
                    "channel": "C123",
                },
            }
        )

        self.assertEqual(response.status_code, 400)


class SlackPublicAppTest(unittest.TestCase):
    def test_does_not_expose_the_local_support_email_endpoint(self) -> None:
        client = TestClient(slack_app)

        response = client.post(
            "/support-email",
            json={
                "sender": "student@example.com",
                "subject": "Question",
                "body": "Can I return this?",
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_slack_container_starts_only_the_public_slack_app(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        dockerfile = (repo_root / "Dockerfile.slack").read_text()

        self.assertIn("support_agent_app.api:slack_app", dockerfile)
        self.assertNotIn("support_agent_app.api:app\"", dockerfile)
