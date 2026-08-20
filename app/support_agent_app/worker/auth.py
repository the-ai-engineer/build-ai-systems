"""Who is allowed to invoke the private worker.

Two authenticators behind one protocol. `GoogleOidcTaskAuthenticator` is the
deployed one: Cloud Tasks mints an OIDC token for the webhook's service account
and Google signs it, so the worker can prove the caller is that identity and
nothing else. `StaticTaskAuthenticator` is the local stand-in, for running the
two services on a laptop where there is no Google identity to mint.

They differ in the header they read, because the token they read is not the
same kind of thing: a bearer token belongs in `Authorization`, and the local
shared string has its own header so it can never be mistaken for one.

The route asks the selected authenticator which header to read, so adding a
third authenticator changes this file and nothing else.
"""

from __future__ import annotations

import secrets
from typing import Any, Protocol

from ..application.protocols import TASK_IDENTITY_HEADER
from ..settings import LOCAL_TASK_IDENTITY

__all__ = [
    "AUTHORIZATION_HEADER",
    "GOOGLE_ISSUERS",
    "LOCAL_TASK_IDENTITY",
    "TASK_IDENTITY_HEADER",
    "GoogleIdTokenVerifier",
    "GoogleOidcTaskAuthenticator",
    "IdTokenVerifier",
    "InvalidTaskIdentityError",
    "StaticTaskAuthenticator",
    "TaskAuthenticator",
]

AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "bearer "

# Google signs its OIDC tokens under one of these two issuer spellings.
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})

# Cloud Tasks mints the token shortly before it dispatches, but the worker's
# clock is not the token service's clock.
CLOCK_SKEW_SECONDS = 10


class InvalidTaskIdentityError(PermissionError):
    pass


class TaskAuthenticator(Protocol):
    """Decide whether one HTTP caller may hand the worker a task.

    `identity_header` is the header the route reads and passes to
    `authenticate`. `authenticate` returns nothing and raises
    `InvalidTaskIdentityError` for every rejection, so a caller cannot mistake
    a falsy return value for a pass.
    """

    identity_header: str

    def authenticate(self, presented_identity: str | None) -> None: ...


class StaticTaskAuthenticator:
    """Local identity check: a shared string in a header of its own.

    This proves nothing about who called. It exists so the two services can run
    on a laptop without a Google identity, and it is never the deployed default:
    `WorkerBoundarySettings.worker_task_auth` defaults to `google-oidc` and a
    local run opts out of it explicitly.
    """

    identity_header = TASK_IDENTITY_HEADER

    def __init__(self, expected_identity: str = LOCAL_TASK_IDENTITY) -> None:
        if not expected_identity:
            raise ValueError("expected_identity is required")
        self._expected_identity = expected_identity

    def authenticate(self, presented_identity: str | None) -> None:
        if presented_identity is None or not secrets.compare_digest(
            presented_identity.encode("utf-8"),
            self._expected_identity.encode("utf-8"),
        ):
            raise InvalidTaskIdentityError("invalid task identity")


class IdTokenVerifier(Protocol):
    """Check a Google-signed OIDC token and return its claims.

    Narrower than the google-auth call it stands for, so a test can supply a
    double without a Google Cloud project, credentials, or a network. An
    implementation must verify the signature, the expiry, and the audience, and
    raise on any failure rather than returning unverified claims.
    """

    def __call__(self, token: str, audience: str) -> dict[str, Any]: ...


class GoogleIdTokenVerifier:
    """The real verifier: Google's public certificates, fetched and cached.

    The transport session is built on first use and reused, because fetching
    the certificate set on every task would put a second network call in front
    of every unit of work.
    """

    def __init__(self) -> None:
        self._request: Any | None = None

    def __call__(self, token: str, audience: str) -> dict[str, Any]:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        if self._request is None:
            self._request = google_requests.Request()
        return id_token.verify_oauth2_token(
            token,
            self._request,
            audience=audience,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )


class GoogleOidcTaskAuthenticator:
    """The deployed identity check: a Google-signed OIDC token from one caller.

    Cloud Tasks attaches an `Authorization: Bearer <id token>` header to every
    dispatch, minted for the service account the queue was told to use and with
    the audience the task carried. `api/task_queue.py` sets that audience to the
    worker's base URL, so `expected_audience` is that same URL and the two are
    compared exactly, trailing slash aside.

    Four things must hold, and any one of them failing is a 401 before the
    worker touches the request:

    - Google signed the token and it has not expired
    - the audience is this worker
    - the issuer is Google
    - the verified email is the one service account allowed to enqueue work

    Cloud Run's own `run.invoker` check already rejects unknown callers before
    the request reaches this process. This is the second lock: it is the one
    that says *which* identity, and it keeps holding if the service is ever
    exposed by a misconfigured binding.
    """

    identity_header = AUTHORIZATION_HEADER

    def __init__(
        self,
        *,
        expected_audience: str,
        expected_service_account: str,
        verifier: IdTokenVerifier | None = None,
    ) -> None:
        if not expected_audience:
            raise ValueError("expected_audience is required")
        if not expected_service_account:
            raise ValueError("expected_service_account is required")
        self._expected_audience = expected_audience.rstrip("/")
        self._expected_service_account = expected_service_account
        self._verify = verifier or GoogleIdTokenVerifier()

    def authenticate(self, presented_identity: str | None) -> None:
        token = _bearer_token(presented_identity)
        try:
            claims = self._verify(token, self._expected_audience)
        except Exception as error:
            # Every rejection google-auth makes arrives as some exception type
            # of its own. None of them should reach the route, and none of them
            # should tell the caller which check failed.
            raise InvalidTaskIdentityError("invalid task identity") from error

        if not isinstance(claims, dict):
            raise InvalidTaskIdentityError("invalid task identity")
        if str(claims.get("iss", "")) not in GOOGLE_ISSUERS:
            raise InvalidTaskIdentityError("invalid task identity")
        # The verifier is asked to check the audience, and is checked on it
        # here too. This is the one claim a wrong answer would silently hand
        # another service's tasks to this worker.
        if not _matches(str(claims.get("aud", "")).rstrip("/"), self._expected_audience):
            raise InvalidTaskIdentityError("invalid task identity")
        if claims.get("email_verified") is not True:
            raise InvalidTaskIdentityError("invalid task identity")
        if not _matches(str(claims.get("email", "")), self._expected_service_account):
            raise InvalidTaskIdentityError("invalid task identity")


def _bearer_token(header_value: str | None) -> str:
    if not header_value or not header_value.lower().startswith(BEARER_PREFIX):
        raise InvalidTaskIdentityError("invalid task identity")
    token = header_value[len(BEARER_PREFIX) :].strip()
    if not token:
        raise InvalidTaskIdentityError("invalid task identity")
    return token


def _matches(presented: str, expected: str) -> bool:
    return secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
