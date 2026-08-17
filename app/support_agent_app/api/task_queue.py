"""Queue adapters that carry one request ID to the worker.

Google Cloud has no supported Cloud Tasks emulator, and the course does not add
a third-party one. `LocalTaskQueue` is the explicit local stand-in instead. It
is deliberately visible rather than hidden behind a mock, because the thing it
imitates is the part of the system most likely to surprise you: enqueueing is
fast and synchronous, delivery is neither.

It keeps the shape that matters:

- enqueue returns as soon as the queue owns the task, so the webhook can answer
  Slack in time
- delivery happens later, on another thread, against the worker's HTTP boundary
- a duplicate task name is rejected, not delivered twice
- a 503 from the worker is retried with backoff; a 4xx is not

It is not Cloud Tasks. Tasks live in memory, so they do not survive a restart,
and there is no shared queue across processes. Cloud Tasks replaces this class
and nothing else.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from uuid import UUID

import httpx

from ..application.lifecycle import TaskAlreadyQueuedError

logger = logging.getLogger(__name__)

WORKER_TASK_PATH = "/tasks/process-support-request"
MAX_DELIVERY_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 0.5
BACKOFF_MULTIPLIER = 2.0


@dataclass(frozen=True)
class _Delivery:
    request_id: UUID
    task_name: str
    attempt: int = 1


class LocalTaskQueue:
    """An in-process queue that delivers to a worker over HTTP.

    Start it with `start()` and stop it with `stop()`, or use it as a context
    manager. A composition root owns its lifetime.
    """

    def __init__(
        self,
        *,
        worker_base_url: str,
        task_identity: str,
        identity_header: str,
        client: httpx.Client | None = None,
        max_delivery_attempts: int = MAX_DELIVERY_ATTEMPTS,
        request_timeout_seconds: float = 65.0,
    ) -> None:
        if not worker_base_url:
            raise ValueError("worker_base_url is required")
        if not task_identity:
            raise ValueError("task_identity is required")
        self._worker_base_url = worker_base_url.rstrip("/")
        self._task_identity = task_identity
        self._identity_header = identity_header
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self._max_delivery_attempts = max_delivery_attempts
        self._request_timeout_seconds = request_timeout_seconds

        self._pending: Queue[_Delivery] = Queue()
        self._accepted_names: set[str] = set()
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._dispatcher: threading.Thread | None = None
        # Deliveries accepted but not yet finished, so tests can wait on the
        # queue draining without polling the worker or sleeping a fixed time.
        self._outstanding = 0
        self._settled = threading.Condition()

    # -- the queue boundary the application sees --------------------------

    def enqueue_support_request(self, *, request_id: UUID, task_name: str) -> None:
        if self._stopping.is_set():
            raise RuntimeError("the local task queue is not running")
        with self._lock:
            if task_name in self._accepted_names:
                raise TaskAlreadyQueuedError(task_name)
            self._accepted_names.add(task_name)
        self._track(1)
        self._pending.put(_Delivery(request_id=request_id, task_name=task_name))

    # -- lifetime ---------------------------------------------------------

    def start(self) -> None:
        if self._dispatcher is not None:
            return
        self._stopping.clear()
        self._dispatcher = threading.Thread(
            target=self._dispatch_forever,
            name="local-task-queue",
            daemon=True,
        )
        self._dispatcher.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stopping.set()
        dispatcher = self._dispatcher
        if dispatcher is not None:
            dispatcher.join(timeout=timeout_seconds)
        self._dispatcher = None
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> LocalTaskQueue:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def wait_until_delivered(self, *, timeout_seconds: float = 30.0) -> bool:
        """Block until every accepted task has been delivered or given up on.

        For tests and demos only. Nothing in the request path calls this.
        """
        with self._settled:
            return self._settled.wait_for(lambda: self._outstanding == 0, timeout_seconds)

    def _track(self, delta: int) -> None:
        with self._settled:
            self._outstanding += delta
            if self._outstanding == 0:
                self._settled.notify_all()

    # -- delivery ---------------------------------------------------------

    def _dispatch_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                delivery = self._pending.get(timeout=0.1)
            except Empty:
                continue
            try:
                self._deliver(delivery)
            finally:
                self._track(-1)

    def _deliver(self, delivery: _Delivery) -> None:
        try:
            response = self._client.post(
                f"{self._worker_base_url}{WORKER_TASK_PATH}",
                headers={self._identity_header: self._task_identity},
                json={"request_id": str(delivery.request_id)},
                timeout=self._request_timeout_seconds,
            )
        except httpx.HTTPError as error:
            self._retry(delivery, reason=type(error).__name__)
            return

        if response.status_code == 503:
            self._retry(delivery, reason="worker asked for a retry")
            return
        if response.status_code >= 400:
            # A 4xx is the worker refusing the task. Retrying cannot help.
            logger.error(
                "task %s rejected by the worker with status %s",
                delivery.task_name,
                response.status_code,
            )
            return
        logger.info("task %s delivered", delivery.task_name)

    def _retry(self, delivery: _Delivery, *, reason: str) -> None:
        if delivery.attempt >= self._max_delivery_attempts:
            logger.error(
                "task %s gave up after %s attempts (%s)",
                delivery.task_name,
                delivery.attempt,
                reason,
            )
            return
        backoff = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (delivery.attempt - 1))
        logger.warning(
            "task %s attempt %s failed (%s), retrying in %.1fs",
            delivery.task_name,
            delivery.attempt,
            reason,
            backoff,
        )
        if self._stopping.wait(backoff):
            return
        self._track(1)
        self._pending.put(
            _Delivery(
                request_id=delivery.request_id,
                task_name=delivery.task_name,
                attempt=delivery.attempt + 1,
            )
        )
