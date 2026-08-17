"""The use case behind the webhook: accept one mention and queue the work.

The order matters and is the whole point of this file. The request is stored
before the task is created, so a task can never reference work that is not
durable. If the queue then fails, the request stays `accepted` and the caller
returns a non-2xx so Slack retries. The retry re-derives the same task name and
converges, rather than creating a second unit of work.

Nothing here calls a model or reads a policy. That is invariant INV-2, and it is
why the webhook can answer Slack inside its three second window.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..application.lifecycle import (
    FIRST_TASK_GENERATION,
    IncomingSupportRequest,
    TaskAlreadyQueuedError,
    task_name_for,
)
from ..application.protocols import SupportRequestIntake, TaskQueue


class RequestNotQueuedError(RuntimeError):
    """The request is stored but the queue would not take it.

    The caller must not return 2xx. The work is durable and a Slack retry will
    pick it up from `accepted`.
    """


@dataclass(frozen=True)
class AcceptedForProcessing:
    request_id: UUID
    created: bool
    already_queued: bool


def accept_and_queue(
    incoming: IncomingSupportRequest,
    *,
    requests: SupportRequestIntake,
    queue: TaskQueue,
    task_generation: int = FIRST_TASK_GENERATION,
) -> AcceptedForProcessing:
    accepted = requests.accept_request(incoming)
    task_name = task_name_for(incoming.slack_event_id, task_generation)

    already_queued = False
    try:
        queue.enqueue_support_request(request_id=accepted.request_id, task_name=task_name)
    except TaskAlreadyQueuedError:
        # An earlier delivery of this same event already created the work.
        already_queued = True
    except Exception as error:
        raise RequestNotQueuedError("could not queue the accepted request") from error

    requests.mark_queued(accepted.request_id, confirmed_task_name=task_name)
    return AcceptedForProcessing(
        request_id=accepted.request_id,
        created=accepted.created,
        already_queued=already_queued,
    )
