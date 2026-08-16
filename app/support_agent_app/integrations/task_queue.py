"""Cloud Tasks enqueueing for the public webhook.

Not implemented yet. The queue lesson fills this in.

It will create a task carrying only the request ID, targeted at the private
worker with an OIDC token. Queue names, retry configuration, and Google client
details stay inside this module.
"""

from __future__ import annotations
