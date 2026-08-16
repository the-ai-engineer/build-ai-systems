# Architecture

This describes the system as it exists today, not the finished system.
`brief.md` holds the customer problem and `docs/final-agent-spec.md` holds the contract for the finished application.

## What runs

Two runtimes share one Python package, `app/support_agent_app`, and deploy independently.

| Runtime | Entry point | Exposure | Status |
|---|---|---|---|
| Worker | `worker/main.py` | Private. Accepts authenticated task invocations. | Built |
| Webhook | `api/main.py` | Public. Accepts Slack events. | Sketched, not implemented |
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
  api/            Public HTTP boundary for Slack events        (sketched)
  worker/         Private HTTP boundary for queued tasks
  commands/       Deliberate operator actions
  application/    Use cases, domain vocabulary, protocols
  agent/          Prompts, tools, model schemas, evidence checks
  database/       Connections, migrations, repositories
  integrations/   Slack, model provider, task queue
  testing/        Deterministic adapters, excluded from production
  settings.py     All configuration
```

- `application/` owns the vocabulary (`domain.py`, `lifecycle.py`), the boundaries (`protocols.py`), the time budget (`deadlines.py`), failure classification (`failures.py`), and the single use case (`process_request.py`).
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

Today, starting from a request already stored in Postgres:

1. A task arrives at the worker carrying only `request_id`. The employee's question stays in the database, so the queue never holds sensitive content.
2. `worker/auth.py` checks the task identity. A failure is a 401 before any work happens.
3. `WorkerService.process` claims the request with a fenced lease and receives a `Claim`.
4. It checks for a previously failed or stranded reply and resumes that path if one exists.
5. Otherwise it runs the agent, which may list the policy index and load at most three active documents.
6. `agent/evidence.py` verifies every citation against the documents the run actually loaded. An unverifiable answer becomes a human-review decision.
7. The verified decision is persisted, one outbound action is created, and the reply is sent to the Slack thread.
8. The result is recorded and the route maps it to a status code.

The public webhook step, and the Cloud Tasks step between it and the worker, are not built yet.

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
5. Run records exclude questions, answers, and policy text.
6. One migration history. No schema applied at startup.
7. Fixture adapters stay in `testing/` and are never the production default.

## Recorded exceptions

**`application/failures.py` imports provider exception types.**
`classify_workflow_failure` maps `pydantic_ai` and `psycopg` exceptions to durable categories, so the application layer imports two provider packages. Moving it behind an injected classifier is the correct fix and is deliberately deferred; the mapping is small, tested, and in one place.

**`ARCHITECTURE.md` exists before the design lesson.**
The course has students write their own architecture document first. This file is the reference they compare against afterwards, not a substitute for that exercise.

**Root holds course documents.**
`brief.md`, `MEMORY.md`, and `docs/` are teaching artifacts, not application structure.

**`api/` and `integrations/task_queue.py` are sketched, not implemented.**
The standard says not to create directories that own no code. These are deliberate exceptions: the webhook and queue are known parts of the design, and naming them now makes the shape of the finished system visible while it is being built. Each file states what it will own. They must be implemented or deleted, not left indefinitely.

**Pyright is not yet clean.**
It reports 259 errors, against 261 on the same code before this structure existed.
They are dominated by psycopg query-overload typing in the repository modules and by untyped row access in the integration tests, neither of which this change introduced.
`ruff check` and `ruff format --check` are clean.
