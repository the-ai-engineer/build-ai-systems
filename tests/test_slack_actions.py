from __future__ import annotations

import unittest

import httpx

from support_agent_app.domain import AnswerDecision, HumanReviewDecision, SourceCitation
from support_agent_app.slack_actions import (
    HUMAN_REVIEW_REPLY,
    FakeSlackClient,
    SlackSendError,
    SlackWebApiClient,
    format_slack_reply,
)


class SlackActionTests(unittest.TestCase):
    def test_supported_reply_contains_answer_and_source_filenames(self) -> None:
        decision = AnswerDecision(
            answer="You may carry five days with approval.",
            reason="The policy supports it.",
            sources=(
                SourceCitation(
                    document_id="annual-leave-policy",
                    title="Annual Leave Policy",
                    source_filename="annual-leave-policy.md",
                    document_revision="sha256:synthetic",
                    supporting_excerpt="Synthetic verified excerpt.",
                ),
            ),
        )

        reply = format_slack_reply(decision)

        self.assertEqual(
            reply,
            "You may carry five days with approval.\n\nSources\n- annual-leave-policy.md",
        )

    def test_human_review_reply_is_fixed_and_tags_nobody(self) -> None:
        decision = HumanReviewDecision(
            reason="The request is unsupported.",
            reason_code="unsupported",
        )

        reply = format_slack_reply(decision)

        self.assertEqual(reply, HUMAN_REVIEW_REPLY)
        self.assertNotIn("<@", reply)
        self.assertNotIn("<!subteam", reply)

    def test_fake_slack_records_one_thread_attempt(self) -> None:
        slack = FakeSlackClient()

        message_ts = slack.post_thread_reply(
            channel_id="C-test",
            thread_ts="100.001",
            text="Synthetic reply.",
            timeout_seconds=3.0,
        )

        self.assertEqual(message_ts, "900.001")
        self.assertEqual(len(slack.attempts), 1)
        self.assertEqual(slack.attempts[0].channel_id, "C-test")
        self.assertEqual(slack.attempts[0].thread_ts, "100.001")

    def test_real_adapter_classifies_a_clear_slack_rejection(self) -> None:
        def reject(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"ok": False, "error": "not_allowed"})

        client = httpx.Client(
            base_url="https://slack.com/api",
            transport=httpx.MockTransport(reject),
        )
        slack = SlackWebApiClient("synthetic-token", client=client)

        with self.assertRaises(SlackSendError) as raised:
            slack.post_thread_reply(
                channel_id="C-test",
                thread_ts="100.001",
                text="Synthetic reply.",
                timeout_seconds=3.0,
            )

        self.assertFalse(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
