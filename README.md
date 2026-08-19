# Build AI Systems

Public code repository for the Build AI Systems course.

The project builds a professional HR policy assistant in Python.
An employee mentions it in a dedicated Slack channel, the system processes the request asynchronously, retrieves approved policies from Postgres, and replies in the Slack thread.
It refuses off-topic requests and gives uncertain, unsupported, sensitive, or conflicting requests a fixed reply that asks the employee to contact HR.

## Repository boundary

Canonical written lessons, diagrams, scripts, and teaching material live in `/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/`.
This public repository owns runnable code, tests, policies, deployment configuration, and the [finished application specification](docs/final-agent-spec.md).
Do not duplicate paid lesson prose here.

`MEMORY.md` is a sanitized coordination log, not a source of truth.
`ai-engineer-curriculum` is not part of the active Build AI Systems workflow.

## Application contract

The public Cloud Run webhook verifies Slack requests, stores accepted work, and creates a Cloud Task containing only the internal `request_id`.
The private Cloud Run worker claims the request with a fenced lease, runs the policy workflow, and records one controlled Slack action.
Postgres is the durable source of truth.

The finished application uses Pydantic AI's Google Cloud provider with configurable `google-cloud:gemini-3.5-flash` as the current tested default.
Local authenticated integration uses Application Default Credentials.
Cloud Run uses its runtime service identity and does not require a separate Gemini API key.
Deterministic fake-model tests remain required.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the system is put together today, [docs/final-agent-spec.md](docs/final-agent-spec.md) for the complete implementation contract, and [docs/course-code-map.md](docs/course-code-map.md) for the short lesson-to-code map.
[PYTHON_STANDARDS.md](PYTHON_STANDARDS.md) is the coding and structure standard for this repository.
Use [docs/slack-setup.md](docs/slack-setup.md) and the versioned manifests in `slack/` to configure the course Slack app without enabling event delivery before the webhook exists.

## Run the local policy agent

The first application slice runs with synthetic fixtures and a deterministic Pydantic AI model.
It needs no Slack, Google Cloud, database, model credentials, or network access.

```bash
uv sync
uv run python -m unittest discover -s tests/unit -t .
uv run python -m examples.demos.run_workflow --fixture documented
uv run python -m examples.demos.run_workflow --fixture unsupported
uv run python -m examples.demos.run_workflow --fixture prompt-injection
```

See [docs/local-policy-agent.md](docs/local-policy-agent.md) for the optional Postgres and Google Cloud model paths.

## Run the local worker

The worker loads a synthetic request that is already stored in Postgres.

Copy `.env.example` to `.env` and set `DATABASE_URL`, then apply the schema:

```bash
cp .env.example .env
uv run apply-migrations
uv run seed-policies
```

`apply-migrations` and `seed-policies` are installed commands and find the root
`.env` from anywhere in the tree. The demos are run with `python -m examples...`,
so they must be run from the repository root.

The demos build deterministic fake model and Slack adapters directly, so they
make no Google Cloud or Slack call:

```bash
uv run python -m unittest discover -s tests/integration -t .
uv run python -m examples.demos.run_worker --fixture documented
uv run python -m examples.demos.run_worker --fixture human-review
uv run python -m examples.demos.run_worker --fixture uncertain-send
```

The worker service itself defaults to the real adapters. Ask for the fixture
adapters explicitly when running it without Slack credentials:

```bash
WORKER_ADAPTER_MODE=local-fixtures \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
```

## Run the whole thing locally

### The fastest look

One command drives every stage, from a signed Slack event to the reply text the
employee would see. The model and Slack are deterministic fakes, so it needs no
credentials and sends nothing:

```bash
uv run python -m examples.demos.run_end_to_end
```

### The demo worth showing

Run the webhook and the worker as two processes, which is the shape the deployed
system actually has, then drive it with signed events.

First, set up the database once:

```bash
cp .env.example .env          # set DATABASE_URL
uv run apply-migrations
uv run seed-policies
```

Terminal 1, the private worker:

```bash
DATABASE_URL="postgresql:///support_agent" \
WORKER_ADAPTER_MODE=local-fixtures \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
```

Terminal 2, the public webhook. It owns the local queue that delivers to the
worker:

```bash
DATABASE_URL="postgresql:///support_agent" \
SLACK_SIGNING_SECRET=demo-secret \
SLACK_ALLOWED_TEAM_IDS=T-demo \
SLACK_ALLOWED_CHANNEL_IDS=C-demo \
WORKER_BASE_URL=http://127.0.0.1:8081 \
  uv run uvicorn support_agent_app.api.main:create_app --factory --port 8080
```

Terminal 3, send a mention. It signs the request the way Slack does, then reads
the outcome from Postgres:

```bash
DATABASE_URL="postgresql:///support_agent" \
  uv run python -m examples.demos.send_slack_event \
    --question "Can unused annual leave be carried into next year?"
```

```text
webhook responded 200
watching Postgres for the worker to finish...
status: completed
business attempts: 1
action: succeeded
--- the reply in the Slack thread ---
You may carry up to five unused days into the next holiday year with manager approval.

Sources
- annual-leave-policy.md
```

The reply is read from the durable record, not from a log, because the complete
message text is deliberately never logged. Postgres is the source of truth.

### Asking your own question

Both demos take `--question`. Add `--live-model` to make it mean something: the
deterministic fixture model returns a canned decision and ignores what you typed,
and the demos say so if you forget.

Straight at the agent, no database, fastest loop:

```bash
uv run python -m examples.demos.run_workflow \
  --question "How much annual leave can I carry over?" --live-model
```

Through the durable worker path, so you also see the claim, the decision record,
and the outbound action:

```bash
DATABASE_URL="postgresql:///support_agent" \
  uv run python -m examples.demos.run_worker \
    --question "How much annual leave can I carry over?" --live-model
```

`--live-model` needs `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
Application Default Credentials.

### Things worth demonstrating

| What to show | How |
|---|---|
| A cited answer | the command above |
| The fixed human-review reply | restart the worker with `WORKER_FAKE_FIXTURE=sensitive` |
| A refused prompt injection | restart the worker with `WORKER_FAKE_FIXTURE=prompt-injection` |
| A forged request is rejected | add `--signing-secret wrong-secret`, and the webhook answers 401 with nothing stored |
| Another channel is ignored | add `--channel-id C-other`, and the webhook answers 200 but creates no work |
| A stale worker cannot reply twice | `uv run python -m examples.demos.run_state_machine` |

`WORKER_FAKE_FIXTURE` chooses which canned decision the fake model returns, so
the question you type does not change the answer in fixture mode. Swap to
`WORKER_ADAPTER_MODE=configured` with Google Cloud credentials and a Slack bot
token to make the model and the reply real.

### Notes

The webhook is `POST /slack/events`. It verifies the Slack signature over the raw
body, stores the request, hands the queue a request ID, and acknowledges. It
never calls a model, which is what keeps it inside Slack's three second window.

Google Cloud has no supported Cloud Tasks emulator and the course does not add a
third-party one, so `LocalTaskQueue` is the explicit local stand-in. Cloud Tasks
replaces that one class and nothing else. Tasks live in memory, so a restart
loses anything undelivered.

Real Slack needs a public HTTPS URL, so put a temporary tunnel in front of port
8080 and use the real signing secret. See [docs/slack-setup.md](docs/slack-setup.md).

## Provision the cloud development environment

Two scripts stand the Google Cloud development environment up and take it down
again. There is no Terraform: this course teaches the application, not an
infrastructure tool.

```bash
scripts/provision-dev.sh
```

It enables the required APIs, then creates an Artifact Registry repository, a
Cloud Tasks queue, the smallest Cloud SQL Postgres instance, the three runtime
service accounts (`support-webhook`, `support-worker`, `support-maintenance`),
and the Secret Manager secrets each one is allowed to read.

The script is re-runnable. Every step checks for the resource first, so a second
run reports what already exists and changes nothing. Defaults are overridable:

```bash
PROJECT_ID=... REGION=... ENV_FILE=... scripts/provision-dev.sh
```

`SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` are read from `ENV_FILE` (`.env` by
default) and piped into Secret Manager on stdin. The script never prints a
secret and never puts one on a command line. The database password is generated
once, stored inside the `database-url` secret, and reused on later runs, so
re-running the script does not rotate a credential a deployed service is holding.

### What it costs

Cloud Run scales to zero. Cloud SQL does not, so it is effectively the whole
bill: a `db-f1-micro` instance with 10 GB of SSD, left running, is roughly **$10
to $15 a month**. Artifact Registry, Cloud Tasks, Secret Manager, and the
service accounts are pennies or free at development volume. Treat that as an
estimate and check the real number against the
[Cloud SQL pricing page](https://cloud.google.com/sql/pricing) and your billing
account.

Delete the billable resources when you are done for the day:

```bash
scripts/teardown-dev.sh
```

Cloud SQL goes first, then Artifact Registry and the secrets. The Cloud Tasks
queue is purged and paused rather than deleted, because Cloud Tasks reserves a
deleted queue name for about a week and an idle queue costs nothing. Service
accounts and enabled APIs stay for the same reason: they are free, and deleting
a service account leaves stale IAM bindings behind it.

`--dry-run` shows what would go without deleting anything. Cloud SQL also
reserves a deleted instance name for about a week, so if you tear down and want
to rebuild sooner than that, provision with a different `SQL_INSTANCE`.

## Run the examples

Install the Python dependencies:

```bash
uv sync
cp examples/.env.sample examples/.env
```

Run an example:

```bash
uv run python examples/01_basic_model_call.py
```

The model examples require the matching provider credentials.
The whole-document, vector, and hybrid RAG examples use the OpenAI API.
The SQL RAG example uses an in-memory SQLite database and needs no setup.

## Verify the repository

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
uv run python examples/06b_sql_rag.py
```

Tests come in three kinds, and the difference is what each is allowed to touch.

| | Needs | Answers |
|---|---|---|
| `tests/unit/` | nothing | Is our own code correct? |
| `tests/functional/` | Postgres | Does the system hold together under failure and retry? |
| `tests/evals/` | Gemini, costs money | How does the real model behave? |

```bash
uv run python -m unittest discover -s tests/unit -t .        # fast, offline, free
DATABASE_URL=... uv run python -m unittest discover -s tests/functional -t .
GOOGLE_CLOUD_PROJECT=... uv run python -m unittest discover -s tests/evals -t .
```

Unit and functional tests never call a model. Where they need a decision, they
use a stub agent runner from `tests/fakes/`, because a scripted model asserting
its own script proves nothing. The one legitimate use of a scripted model is as
an adversary: `test_parallel_model_calls_cannot_bypass_document_limit` scripts a
model that tries to load four documents, to prove the guardrail holds.

Evals skip unless `GOOGLE_CLOUD_PROJECT` is set. They take about a minute and
cost a few cents.

`uv run pyright` is configured but not yet clean; see the exceptions in [ARCHITECTURE.md](ARCHITECTURE.md).

## Repository structure

```text
ARCHITECTURE.md      How the system is put together today
PYTHON_STANDARDS.md  Coding and project structure standard
brief.md             Customer problem and first-release requirements
app/support_agent_app/
  api/               The public Slack webhook, whole
  worker/            The private worker, whole
    agent/           Prompts, tools, schemas, evidence checks
  application/       Only what both services share
  database/          Connections, migrations, repositories
  commands/          Operator actions
  testing/           Deterministic adapters, not for production
  settings.py        All configuration
migrations/          One SQL migration history
policies/            The approved policy set, used by the app and the examples
examples/            Small standalone AI engineering examples
  demos/             Runnable demos of the application slices
slack/               Bootstrap and deployment-stage Slack app manifests
scripts/             Provision and tear down the cloud development environment
docs/                Application docs and the implementation contract
MEMORY.md            Sanitized, non-authoritative coordination log
tests/unit/          No network, no database, no model
tests/functional/    Real Postgres, stubbed agent
tests/evals/         Real model, skipped without credentials
```

Slack ingress, queues, cloud deployment, and operational checks are added by later linked implementation tasks.
