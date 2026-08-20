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

## Build the container image

One image holds both runtimes. Which one starts is the container command, so the
webhook and the worker deploy the same digest and cannot drift apart.

```bash
scripts/build-and-push.sh              # build for linux/amd64 and push
scripts/build-and-push.sh --no-push    # build only
PROJECT_ID=... REGION=... TAG=... scripts/build-and-push.sh
```

It pushes to the Artifact Registry repository the provisioning script created,
`europe-west1-docker.pkg.dev/build-ai-systems-dev/support-agent/support-agent`,
tagged with the short commit and with `latest`. Deploy the commit tag: it names
the code that is running. Cloud Run runs x86-64, so the build is `linux/amd64`
even on an Apple Silicon machine.

The image holds the application and its dependencies, and nothing else. No
`.env`, no credential, and no `support_agent_app/testing`: the fixture adapters
are deleted from the image, so a deployment cannot answer an employee from a
canned model even if `WORKER_ADAPTER_MODE` is set by mistake. It also carries no
`migrations/` and no `policies/`, because neither runtime reads them, so
`apply-migrations` and `seed-policies` do not run inside it. They fail saying
where they looked. Run them from a checkout.

### Run the two runtimes locally

Build it, then start each runtime with its own command. Postgres here is the
local one, reached over the host loopback:

```bash
docker build -t support-agent:local .

docker run --rm -p 8081:8080 \
  -e DATABASE_URL="postgresql://user:password@host.docker.internal:5432/support_agent" \
  -e SLACK_BOT_TOKEN="xoxb-..." \
  support-agent:local \
  uvicorn support_agent_app.worker.main:create_app --factory --host 0.0.0.0 --port 8080

docker run --rm -p 8080:8080 \
  -e DATABASE_URL="postgresql://user:password@host.docker.internal:5432/support_agent" \
  -e SLACK_SIGNING_SECRET=demo-secret \
  -e SLACK_ALLOWED_TEAM_IDS=T-demo -e SLACK_ALLOWED_CHANNEL_IDS=C-demo \
  -e WORKER_BASE_URL=http://host.docker.internal:8081 \
  support-agent:local
```

The webhook is the default command, so it needs none. `host.docker.internal`
only works when Postgres accepts connections from outside loopback; a Postgres
that listens on `localhost` alone is not reachable from a container, and the
simplest answer there is to run Postgres in a container on the same Docker
network and point both runtimes at it by name.

The worker uses the real model and Slack adapters by default. Without cloud
credentials in the container it will accept a request, claim it, and record
`model_configuration` as the failure, which is the correct loud answer rather
than a canned reply.

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
Dockerfile           One image, both runtimes, selected by the command
scripts/             Operator scripts, including the image build and push
docs/                Application docs and the implementation contract
MEMORY.md            Sanitized, non-authoritative coordination log
tests/unit/          No network, no database, no model
tests/functional/    Real Postgres, stubbed agent
tests/evals/         Real model, skipped without credentials
```

Slack ingress, queues, cloud deployment, and operational checks are added by later linked implementation tasks.
