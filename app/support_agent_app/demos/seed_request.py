"""Store one support request and print the curl that processes it.

    uv run demo-seed-request --question "How much annual leave do I get?"

This deliberately stops after storing. You make the HTTP call yourself, because
seeing the task payload is the point: it carries a request ID and nothing else.
The employee's question stays in Postgres, which is what keeps sensitive content
out of the queue.

How the worker answers is decided by how you started the worker, not by this
script. That is also deliberate.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

from ..application.lifecycle import IncomingSupportRequest
from ..application.protocols import TASK_IDENTITY_HEADER
from ..commands.seed_policies import seed_policy_documents
from ..database.repositories.support_request_repository import PostgresSupportRepository
from ..settings import LOCAL_TASK_IDENTITY, MissingConfiguration, WorkerSettings

DEFAULT_QUESTION = "Can unused annual leave be carried into next year?"
WORKER_TASK_PATH = "/tasks/process-support-request"


def main() -> None:
    parser = argparse.ArgumentParser(description="Store a support request and print its curl.")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--worker-url", default="http://127.0.0.1:8081")
    parser.add_argument("--task-identity", default=LOCAL_TASK_IDENTITY)
    parser.add_argument(
        "--request-id-only",
        action="store_true",
        help="Print only the request ID, for scripting.",
    )
    args = parser.parse_args()

    try:
        database_url = WorkerSettings.load().database_url
    except MissingConfiguration as error:
        raise SystemExit(str(error)) from error

    seed_policy_documents(database_url)
    requests = PostgresSupportRepository(database_url)
    accepted = requests.accept_request(
        IncomingSupportRequest(
            slack_event_id=f"Ev-seed-{uuid4()}",
            slack_team_id="T-demo",
            slack_channel_id="C-demo",
            slack_message_ts="700.001",
            slack_thread_ts="700.001",
            slack_user_id="U-demo",
            question_text=args.question,
        )
    )
    requests.mark_queued(accepted.request_id)

    if args.request_id_only:
        print(accepted.request_id)
        return

    payload = json.dumps({"request_id": str(accepted.request_id)})
    print(f"stored request {accepted.request_id} in Postgres, status=queued")
    print(f'the question is in the database, not in the payload: "{args.question}"')
    print()
    print("now process it. Note what the worker receives: a request ID, nothing else.")
    print()
    print(f"curl -i -X POST {args.worker_url.rstrip('/')}{WORKER_TASK_PATH} \\")
    print(f"  -H '{TASK_IDENTITY_HEADER}: {args.task_identity}' \\")
    print("  -H 'Content-Type: application/json' \\")
    print(f"  -d '{payload}'")


if __name__ == "__main__":
    main()
