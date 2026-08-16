"""Slack event envelopes and the webhook's own responses.

Not implemented yet. The ingress lesson fills this in.

These are HTTP-shaped types owned by the API boundary. The application layer
never sees them; the route translates a Slack event into an
`IncomingSupportRequest` before calling a use case.
"""

from __future__ import annotations
