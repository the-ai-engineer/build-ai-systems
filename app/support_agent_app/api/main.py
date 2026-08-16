"""Composition root for the public Slack webhook process.

Not implemented yet. The ingress lesson fills this in.

It will read `ApiSettings`, build a `PostgresSupportRepository` as the
`SupportRequestIntake`, build a Cloud Tasks client from `integrations`, and
mount `routes.create_router`. Like `worker/main.py`, it is the only module in
this package allowed to name concrete adapters.
"""

from __future__ import annotations
