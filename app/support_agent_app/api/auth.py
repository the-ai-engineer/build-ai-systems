"""Slack request signature verification.

This runs against the raw request body, before any JSON parsing. That ordering
is the point: parsing untrusted bytes you have not authenticated is how a
webhook becomes an open door.

Two checks, both required. The signature proves the request came from Slack.
The timestamp window means a captured request cannot be replayed later.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable

SIGNATURE_HEADER = "X-Slack-Signature"
TIMESTAMP_HEADER = "X-Slack-Request-Timestamp"
SIGNATURE_VERSION = "v0"
MAX_TIMESTAMP_AGE_SECONDS = 60 * 5


class InvalidSlackSignatureError(PermissionError):
    """The request did not come from Slack, or is too old to trust."""


class SlackSignatureVerifier:
    """Verify `X-Slack-Signature` over the raw body."""

    def __init__(
        self,
        signing_secret: str,
        *,
        max_age_seconds: int = MAX_TIMESTAMP_AGE_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not signing_secret:
            raise ValueError("signing_secret is required")
        self._signing_secret = signing_secret.encode("utf-8")
        self._max_age_seconds = max_age_seconds
        self._clock = clock

    def verify(
        self,
        *,
        raw_body: bytes,
        timestamp: str | None,
        signature: str | None,
    ) -> None:
        if not timestamp or not signature:
            raise InvalidSlackSignatureError("missing signature headers")

        try:
            sent_at = int(timestamp)
        except ValueError as error:
            raise InvalidSlackSignatureError("malformed timestamp") from error

        if abs(self._clock() - sent_at) > self._max_age_seconds:
            raise InvalidSlackSignatureError("timestamp outside the accepted window")

        expected = self.signature_for(raw_body=raw_body, timestamp=timestamp)
        # compare_digest raises on non-ASCII str input, and a forged header is
        # exactly where non-ASCII turns up.
        if not signature.isascii() or not hmac.compare_digest(expected, signature):
            raise InvalidSlackSignatureError("signature mismatch")

    def signature_for(self, *, raw_body: bytes, timestamp: str) -> str:
        basestring = (
            SIGNATURE_VERSION.encode("ascii") + b":" + timestamp.encode("ascii") + b":" + raw_body
        )
        digest = hmac.new(self._signing_secret, basestring, hashlib.sha256).hexdigest()
        return f"{SIGNATURE_VERSION}={digest}"
