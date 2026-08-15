from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError

from support_agent_app.worker import create_app
from support_agent_app.worker_auth import (
    LOCAL_TASK_IDENTITY,
    TASK_IDENTITY_HEADER,
    InvalidTaskIdentityError,
    StaticTaskAuthenticator,
)
from support_agent_app.worker_service import WorkerResult, classify_workflow_failure


class StubProcessor:
    def __init__(self, outcome: str = "completed") -> None:
        self.outcome = outcome
        self.calls = 0

    def process(self, request_id, deadline):
        self.calls += 1
        self.last_request_id = request_id
        self.last_deadline = deadline
        return WorkerResult(request_id=request_id, outcome=self.outcome, send_attempted=True)


class WorkerAuthTests(unittest.TestCase):
    def test_workflow_failure_classification_separates_permanent_configuration(self) -> None:
        self.assertEqual(
            classify_workflow_failure(ValueError("synthetic configuration")),
            ("model_configuration", False),
        )
        self.assertEqual(
            classify_workflow_failure(ModelHTTPError(503, "synthetic-model")),
            ("model_provider_temporary", True),
        )

    def test_static_authenticator_rejects_missing_and_wrong_identities(self) -> None:
        authenticator = StaticTaskAuthenticator("expected-task")

        for identity in (None, "wrong-task"):
            with self.subTest(identity=identity):
                with self.assertRaises(InvalidTaskIdentityError):
                    authenticator.authenticate(identity)

        authenticator.authenticate("expected-task")

    def test_endpoint_accepts_only_request_id_from_a_valid_identity(self) -> None:
        processor = StubProcessor()
        client = TestClient(create_app(service=processor))
        request_id = uuid4()

        response = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: LOCAL_TASK_IDENTITY},
            json={"request_id": str(request_id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"], "completed")
        self.assertEqual(processor.calls, 1)
        self.assertEqual(processor.last_request_id, request_id)
        self.assertGreater(processor.last_deadline.remaining_seconds(), 0)

        extra_field = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: LOCAL_TASK_IDENTITY},
            json={"request_id": str(request_id), "question": "must not be accepted"},
        )
        self.assertEqual(extra_field.status_code, 422)
        self.assertEqual(processor.calls, 1)

    def test_endpoint_rejects_invalid_identity_before_processing(self) -> None:
        processor = StubProcessor()
        client = TestClient(create_app(service=processor))

        response = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: "wrong-task"},
            json={"request_id": str(uuid4())},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid task identity"})
        self.assertEqual(processor.calls, 0)

    def test_endpoint_returns_retry_status_for_an_active_lease(self) -> None:
        processor = StubProcessor("active-lease")
        client = TestClient(create_app(service=processor))

        response = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: LOCAL_TASK_IDENTITY},
            json={"request_id": str(uuid4())},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "active-lease"})


if __name__ == "__main__":
    unittest.main()
