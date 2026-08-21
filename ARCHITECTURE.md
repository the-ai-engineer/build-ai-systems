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

Both runtimes ship as one container image, selected by the command. See
**The container image** below.

The worker is a FastAPI application with one route, `POST /tasks/process-support-request`.
Run it locally with:

```
uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
```

Postgres is the durable source of truth. Nothing else holds state.

## Components and what each owns

```
app/support_agent_app/
  api/            The public Slack webhook, whole
    main.py auth.py accept_request.py task_queue.py
  worker/         The private worker, whole
    main.py auth.py process_request.py deadlines.py failures.py
    messaging.py model_provider.py
    agent/        prompts.py tools.py schemas.py evidence.py agent.py pricing.py
  application/    The contract the two services share, and nothing else
    domain.py lifecycle.py protocols.py failures.py
  database/       Connections, migrations, repositories
  commands/       Deliberate operator actions
  testing/        Deterministic adapters, excluded from production
  settings.py     Typed configuration loading and runtime-specific validation
```

The layout is organised by **service**, not by technical role. Each runtime is one
folder you can read top to bottom, because each is deployed, scaled, and taught
separately. `agent/` sits inside `worker/` because the worker is its only caller.

`application/` holds only what both services must agree on: the vocabulary, the
lifecycle, the protocols, and the two send-failure types an integration raises
and a runtime catches. Anything used by one service lives in that service.

- `api/` owns the public boundary end to end: signature verification, event normalization, the accept use case, and the queue client that produces the task. Slack's wire shapes stop at `normalize_app_mention`.
- `worker/` owns the private boundary end to end: task identity, the process use case, the time budget, provider failure classification, the Slack client, the model provider, and the agent.
- `application/` is the seam between them. If a module here is only used by one service, it is in the wrong place.
- `agent/` owns everything the model touches, and lives under `worker/` because nothing else calls it. One route does not need a router module, a schemas module, and a composition root as three files. `auth.py` stays separate because swapping the static identity check for Google OIDC was a real, isolated change; it was made there and touched one other line of the route.
- `database/` owns SQL, transactions, and row mapping. Migrations live in root `migrations/`.
- Provider detail stays inside its adapter. Slack error codes and httpx exceptions do not escape `worker/messaging.py`.
- `testing/` owns the deterministic adapters, in-memory repositories, and fixtures.

## Which way dependencies point

```
api/  ->  application/ , database/
worker/  ->  application/ , database/
worker/agent/  ->  application/
```

`api/` and `worker/` never import each other. That is checkable in one grep, and
it is what makes independent deployment true rather than aspirational.

`application/` imports nothing from the layers above or beside it, with one recorded exception below.
`worker/main.py` and `api/main.py` are composition roots and are the only modules that name concrete adapters.

`WorkerService` takes a `SupportRequestStore`, a `PolicyRepository`, an `AgentRunner`, and a `SlackClient`.
It never learns that the store is Postgres, that the agent is Google ADK, or that the messaging platform is Slack.

## How one request flows

An employee mentions the assistant in the HR channel:

1. Slack posts the event to `POST /slack/events`. The webhook verifies the HMAC signature over the **raw body**, before parsing JSON, and rejects timestamps older than five minutes so a captured request cannot be replayed.
2. The event is normalized into an `IncomingSupportRequest`. Anything this app does not act on, including a mention from another workspace or channel, gets a 2xx without creating work, so Slack stops retrying something it was never going to act on.
3. `accept_and_queue` stores the request **before** creating the task, so a task can never point at work that is not durable. The task name is a SHA-256 of the Slack event ID and generation, so a Slack retry re-derives the same name and the queue rejects the duplicate.
4. The webhook acknowledges. It has called no model and read no policy (INV-2), which is what keeps it inside Slack's three second window.
5. The queue delivers the request ID to the worker later, on its own thread.

Then, in the worker:

6. A task arrives carrying only `request_id`. The employee's question stays in the database, so the queue never holds sensitive content.
7. `worker/auth.py` verifies the Google-signed OIDC token Cloud Tasks attached. A failure is a 401 before any work happens.
8. `WorkerService.process` claims the request with a fenced lease and receives a `Claim`.
9. It checks for a previously failed or stranded reply and resumes that path if one exists.
10. Otherwise it runs the agent, which may list the policy index and load at most three active documents.
11. `agent/evidence.py` verifies every citation against the documents the run actually loaded. An unverifiable answer becomes a human-review decision.
12. The verified decision is persisted, one outbound action is created, and the reply is sent to the Slack thread.
13. The result is recorded and the route maps it to a status code.

`tests/integration/api/test_end_to_end.py` runs all thirteen steps against a real Postgres, with only the model and Slack faked.

### Who may invoke the worker

The worker is private and proves who called it. `WORKER_TASK_AUTH` chooses the
check, `google-oidc` is the default, and `worker/main.py` is the only module
that names either authenticator.

`GoogleOidcTaskAuthenticator` reads the `Authorization: Bearer` header Cloud
Tasks attaches and requires four things: Google signed the token and it has not
expired, the audience is this worker, the issuer is Google, and the verified
email is `TASK_OIDC_SERVICE_ACCOUNT`. The audience is the worker's base URL,
because that is exactly what `api/task_queue.py` puts in the token it asks for;
`WORKER_BASE_URL` is that URL on both services, so the contract is one value and
not two that must be kept in step. Anything else is a 401 raised before the
route reaches the request, so an unauthorized caller costs a signature check and
no database work.

`StaticTaskAuthenticator` compares a shared string in `X-Worker-Task-Identity`.
It proves nothing about who called and exists so the two services can run on a
laptop with no Google identity to mint. It is never the deployed default: the
setting defaults to `google-oidc`, a `google-oidc` worker with no audience or
service account refuses to start, and a local run asks for `static` by name.
The two use different headers, so a static header presented to a deployed worker
is not a weaker credential, it is no credential at all.

Two locks, not one. Cloud Run's `run.invoker` binding rejects unknown callers
before the request reaches the process; the token check is the one that says
*which* identity, and it keeps holding if a binding is ever widened by mistake.

### The queue between them

`TaskQueue` has two implementations and `api/main.py` chooses between them by configuration. `TASK_QUEUE_BACKEND=cloud-tasks` selects `CloudTasksQueue`; anything else selects the local stand-in. No other module names either class.

`CloudTasksQueue` creates one HTTP task per accepted request. The task name is the full resource path ending in `task_name_for(...)`, so a Slack retry asks for a name the queue already holds and the API answers `AlreadyExists`. The adapter turns that into `TaskAlreadyQueuedError`, which `accept_and_queue` already treats as queued rather than failed. Google's deduplication only lasts about an hour after a task finishes; the request row, keyed by Slack event ID, is the durable guard. The task body carries the request ID and nothing else, and the worker is private, so each task carries an OIDC token Cloud Tasks mints for the webhook's own service account.

`LocalTaskQueue` is the explicit local stand-in, because Google Cloud has no supported emulator and the course does not add a third-party one. It keeps the shape that matters: enqueue returns immediately, delivery happens later on another thread, a duplicate task name is rejected, and a 503 is retried with backoff. Tasks live in memory and do not survive a restart. It is the one class Cloud Tasks replaces, and swapping them changes nothing above the `TaskQueue` protocol.

Because delivery is genuinely concurrent, the worker can claim a request and move it to `processing` before the webhook finishes writing `queued`. That is the system winning a race, not an error, so `mark_queued` becomes a no-op once the request has moved on under a claim.

## Durable data

Postgres owns everything, under one migration history in root `migrations/`.

- `support_documents` holds the approved policy set. `commands/seed_policies.py` loads it from root `policies/`.
- `support_requests` holds accepted requests and their lifecycle state, including lease version and attempt counts.
- `outbound_actions` holds each reply attempt with its exact text and content hash.
- `support_schema_migrations` records which migrations have run.

Migrations are never applied at application startup. An operator runs `apply-migrations`.

## Configuration

Root `config.toml` is the canonical source for safe application defaults.
`settings.py` loads it through Pydantic Settings and keeps separate models for
the worker boundary, worker application, model provider, and webhook. Each
runtime therefore validates only the values it needs and receives only the
secrets it owns.

Source priority is constructor values, environment variables, `.env`, file
secrets, then `config.toml`. The committed TOML file contains no credential or
deployment identity. Local secrets and machine-specific overrides live in the
ignored `.env`; Cloud Run injects production secrets from Secret Manager as
environment variables. Google Cloud project and location are also
environment-owned because they select the deployment and data-residency
boundary. The container image copies `config.toml` to `/srv`, its working
directory, so local processes and deployed processes use the same safe defaults.

## The cloud development environment

Google Cloud project `build-ai-systems-dev`, region `europe-west1`, built by
`scripts/provision-dev.sh` and removed by `scripts/teardown-dev.sh`. This is the
ground the deployment stands on; **Deployment topology** below is what runs on
it.

| Resource | Name | Holds |
|---|---|---|
| Artifact Registry | `support-agent` | Container images |
| Cloud SQL Postgres 17 | `support-agent-dev`, `db-f1-micro` | The `support_agent` database |
| Cloud Tasks | `support-requests` | Ten concurrent dispatches, five per second, five attempts |
| Secret Manager | `slack-bot-token`, `slack-signing-secret`, `database-url` | The three credentials |

Each runtime gets its own identity and only the access it needs:

| Identity | Project roles | Secrets it can read |
|---|---|---|
| `support-webhook` | `cloudsql.client`, `cloudtasks.enqueuer`, `iam.serviceAccountUser` on itself, `run.invoker` on the worker service | `slack-signing-secret`, `database-url` |
| `support-worker` | `cloudsql.client`, `aiplatform.user` | `slack-bot-token`, `database-url` |
| `support-maintenance` | `cloudsql.client` | `database-url` |

The webhook cannot post to Slack and the worker cannot enqueue tasks, which is
the same split the code already makes. `CloudTasksQueue` mints its OIDC token
for `support-webhook`, so that one identity is what both the invoker binding and
the worker's token check accept.

Two of the webhook's grants are about that token rather than about a resource.
Asking Cloud Tasks to mint a token as an account means acting as it, so the
webhook holds `iam.serviceAccountUser` on its own identity and on nothing else.
`run.invoker` is granted on the worker's Cloud Run service, which the
provisioning script does not create: until the first deploy it reports that the
service is missing and grants nothing. `scripts/deploy-dev.sh` grants the same
binding immediately after it deploys the worker, so provisioning does not have
to be run a second time. Both steps remove `allUsers` and
`allAuthenticatedUsers` if either ever appears on the worker, because the worker
is private and a public invoker is not a configuration choice it offers.

Secret values are read from a local `.env` and piped into Secret Manager on
stdin. They are never printed, logged, or placed on a command line. The database
password is generated once, stored inside the `database-url` secret, and reused
on every later run, so re-provisioning does not rotate a credential a running
service is holding.

## The container image

One root `Dockerfile` builds one image, and the container command decides which
runtime starts:

```
uvicorn support_agent_app.api.main:create_app    --factory --host 0.0.0.0 --port 8080
uvicorn support_agent_app.worker.main:create_app --factory --host 0.0.0.0 --port 8080
```

Nothing else differs. The webhook and the worker are the same code with
different composition roots, so making them different images would mean two
builds that can drift and two digests to reason about when one of them
misbehaves. The later maintenance jobs override the command the same way.

`scripts/build-and-push.sh` builds it for `linux/amd64`, which is what Cloud Run
runs, and pushes it to `europe-west1-docker.pkg.dev/build-ai-systems-dev/support-agent/support-agent`.
The tag is the short commit, so a deployment names the code it is running.

The build has two stages. The first resolves dependencies from `uv.lock` with
`uv sync --frozen`, then installs the application with `--no-editable` so the
virtual environment holds a real copy. The second stage carries that virtual
environment onto a plain Python base and runs as an unprivileged user that does
not own it.

What is deliberately not in the image:

- No `.env` and no credential. The build context is denied by default and the
  Dockerfile copies `pyproject.toml`, `uv.lock`, and `app/` only. Configuration
  arrives as environment variables and secrets at deploy time.
- No `support_agent_app/testing`. `WORKER_MODEL_SOURCE` already defaults to
  `configured` and `WORKER_SLACK_SINK` to `slack` (rule 8), and deleting the
  package makes that structural: a deployment cannot answer an employee from a
  canned model even if someone sets `WORKER_MODEL_SOURCE=fixture` by mistake. It
  fails with `ModuleNotFoundError` instead. `demo-workflow` is in the image and
  fails the same way, which is correct: a demo is not something a deployment
  runs.
What is in the image but no runtime reads: `migrations/` and `policies/`, at
`/srv/migrations` and `/srv/policies`. The operator commands run from this same
image as Cloud Run jobs, and a job cannot apply a migration it does not carry.
The webhook and the worker still never read either one: migrations are an
operator action and policies come from the database.

Both commands take the directory as an argument. They resolve their defaults
relative to their own module, which is the repository root in a checkout and a
path inside the virtual environment in the image, so the jobs name
`/srv/migrations` and `/srv/policies` rather than leaving a fixed path to be
found by a relative resolution that was never going to reach it. Naming a
directory an operator command will change is an operator's choice anyway.

Neither command can succeed over an absent directory. `apply_migrations` used to
glob one, find nothing, and print "Migrations are up to date" over an empty
schema; both now fail with the path they looked in.

## Deployment topology

`scripts/deploy-dev.sh` puts that one image into four places, and the order it
uses is the only real safety property it has:

| Order | Cloud Run resource | Runs as | Command |
|---|---|---|---|
| 1 | job `support-migrate` | `support-maintenance` | `apply-migrations --migrations-dir /srv/migrations` |
| 2 | job `support-seed-policies` | `support-maintenance` | `seed-policies --migrations-dir … --policies-dir …` |
| 3 | service `support-worker` | `support-worker` | `uvicorn support_agent_app.worker.main:create_app` |
| 4 | service `support-webhook` | `support-webhook` | `uvicorn support_agent_app.api.main:create_app` |

Both jobs finish before either service exists, so there is no window in which a
request can reach a schema that is not there (rule 7). The `run.invoker` binding
is granted between 3 and 4, so the private worker has exactly one permitted
caller before anything can send it work.

Services are deployed by digest, not by tag, because a tag can move between two
`gcloud run deploy` calls and "both services run the same build" would then be
something the script hoped for rather than something it did.

`WORKER_BASE_URL` is one value set on both services: the audience Cloud Tasks
writes into the token, and the audience the worker accepts. A service has no URL
until it exists, so the first deploy predicts the default Cloud Run hostname from
the service name and project number, then reads back the URL Cloud Run issued and
corrects the variable if they differ. They did differ on the first deploy here.
Cloud Run answers on both hostnames but only one can be the audience, and a
worker holding the other rejects every task with a 401 that looks like a broken
IAM binding.

The webhook is public, which the organization's
`constraints/iam.allowedPolicyMemberDomains` policy forbids by default: `allUsers`
is not a permitted member. This project holds a deliberate exception, recorded in
`docs/deploying-to-cloud-run.md`, because Slack presents no Google identity. The
exception is project-wide, since the constraint has no per-resource form, so the
worker's privacy rests on its own bindings and its token check rather than on
that policy.

`docs/deploying-to-cloud-run.md` holds the recorded proof that a task flows from
a signed Slack event to a cited reply with nothing running locally.

## Trust boundaries

- The employee's question is untrusted input.
- Model output is untrusted input. `AgentDecision` is a model-facing schema; only `AnswerDecision` and `HumanReviewDecision`, produced by `verify_decision`, reach the database or Slack.
- Policy documents are treated as content, never as instructions.
- The worker is private and authenticates every invocation, in the deployed system by verifying a Google-signed OIDC token from one service account. The webhook is public and verifies Slack signatures, because Slack cannot present a Google identity.

## Failure and recovery

The worker holds a bounded time budget (`deadlines.py`) and reserves time at the end of it so it can always record what happened.

Send failures are split three ways, because the correct recovery differs:

- **Clear failure**: Slack refused. Safe to retry.
- **Uncertain**: the send began and the outcome is unknown. Never blindly retried, because the employee may already have a reply.
- **Success**: recorded with the Slack message timestamp.

A claim is a fencing token. A worker whose lease has expired and been taken over cannot change durable state; it gets `StaleClaimError`. `app/support_agent_app/demos/run_state_machine.py` demonstrates this.

Retryable outcomes surface as HTTP 503 so the queue retries. Permanent failures do not.

## Rules future changes must preserve

1. `application/` does not import a web framework, a provider SDK, or a concrete adapter.
2. Only composition roots construct concrete adapters.
3. Model output is verified before any external side effect.
4. The queue carries a request ID, never question or policy text.
5. The webhook stores the request before creating a task, and never calls a model.
6. Run records exclude questions, answers, and policy text.
7. One migration history. No schema applied at startup.
8. Fixture adapters stay in `testing/` and are never the production default. The static task identity check is held to the same rule.

## Testing

Three kinds, separated by what each is allowed to touch.

- `tests/unit/` touches nothing external. Our own code only.
- `tests/functional/` uses real Postgres and a stub agent runner. These are about claims, leases, retries, duplicate delivery, and the webhook-to-worker path, none of which involve a model.
- `tests/evals/` calls the real model. Refusals, grounding, and budget adherence live here, because they are claims about a model and only a model can answer them.

Unit and functional tests never invoke a model. The rule that decides this:

> A scripted model as an adversary is useful. A scripted model as an oracle is worthless.

`test_parallel_model_calls_cannot_bypass_document_limit` scripts a model that
attempts four parallel document loads, to prove the guardrail holds. That is an
adversary, and no real model would do it reliably on demand. A test asserting
that the agent refuses a sensitive question, backed by a script written to
return that refusal, is an oracle asserting itself. One of those existed; it was
deleted, and against the real model two of its assertions were wrong.

## Recorded exceptions

**No `integrations/` package.**
`PYTHON_STANDARDS.md` puts external clients in `integrations/`. Every client here has exactly one caller, so each lives with the service that owns it: `api/task_queue.py`, `worker/messaging.py`, `worker/model_provider.py`. A shared `integrations/` would spread each service across one more directory for no reader benefit. Introduce it if a client ever gains a second caller.

**`worker/failures.py` imports provider exception types.**
`classify_workflow_failure` maps `google.genai` and `psycopg` exceptions to durable categories.

This is no longer a layering violation now that it lives inside the worker, which already knows both. It is recorded because the mapping is the one place provider error semantics are interpreted, and it should stay that way.

This is a decision, not a deferral. Inverting it means adding a classifier parameter to `WorkerService` and threading it through every call site and test, so that one thirteen-line function can move one directory. The mapping is small, tested, and in one place, and the rule it breaks exists to stop provider details leaking into orchestration, which is not happening here. It stays until a second provider makes the abstraction real.

**Provisioning lives in `scripts/`, not `infra/`.**
`PYTHON_STANDARDS.md` puts versioned infrastructure and deployment configuration
in `infra/`. There is no infrastructure configuration here, versioned or
otherwise: there are two bash scripts an operator runs. Naming a directory after
a category the repository does not yet have would send a reader looking for
manifests that do not exist. Introduce `infra/` when there is deployment
configuration to version, and move the scripts under it then.

There is also no Terraform. The course teaches the application, and a second
tool with its own state, providers, and failure modes would compete with that
for a student's attention. Two readable scripts show the same resources and the
same reasons.

**`ARCHITECTURE.md` exists before the design lesson.**
The course has students write their own architecture document first. This file is the reference they compare against afterwards, not a substitute for that exercise.

**Root holds course documents.**
`brief.md`, `MEMORY.md`, and `docs/` are teaching artifacts, not application structure.

**`SupportRequestStore` has fifteen methods and one implementation.**
That is more surface than an interface usually earns. It stays because it is the boundary that keeps `WorkerService` free of Postgres, which is the system's central design claim, and because a type checker verifies the match where `worker/main.py` passes the repository in. Writing it caught nine signature mismatches. `PostgresSupportRepository` deliberately does not inherit from it: a `Protocol` subclass silently inherits `...` bodies for anything it fails to implement, which would turn drift into a `None` return at runtime instead of a type error.

**The model's reason code is not a stable control signal.**
`format_slack_reply` chooses different user-visible text when `reason_code == "off_topic"`. That code is chosen by the model, and it is not stable: the same prompt-injection attempt came back as `off_topic` on one run and semantically identical refusals came back as `unsupported`. The refusal itself is reliable; the label is not. The evals therefore assert the decision and not the code. Branching user-visible behaviour on the label is a known weakness.

**Pyright is not yet clean.**
It reports 289 errors, against 261 on the same code before this structure existed.
They are dominated by psycopg query-overload typing in the repository modules and by untyped row access in the integration tests, neither of which this change introduced.
`ruff check` and `ruff format --check` are clean.
