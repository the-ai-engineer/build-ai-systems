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

Unit tests need no database. Integration tests are skipped unless `DATABASE_URL` is set.
`uv run pyright` is configured but not yet clean; see the exceptions in [ARCHITECTURE.md](ARCHITECTURE.md).

## Repository structure

```text
ARCHITECTURE.md      How the system is put together today
PYTHON_STANDARDS.md  Coding and project structure standard
brief.md             Customer problem and first-release requirements
app/support_agent_app/
  api/               Public Slack webhook boundary
  worker/            Private worker boundary
  commands/          Operator actions
  application/       Use cases, domain vocabulary, protocols
  agent/             Prompts, tools, schemas, evidence checks
  database/          Connections, migrations, repositories
  integrations/      Slack, model provider, task queue
  testing/           Deterministic adapters, not for production
  settings.py        All configuration
migrations/          One SQL migration history
policies/            The approved policy set, used by the app and the examples
examples/            Small standalone AI engineering examples
  demos/             Runnable demos of the application slices
slack/               Bootstrap and deployment-stage Slack app manifests
docs/                Application docs and the implementation contract
MEMORY.md            Sanitized, non-authoritative coordination log
tests/unit/          No network, no database
tests/integration/   Real Postgres and real boundaries
```

Slack ingress, queues, cloud deployment, and operational checks are added by later linked implementation tasks.
