"""Send a signed Slack mention to a running webhook and show what happened.

    DATABASE_URL=... uv run python -m examples.demos.send_slack_event \
        --question "Can unused annual leave be carried into next year?"

Use this with the webhook and worker running as separate processes, which is the
shape the deployed system actually has. It signs the request the way Slack does,
posts it, then watches Postgres until the request reaches a terminal state.

It reads the reply from the durable record rather than from a log, because the
complete message text is deliberately never logged (INV-9). Postgres is the
source of truth, so that is where you look.
"""

from __future__ import annotations

import argparse
import json
import time
from uuid import uuid4

import httpx
from psycopg import connect
from psycopg.rows import dict_row
from support_agent_app.api.auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SlackSignatureVerifier,
)
from support_agent_app.settings import WorkerSettings

TERMINAL_STATUSES = frozenset({"completed", "failed", "reconciliation"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a signed Slack mention to the webhook.")
    parser.add_argument(
        "--question",
        default="Can unused annual leave be carried into next year?",
        help="What the employee types after the mention.",
    )
    parser.add_argument("--webhook-url", default="http://127.0.0.1:8080")
    parser.add_argument("--signing-secret", default="demo-secret")
    parser.add_argument("--team-id", default="T-demo")
    parser.add_argument("--channel-id", default="C-demo")
    parser.add_argument(
        "--thread-ts",
        default=None,
        help="Reply into an existing thread instead of starting a new one.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()

    try:
        database_url = WorkerSettings.load().database_url
    except Exception as error:
        raise SystemExit("DATABASE_URL is required") from error

    event_id = f"Ev-demo-{uuid4()}"
    status = _post_event(args, event_id)
    print(f"webhook responded {status}")
    if status != 200:
        raise SystemExit("the webhook did not accept the event")

    print("watching Postgres for the worker to finish...")
    row, seen = _await_outcome(database_url, event_id, args.timeout_seconds)
    if row is None and not seen:
        # 200 with no stored request means the webhook deliberately ignored the
        # event, so Slack stops retrying something it was never going to act on.
        print("no request was stored: the webhook ignored this event")
        print("(a 2xx here is on purpose, so Slack stops retrying it)")
        return
    if row is None:
        raise SystemExit("the request was stored but did not reach a terminal state in time")

    print(f"status: {row['status']}")
    if row["last_error_category"]:
        print(f"last_error_category: {row['last_error_category']}")
    print(f"business attempts: {row['business_attempt_count']}")
    if not row["outbound_text"]:
        print("no reply was created")
        return
    print(f"action: {row['action_status']}")
    print("--- the reply in the Slack thread ---")
    print(row["outbound_text"])


def _post_event(args: argparse.Namespace, event_id: str) -> int:
    message_ts = f"{int(time.time())}.000100"
    event = {
        "type": "app_mention",
        "channel": args.channel_id,
        "user": "U-employee",
        "ts": message_ts,
        "text": f"<@U08BOTID99> {args.question}",
    }
    if args.thread_ts:
        event["thread_ts"] = args.thread_ts

    body = json.dumps(
        {
            "type": "event_callback",
            "event_id": event_id,
            "team_id": args.team_id,
            "event": event,
        }
    ).encode("utf-8")

    verifier = SlackSignatureVerifier(args.signing_secret)
    timestamp = str(int(time.time()))
    response = httpx.post(
        f"{args.webhook_url.rstrip('/')}/slack/events",
        content=body,
        headers={
            SIGNATURE_HEADER: verifier.signature_for(raw_body=body, timestamp=timestamp),
            TIMESTAMP_HEADER: timestamp,
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )
    return response.status_code


def _await_outcome(database_url: str, event_id: str, timeout_seconds: float):
    """Return the terminal row, and whether the request was ever stored."""

    deadline = time.monotonic() + timeout_seconds
    seen = False
    while time.monotonic() < deadline:
        with connect(database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                select r.status,
                       r.business_attempt_count,
                       r.last_error_category,
                       a.status as action_status,
                       a.outbound_text
                from support_requests r
                left join outbound_actions a using (request_id)
                where r.slack_event_id = %s
                order by a.created_at desc nulls last
                limit 1
                """,
                (event_id,),
            ).fetchone()
        if row is not None:
            seen = True
            if row["status"] in TERMINAL_STATUSES:
                return row, seen
        time.sleep(0.25)
    return None, seen


if __name__ == "__main__":
    main()
