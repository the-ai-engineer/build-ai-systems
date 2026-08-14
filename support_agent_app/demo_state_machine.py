"""Show an expired worker being rejected after a newer Postgres claim."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from uuid import uuid4

from .migrations import apply_migrations
from .request_repository import (
    IncomingSupportRequest,
    PostgresSupportRepository,
    StaleClaimError,
)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    apply_migrations(database_url)
    repository = PostgresSupportRepository(database_url)
    accepted = repository.accept_request(
        IncomingSupportRequest(
            slack_event_id=f"Ev-demo-{uuid4()}",
            slack_team_id="T-demo",
            slack_channel_id="C-demo",
            slack_message_ts="100.001",
            slack_thread_ts="100.001",
            slack_user_id="U-demo",
            question_text="A synthetic state-machine question.",
        )
    )
    repository.mark_queued(accepted.request_id)

    worker_a = repository.claim_request(
        accepted.request_id,
        timedelta(milliseconds=50),
    ).claim
    assert worker_a is not None
    print(f"worker A claimed lease version {worker_a.lease_version}")

    time.sleep(0.08)
    worker_b = repository.claim_request(
        accepted.request_id,
        timedelta(minutes=1),
    ).claim
    assert worker_b is not None
    print(f"worker B claimed expired work with lease version {worker_b.lease_version}")

    try:
        repository.create_reply_action(worker_a, "Synthetic stale reply.")
    except StaleClaimError:
        print("REJECTED: stale worker A cannot create an outbound action after worker B claimed")
    else:
        raise RuntimeError("stale worker A unexpectedly changed durable state")

    action = repository.create_reply_action(worker_b, "Synthetic current reply.")
    print(f"current worker B created one pending action {action.action_id}")


if __name__ == "__main__":
    main()
