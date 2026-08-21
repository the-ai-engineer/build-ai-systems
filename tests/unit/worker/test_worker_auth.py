"""Who may hand the worker a task, and what happens to everyone else."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest import mock
from uuid import uuid4

from fastapi.testclient import TestClient
from google.auth.exceptions import DefaultCredentialsError
from google.genai.errors import ServerError
from support_agent_app.settings import MissingConfiguration, WorkerBoundarySettings
from support_agent_app.worker.auth import (
    AUTHORIZATION_HEADER,
    LOCAL_TASK_IDENTITY,
    TASK_IDENTITY_HEADER,
    GoogleOidcTaskAuthenticator,
    InvalidTaskIdentityError,
    StaticTaskAuthenticator,
)
from support_agent_app.worker.failures import classify_workflow_failure
from support_agent_app.worker.main import build_authenticator, create_app
from support_agent_app.worker.process_request import WorkerResult

AUDIENCE = "https://support-worker-abc123-ew.a.run.app"
WEBHOOK_SA = "support-webhook@build-ai-systems-dev.iam.gserviceaccount.com"


def static_settings() -> WorkerBoundarySettings:
    """Boundary configuration for a local run, built without any environment."""

    return WorkerBoundarySettings(
        worker_task_auth="static",
        worker_base_url="http://127.0.0.1:8081",
        worker_expected_task_identity=LOCAL_TASK_IDENTITY,
        worker_deadline_seconds=55.0,
    )


def oidc_settings() -> WorkerBoundarySettings:
    return WorkerBoundarySettings(
        worker_task_auth="google-oidc",
        worker_base_url=AUDIENCE,
        task_oidc_service_account=WEBHOOK_SA,
        worker_expected_task_identity=LOCAL_TASK_IDENTITY,
        worker_deadline_seconds=55.0,
    )


def cloud_tasks_claims(**overrides: Any) -> dict[str, Any]:
    """The claims a token Cloud Tasks minted for the webhook carries."""

    claims = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": WEBHOOK_SA,
        "email_verified": True,
        "exp": 2_000_000_000,
    }
    claims.update(overrides)
    return claims


class FakeVerifier:
    """Stands in for Google's certificate fetch and signature check.

    It accepts exactly one token string, which is what "signed by Google" means
    to a test: anything else is a forgery and raises, the way google-auth does.
    """

    def __init__(self, *, valid_token: str, claims: dict[str, Any]) -> None:
        self._valid_token = valid_token
        self._claims = claims
        self.calls: list[tuple[str, str]] = []

    def __call__(self, token: str, audience: str) -> dict[str, Any]:
        self.calls.append((token, audience))
        if token != self._valid_token:
            raise ValueError("could not verify the token signature")
        if self._claims.get("aud") != audience:
            raise ValueError("audience mismatch")
        return self._claims


def oidc_authenticator(
    *, valid_token: str = "signed-by-google", claims: dict[str, Any] | None = None
) -> tuple[GoogleOidcTaskAuthenticator, FakeVerifier]:
    verifier = FakeVerifier(
        valid_token=valid_token, claims=cloud_tasks_claims() if claims is None else claims
    )
    authenticator = GoogleOidcTaskAuthenticator(
        expected_audience=AUDIENCE,
        expected_service_account=WEBHOOK_SA,
        verifier=verifier,
    )
    return authenticator, verifier


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
            classify_workflow_failure(ServerError(503, {"error": "synthetic-model"})),
            ("model_provider_temporary", True),
        )
        self.assertEqual(
            classify_workflow_failure(DefaultCredentialsError("synthetic missing ADC")),
            ("model_configuration", False),
        )

    def test_static_authenticator_rejects_missing_and_wrong_identities(self) -> None:
        authenticator = StaticTaskAuthenticator("expected-task")

        for identity in (None, "wrong-task", "wrong-☃"):
            with self.subTest(identity=identity):
                with self.assertRaises(InvalidTaskIdentityError):
                    authenticator.authenticate(identity)

        authenticator.authenticate("expected-task")

    def test_endpoint_accepts_only_request_id_from_a_valid_identity(self) -> None:
        processor = StubProcessor()
        client = TestClient(create_app(service=processor, boundary_settings=static_settings()))
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
        client = TestClient(create_app(service=processor, boundary_settings=static_settings()))

        response = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: "wrong-task"},
            json={"request_id": str(uuid4())},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "invalid task identity"})
        self.assertEqual(processor.calls, 0)

        non_ascii = client.post(
            "/tasks/process-support-request",
            headers=[
                (TASK_IDENTITY_HEADER.encode("ascii"), b"wrong-\xff"),
                (b"content-type", b"application/json"),
            ],
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(non_ascii.status_code, 401)
        self.assertEqual(non_ascii.json(), {"detail": "invalid task identity"})
        self.assertEqual(processor.calls, 0)

    def test_endpoint_returns_retry_status_for_an_active_lease(self) -> None:
        processor = StubProcessor("active-lease")
        client = TestClient(create_app(service=processor, boundary_settings=static_settings()))

        response = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: LOCAL_TASK_IDENTITY},
            json={"request_id": str(uuid4())},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "active-lease"})


class GoogleOidcAuthenticatorTests(unittest.TestCase):
    def test_it_accepts_a_signed_token_from_the_webhook_service_account(self) -> None:
        authenticator, verifier = oidc_authenticator()

        authenticator.authenticate("Bearer signed-by-google")

        self.assertEqual(verifier.calls, [("signed-by-google", AUDIENCE)])

    def test_it_verifies_against_the_audience_the_queue_puts_in_the_token(self) -> None:
        """`api/task_queue.py` sets the audience to the worker's base URL."""

        authenticator = GoogleOidcTaskAuthenticator(
            expected_audience=f"{AUDIENCE}/",
            expected_service_account=WEBHOOK_SA,
            verifier=FakeVerifier(valid_token="t", claims=cloud_tasks_claims()),
        )

        authenticator.authenticate("bearer t")

    def test_it_rejects_a_missing_or_malformed_authorization_header(self) -> None:
        authenticator, verifier = oidc_authenticator()

        for header in (None, "", "signed-by-google", "Basic signed-by-google", "Bearer   "):
            with self.subTest(header=header):
                with self.assertRaises(InvalidTaskIdentityError):
                    authenticator.authenticate(header)

        # A header that is not a bearer token never reaches the verifier.
        self.assertEqual(verifier.calls, [])

    def test_it_rejects_a_forged_token(self) -> None:
        authenticator, _ = oidc_authenticator()

        with self.assertRaises(InvalidTaskIdentityError):
            authenticator.authenticate("Bearer forged.token.value")

    def test_it_rejects_a_valid_token_from_the_wrong_service_account(self) -> None:
        authenticator, _ = oidc_authenticator(
            claims=cloud_tasks_claims(
                email="support-maintenance@build-ai-systems-dev.iam.gserviceaccount.com"
            )
        )

        with self.assertRaises(InvalidTaskIdentityError):
            authenticator.authenticate("Bearer signed-by-google")

    def test_it_rejects_tokens_failing_any_single_claim(self) -> None:
        cases = {
            "wrong audience": cloud_tasks_claims(aud="https://another-service.a.run.app"),
            "wrong issuer": cloud_tasks_claims(iss="https://accounts.example.com"),
            "unverified email": cloud_tasks_claims(email_verified=False),
            "no email": cloud_tasks_claims(email=""),
        }
        for name, claims in cases.items():
            with self.subTest(name):
                # A verifier that returns the claims without objecting, so each
                # rejection here is this class's own check and not a borrowed one.
                authenticator = GoogleOidcTaskAuthenticator(
                    expected_audience=AUDIENCE,
                    expected_service_account=WEBHOOK_SA,
                    verifier=lambda token, audience, claims=claims: claims,
                )
                with self.assertRaises(InvalidTaskIdentityError):
                    authenticator.authenticate("Bearer t")

    def test_it_requires_an_audience_and_a_service_account(self) -> None:
        with self.assertRaises(ValueError):
            GoogleOidcTaskAuthenticator(expected_audience="", expected_service_account=WEBHOOK_SA)
        with self.assertRaises(ValueError):
            GoogleOidcTaskAuthenticator(expected_audience=AUDIENCE, expected_service_account="")


class TaskAuthConfigurationTests(unittest.TestCase):
    def test_google_oidc_is_the_default_and_static_must_be_asked_for(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_OIDC_SERVICE_ACCOUNT": WEBHOOK_SA},
            clear=True,
        ):
            configured = WorkerBoundarySettings.load()
        self.assertEqual(configured.worker_task_auth, "google-oidc")
        self.assertIsInstance(build_authenticator(oidc_settings()), GoogleOidcTaskAuthenticator)
        self.assertIsInstance(build_authenticator(static_settings()), StaticTaskAuthenticator)

    def test_oidc_without_an_audience_or_identity_refuses_to_start(self) -> None:
        with self.assertRaises(MissingConfiguration) as raised:
            WorkerBoundarySettings(
                worker_task_auth="google-oidc",
                worker_base_url="",
                task_oidc_service_account="",
                worker_expected_task_identity=LOCAL_TASK_IDENTITY,
                worker_deadline_seconds=55.0,
            )

        self.assertIn("WORKER_BASE_URL", str(raised.exception))
        self.assertIn("TASK_OIDC_SERVICE_ACCOUNT", str(raised.exception))

    def test_an_oidc_worker_rejects_a_static_identity_header(self) -> None:
        processor = StubProcessor()
        authenticator, _ = oidc_authenticator()
        client = TestClient(
            create_app(
                service=processor,
                authenticator=authenticator,
                boundary_settings=oidc_settings(),
            )
        )

        rejected = client.post(
            "/tasks/process-support-request",
            headers={TASK_IDENTITY_HEADER: LOCAL_TASK_IDENTITY},
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(processor.calls, 0)

        accepted = client.post(
            "/tasks/process-support-request",
            headers={AUTHORIZATION_HEADER: "Bearer signed-by-google"},
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(processor.calls, 1)


if __name__ == "__main__":
    unittest.main()
