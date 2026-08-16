"""Slack request signature verification.

Not implemented yet. The ingress lesson fills this in.

It will verify `X-Slack-Signature` against `ApiSettings.slack_signing_secret`
using a constant-time comparison, and reject stale timestamps so a captured
request cannot be replayed.
"""

from __future__ import annotations
