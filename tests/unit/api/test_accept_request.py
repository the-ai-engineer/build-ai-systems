from __future__ import annotations

import unittest

from support_agent_app.api.accept_request import (
    RequestNotQueuedError,
    accept_and_queue,
)
from support_agent_app.application.lifecycle import IncomingSupportRequest, task_name_for

from tests.fakes.intake import FakeIntake, FakeQueue


def incoming(event_id: str = "Ev-1") -> IncomingSupportRequest:
    return IncomingSupportRequest(
        slack_event_id=event_id,
        slack_team_id="T-test",
        slack_channel_id="C-test",
        slack_message_ts="100.001",
        slack_thread_ts="100.001",
        slack_user_id="U-test",
        question_text="A synthetic policy question.",
    )


class AcceptRequestTests(unittest.TestCase):
    def test_stores_then_queues_and_confirms_the_task_name(self) -> None:
        requests, queue = FakeIntake(), FakeQueue()

        accepted = accept_and_queue(incoming(), requests=requests, queue=queue)

        self.assertTrue(accepted.created)
        self.assertFalse(accepted.already_queued)
        self.assertEqual(queue.request_ids, [accepted.request_id])
        self.assertEqual(queue.names, [task_name_for("Ev-1")])
        self.assertEqual(requests.queued, [(accepted.request_id, task_name_for("Ev-1"))])

    def test_a_slack_retry_creates_one_request_and_one_task(self) -> None:
        requests, queue = FakeIntake(), FakeQueue()

        first = accept_and_queue(incoming(), requests=requests, queue=queue)
        replay = accept_and_queue(incoming(), requests=requests, queue=queue)

        self.assertEqual(first.request_id, replay.request_id)
        self.assertTrue(first.created)
        self.assertFalse(replay.created)
        # The queue rejected the duplicate name rather than delivering twice.
        self.assertTrue(replay.already_queued)
        self.assertEqual(len(queue.names), 1)

    def test_a_queue_failure_leaves_the_request_stored_and_unqueued(self) -> None:
        requests = FakeIntake()
        queue = FakeQueue(fail_with=RuntimeError("queue unreachable"))

        with self.assertRaises(RequestNotQueuedError):
            accept_and_queue(incoming(), requests=requests, queue=queue)

        # Stored, so a Slack retry finds it. Not marked queued, because it isn't.
        self.assertEqual(len(requests.by_event_id), 1)
        self.assertEqual(requests.queued, [])

    def test_the_request_is_durable_before_the_task_is_created(self) -> None:
        """A task must never point at work that is not yet stored."""
        requests = FakeIntake()
        order: list[str] = []

        class OrderingQueue(FakeQueue):
            def enqueue_support_request(self, *, request_id, task_name):
                order.append("enqueue")
                super().enqueue_support_request(request_id=request_id, task_name=task_name)

        original_accept = requests.accept_request

        def record_accept(value):
            order.append("store")
            return original_accept(value)

        requests.accept_request = record_accept  # type: ignore[method-assign]

        accept_and_queue(incoming(), requests=requests, queue=OrderingQueue())

        self.assertEqual(order, ["store", "enqueue"])


if __name__ == "__main__":
    unittest.main()
