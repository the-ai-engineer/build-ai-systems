"""What the Cloud Tasks adapter puts on the queue, without a Google Cloud project.

The fake stands in for the one API call the adapter makes, including the part
the design depends on: a task name that already exists is refused.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest import mock
from uuid import UUID, uuid4

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2
from support_agent_app.api.accept_request import accept_and_queue
from support_agent_app.api.main import build_task_queue
from support_agent_app.api.task_queue import (
    WORKER_TASK_PATH,
    CloudTasksQueue,
    LocalTaskQueue,
)
from support_agent_app.application.lifecycle import (
    IncomingSupportRequest,
    TaskAlreadyQueuedError,
    task_name_for,
)
from support_agent_app.settings import ApiSettings, MissingConfiguration

from tests.fakes.intake import FakeIntake

PROJECT = "build-ai-systems-dev"
LOCATION = "europe-west1"
QUEUE = "support-requests"
WORKER_URL = "https://support-worker-abc123.europe-west1.run.app"
WEBHOOK_SA = "support-webhook@build-ai-systems-dev.iam.gserviceaccount.com"
QUEUE_PATH = f"projects/{PROJECT}/locations/{LOCATION}/queues/{QUEUE}"


class FakeCloudTasks:
    """The Cloud Tasks name deduplication, and nothing else it does."""

    def __init__(self) -> None:
        self.parents: list[str] = []
        self.tasks: dict[str, tasks_v2.Task] = {}

    def create_task(self, *, parent: str, task: tasks_v2.Task) -> Any:
        if task.name in self.tasks:
            raise AlreadyExists(f"task {task.name} already exists")
        self.parents.append(parent)
        self.tasks[task.name] = task
        return task


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


def queue_with(client: FakeCloudTasks) -> CloudTasksQueue:
    return CloudTasksQueue(
        project_id=PROJECT,
        location=LOCATION,
        queue_name=QUEUE,
        worker_base_url=WORKER_URL,
        service_account_email=WEBHOOK_SA,
        client=client,
    )


class CloudTasksNamingTests(unittest.TestCase):
    def test_the_task_name_is_derived_from_the_slack_event(self) -> None:
        client = FakeCloudTasks()

        queue_with(client).enqueue_support_request(
            request_id=uuid4(), task_name=task_name_for("Ev-1")
        )

        self.assertEqual(client.parents, [QUEUE_PATH])
        self.assertEqual(list(client.tasks), [f"{QUEUE_PATH}/tasks/{task_name_for('Ev-1')}"])

    def test_a_second_webhook_process_derives_the_same_name(self) -> None:
        """Nothing about the name comes from the process that creates it."""
        first, second = FakeCloudTasks(), FakeCloudTasks()

        queue_with(first).enqueue_support_request(
            request_id=uuid4(), task_name=task_name_for("Ev-1")
        )
        queue_with(second).enqueue_support_request(
            request_id=uuid4(), task_name=task_name_for("Ev-1")
        )

        self.assertEqual(list(first.tasks), list(second.tasks))

    def test_a_repeated_name_is_a_duplicate_and_not_a_failure(self) -> None:
        client = FakeCloudTasks()
        queue = queue_with(client)
        name = task_name_for("Ev-1")

        queue.enqueue_support_request(request_id=uuid4(), task_name=name)
        with self.assertRaises(TaskAlreadyQueuedError):
            queue.enqueue_support_request(request_id=uuid4(), task_name=name)

        self.assertEqual(len(client.tasks), 1)

    def test_a_slack_retry_leaves_the_webhook_with_one_unit_of_work(self) -> None:
        """The whole point of the derived name, through the use case that uses it."""
        client = FakeCloudTasks()
        queue, requests = queue_with(client), FakeIntake()

        first = accept_and_queue(incoming(), requests=requests, queue=queue)
        replay = accept_and_queue(incoming(), requests=requests, queue=queue)

        self.assertEqual(first.request_id, replay.request_id)
        self.assertFalse(first.already_queued)
        self.assertTrue(replay.already_queued)
        self.assertEqual(len(client.tasks), 1)

    def test_a_new_task_generation_gets_its_own_task(self) -> None:
        client = FakeCloudTasks()
        queue = queue_with(client)

        queue.enqueue_support_request(request_id=uuid4(), task_name=task_name_for("Ev-1", 1))
        queue.enqueue_support_request(request_id=uuid4(), task_name=task_name_for("Ev-1", 2))

        self.assertEqual(len(client.tasks), 2)


class CloudTasksRequestTests(unittest.TestCase):
    def enqueued(self, request_id: UUID | None = None) -> tasks_v2.Task:
        client = FakeCloudTasks()
        queue_with(client).enqueue_support_request(
            request_id=request_id or uuid4(), task_name=task_name_for("Ev-1")
        )
        return next(iter(client.tasks.values()))

    def test_the_body_carries_only_the_request_id(self) -> None:
        """INV-4: the queue never holds the employee's question."""
        request_id = uuid4()

        body = json.loads(self.enqueued(request_id).http_request.body)

        self.assertEqual(body, {"request_id": str(request_id)})

    def test_the_task_posts_to_the_private_worker(self) -> None:
        task = self.enqueued()

        self.assertEqual(task.http_request.url, f"{WORKER_URL}{WORKER_TASK_PATH}")
        self.assertEqual(task.http_request.http_method, tasks_v2.HttpMethod.POST)
        self.assertEqual(task.http_request.headers["Content-Type"], "application/json")

    def test_the_task_carries_an_oidc_token_for_the_webhook_identity(self) -> None:
        token = self.enqueued().http_request.oidc_token

        self.assertEqual(token.service_account_email, WEBHOOK_SA)
        self.assertEqual(token.audience, WORKER_URL)

    def test_the_dispatch_deadline_outlasts_the_worker_budget(self) -> None:
        self.assertGreater(self.enqueued().dispatch_deadline.seconds, 55)

    def test_a_trailing_slash_on_the_worker_url_does_not_double(self) -> None:
        client = FakeCloudTasks()
        CloudTasksQueue(
            project_id=PROJECT,
            location=LOCATION,
            queue_name=QUEUE,
            worker_base_url=f"{WORKER_URL}/",
            service_account_email=WEBHOOK_SA,
            client=client,
        ).enqueue_support_request(request_id=uuid4(), task_name=task_name_for("Ev-1"))

        task = next(iter(client.tasks.values()))
        self.assertEqual(task.http_request.url, f"{WORKER_URL}{WORKER_TASK_PATH}")

    def test_missing_configuration_is_refused_at_construction(self) -> None:
        for field in (
            "project_id",
            "location",
            "queue_name",
            "worker_base_url",
            "service_account_email",
        ):
            arguments: dict[str, Any] = {
                "project_id": PROJECT,
                "location": LOCATION,
                "queue_name": QUEUE,
                "worker_base_url": WORKER_URL,
                "service_account_email": WEBHOOK_SA,
                field: "",
            }
            with self.subTest(field=field), self.assertRaises(ValueError):
                CloudTasksQueue(**arguments, client=FakeCloudTasks())


class QueueSelectionTests(unittest.TestCase):
    """`api/main.py` is the only module that names a concrete queue."""

    def setUp(self) -> None:
        # These tests are about what configuration selects, so nothing may come
        # from the developer's own environment or .env file.
        patched = mock.patch.dict(os.environ, {}, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    def settings(self, **overrides: str) -> ApiSettings:
        values: dict[str, Any] = {
            "_env_file": None,
            "database_url": "postgresql://localhost:5432/support_agent",
            "slack_signing_secret": "not-a-real-secret",
        }
        values.update(overrides)
        return ApiSettings(**values)

    def test_the_default_is_the_local_queue(self) -> None:
        self.assertIsInstance(build_task_queue(self.settings()), LocalTaskQueue)

    def test_configuration_selects_cloud_tasks(self) -> None:
        queue = build_task_queue(
            self.settings(
                task_queue_backend="cloud-tasks",
                google_cloud_project=PROJECT,
                task_queue_location=LOCATION,
                task_oidc_service_account=WEBHOOK_SA,
                worker_base_url=WORKER_URL,
            )
        )

        # No client is built until a task is enqueued, so this needs no
        # credentials and reaches no Google Cloud API.
        self.assertIsInstance(queue, CloudTasksQueue)

    def test_cloud_tasks_without_its_configuration_fails_at_startup(self) -> None:
        with self.assertRaises(MissingConfiguration) as raised:
            self.settings(task_queue_backend="cloud-tasks")

        message = str(raised.exception)
        self.assertIn("GOOGLE_CLOUD_PROJECT", message)
        self.assertIn("TASK_QUEUE_LOCATION", message)
        self.assertIn("TASK_OIDC_SERVICE_ACCOUNT", message)


if __name__ == "__main__":
    unittest.main()
