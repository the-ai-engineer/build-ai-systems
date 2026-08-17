from __future__ import annotations

import unittest

from support_agent_app.api.main import (
    UnsupportedEvent,
    normalize_app_mention,
    strip_mentions,
)

TEAMS = frozenset({"T-allowed"})
CHANNELS = frozenset({"C-allowed"})


def mention(**overrides) -> dict:
    event = {
        "type": "app_mention",
        "channel": "C-allowed",
        "user": "U-employee",
        "ts": "1700000000.000100",
        "text": "<@U08BOTID99> Can unused annual leave be carried into next year?",
    }
    event.update(overrides.pop("event", {}))
    payload = {
        "type": "event_callback",
        "event_id": "Ev-1",
        "team_id": "T-allowed",
        "event": event,
    }
    payload.update(overrides)
    return payload


def normalize(payload: dict):
    return normalize_app_mention(
        payload,
        allowed_team_ids=TEAMS,
        allowed_channel_ids=CHANNELS,
    )


class MentionNormalizationTests(unittest.TestCase):
    def test_normalizes_a_top_level_mention_into_its_own_thread(self) -> None:
        incoming = normalize(mention())

        self.assertEqual(incoming.slack_event_id, "Ev-1")
        self.assertEqual(incoming.slack_channel_id, "C-allowed")
        self.assertEqual(incoming.slack_user_id, "U-employee")
        self.assertEqual(
            incoming.question_text,
            "Can unused annual leave be carried into next year?",
        )
        # A top-level mention starts the thread it will be answered in.
        self.assertEqual(incoming.slack_thread_ts, incoming.slack_message_ts)

    def test_keeps_the_thread_root_for_a_mention_inside_a_thread(self) -> None:
        incoming = normalize(mention(event={"thread_ts": "1699999999.000001"}))

        self.assertEqual(incoming.slack_thread_ts, "1699999999.000001")
        self.assertEqual(incoming.slack_message_ts, "1700000000.000100")

    def test_strips_every_mention_form_from_the_question(self) -> None:
        self.assertEqual(strip_mentions("<@U024BE7LH> hello <@W456ABC|name> there"), "hello there")
        self.assertEqual(strip_mentions("<@U024BE7LH>"), "")

    def test_rejects_events_from_another_workspace_or_channel(self) -> None:
        with self.assertRaises(UnsupportedEvent):
            normalize(mention(team_id="T-other"))
        with self.assertRaises(UnsupportedEvent):
            normalize(mention(event={"channel": "C-other"}))

    def test_rejects_bot_authored_events(self) -> None:
        with self.assertRaises(UnsupportedEvent):
            normalize(mention(event={"bot_id": "B-self"}))
        with self.assertRaises(UnsupportedEvent):
            normalize(mention(event={"subtype": "bot_message"}))

    def test_rejects_unsupported_shapes(self) -> None:
        cases = {
            "wrong payload type": mention(type="something_else"),
            "wrong event type": mention(event={"type": "message"}),
            "missing event_id": mention(event_id=""),
            "missing team_id": mention(team_id=""),
            "missing user": mention(event={"user": ""}),
            "missing text": mention(event={"text": None}),
            "mention with no question": mention(event={"text": "<@U08BOTID99>   "}),
        }
        for name, payload in cases.items():
            with self.subTest(name):
                with self.assertRaises(UnsupportedEvent):
                    normalize(payload)

    def test_truncates_an_overlong_question(self) -> None:
        incoming = normalize(mention(event={"text": "<@U08BOTID99> " + "a" * 3_000}))

        self.assertEqual(len(incoming.question_text), 2_000)


if __name__ == "__main__":
    unittest.main()
