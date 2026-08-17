# Architecture

This describes the system as it exists today, not the finished system.
`brief.md` holds the customer problem and `docs/final-agent-spec.md` holds the contract for the finished application.

## What runs

Two runtimes share one Python package, `app/support_agent_app`, and deploy independently.

| Runtime | Entry point | Exposure | Status |
|---|---|---|---|
| Worker | `worker/main.py` | Private. Accepts authenticated task invocations. | Built |
| Webhook | `api/main.py` | Public. Accepts Slack events. | Built |
| Commands | `commands/` | Operator only. | Built |

The worker is a FastAPI application with one route, `POST /tasks/process-support-request`.
Run it locally with:

```
uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
```

Postgres is the durable source of truth. Nothing else holds state.

## Components and what each owns

```
app/support_agent_app/
  api/            Public HTTP boundary for Slack events
  worker/         Private HTTP boundary for queued tasks
  commands/       Deliberate operator actions
  application/    Use cases, domain vocabulary, protocols
  agent/          Prompts, tools, model schemas, evidence checks
  database/       Connections, migrations, repositories
  integrations/   Slack, model provider, task queue
  testing/        Deterministic adapters, excluded from production
  settings.py     All configuration
```

- `application/` owns the vocabulary (`domain.py`, `lifecycle.py`), the boundaries (`protocols.py`), the time budget (`deadlines.py`), failure classification (`failures.py`), and the single use case (`process_request.py`). Reply formatting lives in `process_request.py` because it is one small function with one caller.
- `api/` is `main.py` and `auth.py`. Slack's wire shapes stop at `normalize_app_mention`; nothing downstream knows what Slack is. `auth.py` is separate because signature verification is the security boundary and is tested on its own.
- `worker/` is `main.py` and `auth.py`. One route does not need a router module, a schemas module, and a composition root as three files. `auth.py` stays separate because swapping the static identity check for Google OIDC is a real, isolated change.
- `agent/` owns everything the model touches: `prompts.py`, `tools.py`, the untrusted output schema in `schemas.py`, and the deterministic checks in `evidence.py`.
- `database/` owns SQL, transactions, and row mapping. Migrations live in root `migrations/`.
- `integrations/` owns provider detail. Slack error codes and httpx exceptions do not escape `messaging.py`.
- `testing/` owns the fake model, fake Slack client, in-memory repositories, and fixtures.

## Which way dependencies point

```
worker/ , api/ , commands/     ->  application/
agent/ , database/ , integrations/  ->  application/
```

`application/` imports nothing from the layers above or beside it, with one recorded exception below.
`worker/main.py` and `api/main.py` are composition roots and are the only modules that name concrete adapters.

`WorkerService` takes a `SupportRequestStore`, a `PolicyRepository`, an `AgentRunner`, and a `SlackClient`.
It never learns that the store is Postgres, that the agent is Pydantic AI, or that the messaging platform is Slack.

## How one request flows

An employee mentions the assistant in the HR channel:

1. Slack posts the event to `POST /slack/events`. The webhook verifies the HMAC signature over the **raw body**, before parsing JSON, and rejects timestamps older than five minutes so a captured request cannot be replayed.
2. The event is normalized into an `IncomingSupportRequest`. Anything this app does not act on, including a mention from another workspace or channel, gets a 2xx without creating work, so Slack stops retrying something it was never going to act on.
3. `accept_and_queue` stores the request **before** creating the task, so a task can never point at work that is not durable. The task name is a SHA-256 of the Slack event ID and generation, so a Slack retry re-derives the same name and the queue rejects the duplicate.
4. The webhook acknowledges. It has called no model and read no policy (INV-2), which is what keeps it inside Slack's three second window.
5. The queue delivers the request ID to the worker later, on its own thread.

Then, in the worker:

6. A task arrives carrying only `request_id`. The employee's question stays in the database, so the queue never holds sensitive content.
7. `worker/auth.py` checks the task identity. A failure is a 401 before any work happens.
8. `WorkerService.process` claims the request with a fenced lease and receives a `Claim`.
9. It checks for a previously failed or stranded reply and resumes that path if one exists.
10. Otherwise it runs the agent, which may list the policy index and load at most three active documents.
11. `agent/evidence.py` verifies every citation against the documents the run actually loaded. An unverifiable answer becomes a human-review decision.
12. The verified decision is persisted, one outbound action is created, and the reply is sent to the Slack thread.
13. The result is recorded and the route maps it to a status code.

`tests/integration/api/test_end_to_end.py` runs all thirteen steps against a real Postgres, with only the model and Slack faked.

### The queue between them

`LocalTaskQueue` is the explicit local stand-in for Cloud Tasks, because Google Cloud has no supported emulator and the course does not add a third-party one. It keeps the shape that matters: enqueue returns immediately, delivery happens later on another thread, a duplicate task name is rejected, and a 503 is retried with backoff. Tasks live in memory and do not survive a restart. Cloud Tasks replaces that one class.

Because delivery is genuinely concurrent, the worker can claim a request and move it to `processing` before the webhook finishes writing `queued`. That is the system winning a race, not an error, so `mark_queued` becomes a no-op once the request has moved on under a claim.

## Durable data

Postgres owns everything, under one migration history in root `migrations/`.

- `support_documents` holds the approved policy set. `commands/seed_policies.py` loads it from root `policies/`.
- `support_requests` holds accepted requests and their lifecycle state, including lease version and attempt counts.
- `outbound_actions` holds each reply attempt with its exact text and content hash.
- `support_schema_migrations` records which migrations have run.

Migrations are never applied at application startup. An operator runs `apply-migrations`.

## Trust boundaries

- The employee's question is untrusted input.
- Model output is untrusted input. `AgentDecision` is a model-facing schema; only `AnswerDecision` and `HumanReviewDecision`, produced by `verify_decision`, reach the database or Slack.
- Policy documents are treated as content, never as instructions.
- The worker is private and authenticates every invocation. The webhook will be public and verifies Slack signatures.

## Failure and recovery

The worker holds a bounded time budget (`deadlines.py`) and reserves time at the end of it so it can always record what happened.

Send failures are split three ways, because the correct recovery differs:

- **Clear failure**: Slack refused. Safe to retry.
- **Uncertain**: the send began and the outcome is unknown. Never blindly retried, because the employee may already have a reply.
- **Success**: recorded with the Slack message timestamp.

A claim is a fencing token. A worker whose lease has expired and been taken over cannot change durable state; it gets `StaleClaimError`. `examples/demos/run_state_machine.py` demonstrates this.

Retryable outcomes surface as HTTP 503 so the queue retries. Permanent failures do not.

## Rules future changes must preserve

1. `application/` does not import a web framework, a provider SDK, or a concrete adapter.
2. Only composition roots construct concrete adapters.
3. Model output is verified before any external side effect.
4. The queue carries a request ID, never question or policy text.
5. The webhook stores the request before creating a task, and never calls a model.
6. Run records exclude questions, answers, and policy text.
7. One migration history. No schema applied at startup.
8. Fixture adapters stay in `testing/` and are never the production default.

## Recorded exceptions

**`application/failures.py` imports provider exception types.**
`classify_workflow_failure` maps `pydantic_ai` and `psycopg` exceptions to durable categories, so the application layer imports two provider packages.

This is a decision, not a deferral. Inverting it means adding a classifier parameter to `WorkerService` and threading it through every call site and test, so that one thirteen-line function can move one directory. The mapping is small, tested, and in one place, and the rule it breaks exists to stop provider details leaking into orchestration, which is not happening here. It stays until a second provider makes the abstraction real.

**`ARCHITECTURE.md` exists before the design lesson.**
The course has students write their own architecture document first. This file is the reference they compare against afterwards, not a substitute for that exercise.

**Root holds course documents.**
`brief.md`, `MEMORY.md`, and `docs/` are teaching artifacts, not application structure.

**No `CloudTasksQueue` yet.**
`integrations/task_queue.py` holds only the local adapter. The Cloud Tasks client belongs to the queue-integration lesson, needs a Google Cloud project to verify, and would otherwise be untested code shipped on the strength of a docstring. `TaskQueue` in `protocols.py` is the seam it drops into, and `task_name_for` already implements the deterministic naming rule both adapters need.

**`SupportRequestStore` has fifteen methods and one implementation.**
That is more surface than an interface usually earns. It stays because it is the boundary that keeps `WorkerService` free of Postgres, which is the system's central design claim, and because a type checker verifies the match where `worker/main.py` passes the repository in. Writing it caught nine signature mismatches. `PostgresSupportRepository` deliberately does not inherit from it: a `Protocol` subclass silently inherits `...` bodies for anything it fails to implement, which would turn drift into a `None` return at runtime instead of a type error.

**Pyright is not yet clean.**
It reports 259 errors, against 261 on the same code before this structure existed.
They are dominated by psycopg query-overload typing in the repository modules and by untyped row access in the integration tests, neither of which this change introduced.
`ruff check` and `ruff format --check` are clean.
