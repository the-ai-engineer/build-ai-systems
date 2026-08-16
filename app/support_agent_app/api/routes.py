"""The public Slack event route.

Not implemented yet. The ingress lesson fills this in.

It will verify the Slack signature, acknowledge within Slack's three second
window, store the request through `SupportRequestIntake`, and enqueue a task
carrying only the request ID. It must not run the policy workflow inline: the
long-running work belongs to the worker.
"""

from __future__ import annotations
