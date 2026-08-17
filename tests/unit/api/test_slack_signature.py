from __future__ import annotations

import unittest

from support_agent_app.api.auth import (
    InvalidSlackSignatureError,
    SlackSignatureVerifier,
)

SECRET = "synthetic-signing-secret"
BODY = b'{"type":"event_callback"}'
NOW = 1_700_000_000


def verifier(now: float = NOW, **kwargs) -> SlackSignatureVerifier:
    return SlackSignatureVerifier(SECRET, clock=lambda: now, **kwargs)


class SlackSignatureTests(unittest.TestCase):
    def test_accepts_a_signature_it_produced(self) -> None:
        subject = verifier()
        signature = subject.signature_for(raw_body=BODY, timestamp=str(NOW))

        subject.verify(raw_body=BODY, timestamp=str(NOW), signature=signature)

    def test_rejects_a_changed_body(self) -> None:
        subject = verifier()
        signature = subject.signature_for(raw_body=BODY, timestamp=str(NOW))

        with self.assertRaises(InvalidSlackSignatureError):
            subject.verify(
                raw_body=BODY + b" ",
                timestamp=str(NOW),
                signature=signature,
            )

    def test_rejects_a_replayed_request_outside_the_window(self) -> None:
        old = verifier()
        signature = old.signature_for(raw_body=BODY, timestamp=str(NOW))

        replayed = verifier(now=NOW + 60 * 6)
        with self.assertRaises(InvalidSlackSignatureError):
            replayed.verify(raw_body=BODY, timestamp=str(NOW), signature=signature)

    def test_rejects_a_signature_from_a_different_secret(self) -> None:
        attacker = SlackSignatureVerifier("other-secret", clock=lambda: NOW)
        forged = attacker.signature_for(raw_body=BODY, timestamp=str(NOW))

        with self.assertRaises(InvalidSlackSignatureError):
            verifier().verify(raw_body=BODY, timestamp=str(NOW), signature=forged)

    def test_rejects_missing_malformed_and_non_ascii_headers(self) -> None:
        subject = verifier()
        signature = subject.signature_for(raw_body=BODY, timestamp=str(NOW))

        cases = (
            {"timestamp": None, "signature": signature},
            {"timestamp": str(NOW), "signature": None},
            {"timestamp": "not-a-number", "signature": signature},
            {"timestamp": str(NOW), "signature": "v0=wrong-☃"},
        )
        for case in cases:
            with self.subTest(**case):
                with self.assertRaises(InvalidSlackSignatureError):
                    subject.verify(raw_body=BODY, **case)

    def test_signature_covers_the_timestamp(self) -> None:
        subject = verifier()
        signature = subject.signature_for(raw_body=BODY, timestamp=str(NOW))

        with self.assertRaises(InvalidSlackSignatureError):
            subject.verify(raw_body=BODY, timestamp=str(NOW - 1), signature=signature)


if __name__ == "__main__":
    unittest.main()
