"""The public Slack webhook runtime. Not built yet.

The ingress lesson fills this in. It is one file for now because a plan reads
better in one place than as four files holding a docstring each. Split it when
there is real code to split.

What it will own, in the order a request moves through it:

1. Verify the Slack signature against `ApiSettings.slack_signing_secret` with a
   constant-time comparison, and reject stale timestamps so a captured request
   cannot be replayed.
2. Translate the Slack event envelope into an `IncomingSupportRequest`. Slack's
   wire shapes stay here; the application layer never sees them.
3. Store the request through `SupportRequestIntake` and acknowledge inside
   Slack's three second window.
4. Enqueue a task carrying only the request ID, via `integrations/task_queue.py`.

It must not run the policy workflow inline. The long-running work is the
worker's, which is the entire point of the split.

Like `worker/main.py`, this is a composition root and the only module in the
package allowed to name concrete adapters.
"""

from __future__ import annotations
