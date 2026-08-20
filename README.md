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

## Configuration

[`config.toml`](config.toml) is the canonical source for safe application
defaults such as the model, worker deadline, authentication mode, and local
queue settings. The Pydantic Settings classes in
`app/support_agent_app/settings.py` load and validate it separately for the
worker and webhook runtimes.

Configuration precedence is explicit: constructor values, environment
variables, `.env`, then `config.toml`. Copy `.env.example` to `.env` for local
secrets, deployment identifiers, and machine-specific overrides. Cloud Run
receives production secrets from Secret Manager as environment variables.
The Google Cloud project and location also remain environment-owned because
they select the deployment and its data-residency boundary.
Never put a database URL, Slack token, signing secret, or credential in
`config.toml`.

## Run the local policy agent

The first application slice runs with synthetic fixtures and a deterministic Pydantic AI model.
It needs no Slack, Google Cloud, database, model credentials, or network access.

```bash
uv sync
uv run python -m unittest discover -s tests/unit -t .
uv run demo-workflow --fixture documented
uv run demo-workflow --fixture unsupported
uv run demo-workflow --fixture prompt-injection
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
uv run demo-worker --fixture documented
uv run demo-worker --fixture human-review
uv run demo-worker --fixture uncertain-send
```

The worker service itself defaults to the real adapters, and to the real
identity check. Ask for the fixture adapters and the local identity check
explicitly when running it without Slack or Google credentials:

```bash
WORKER_MODEL_SOURCE=fixture WORKER_SLACK_SINK=record \
WORKER_TASK_AUTH=static \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081
```

## Run the whole thing locally

### The fastest look

One command drives every stage, from a signed Slack event to the reply text the
employee would see. The model and Slack are deterministic fakes, so it needs no
credentials and sends nothing:

```bash
uv run demo-end-to-end
```

### One script, every call shown

```bash
./demo.sh                 # canned model, nothing external needed but Postgres
./demo.sh --live-model    # real Gemini
```

It starts both services and drives them with plain curl, printing every command
before running it: a direct worker call, a rejected unauthenticated call, a
signed Slack event, a rejected forged signature, and the stored reply. Nothing in
it is a trick you could not type yourself.

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
WORKER_MODEL_SOURCE=fixture WORKER_SLACK_SINK=record \
WORKER_TASK_AUTH=static \
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
  uv run demo-slack-event \
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
uv run demo-workflow \
  --question "How much annual leave can I carry over?" --live-model
```

Through the durable worker path, so you also see the claim, the decision record,
and the outbound action:

```bash
DATABASE_URL="postgresql:///support_agent" \
  uv run demo-worker \
    --question "How much annual leave can I carry over?" --live-model
```

`--live-model` needs `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
Application Default Credentials.

### What is real when you run it locally

The system talks to four things outside itself. Locally each is chosen
independently, which is the whole reason the local setup is workable at all.

| Boundary | Locally | In production |
|---|---|---|
| Postgres | real, on your machine | Cloud SQL |
| Model | real Gemini via Vertex AI, or a canned decision | Vertex AI |
| Task queue | `LocalTaskQueue`, a background thread **inside the webhook process** | Cloud Tasks |
| Slack outbound | recorded to Postgres, or really sent | Slack Web API |

Two questions this always raises:

**Where is the task runner?** There isn't a separate one. `LocalTaskQueue` lives
inside the webhook process. When the webhook accepts an event it puts the request
ID on an in-memory queue, and a background thread POSTs it to the worker's real
HTTP endpoint. So the worker really is called over HTTP, by a thread in the other
process. Cloud Tasks replaces that one class and nothing else. If you POST to the
worker yourself with curl, no queue is involved at all.

**Where does the reply go without Slack?** With `WORKER_SLACK_SINK=record`,
nowhere on the network. This matters less than it sounds: the reply text is
written to `outbound_actions.outbound_text` in Postgres *before* any send is
attempted, so the employee-visible text exists either way. The sink only decides
whether the network is involved. That is why `demo.sh` reads the reply out of the
database rather than out of a log.

```bash
WORKER_MODEL_SOURCE=configured   # real Gemini, needs GOOGLE_CLOUD_PROJECT + ADC
WORKER_SLACK_SINK=record         # no Slack workspace needed
```

That combination is the normal way to develop: real AI, no Slack.

### Demo A: real Slack reply, no tunnel

The worker posts *outbound* to Slack, so it needs no inbound reachability. This
runs entirely on your laptop and a real employee sees a real answer.

You need: a bot token, the bot invited to a channel, and a message to reply under.
In Slack, copy a message link. The `.../p1699999999000100` part is the timestamp
`1699999999.000100`.

```bash
# terminal 1: the worker, real model, real Slack
SLACK_BOT_TOKEN=xoxb-... \
WORKER_MODEL_SOURCE=configured WORKER_SLACK_SINK=slack \
WORKER_TASK_AUTH=static \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081

# terminal 2
uv run demo-seed-request \
  --question "How much annual leave do I get?" \
  --channel-id C0123456789 \
  --thread-ts 1699999999.000100
# then paste the curl it prints
```

The reply appears in the Slack thread. No webhook, no queue, no tunnel: you are
driving the worker's HTTP endpoint yourself, exactly as Cloud Tasks will.

### Demo B: the full loop, mention to reply

Here Slack has to reach *you*, so this one needs a tunnel. Only the webhook is
exposed. The worker stays private, as it is in production.

```bash
# terminal 1: the private worker
SLACK_BOT_TOKEN=xoxb-... \
WORKER_MODEL_SOURCE=configured WORKER_SLACK_SINK=slack \
WORKER_TASK_AUTH=static \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8081

# terminal 2: the public webhook
SLACK_SIGNING_SECRET=<from the Slack app> \
SLACK_ALLOWED_TEAM_IDS=T0123456789 \
SLACK_ALLOWED_CHANNEL_IDS=C0123456789 \
WORKER_BASE_URL=http://127.0.0.1:8081 \
  uv run uvicorn support_agent_app.api.main:create_app --factory --port 8080

# terminal 3: expose only the webhook
ngrok http 8080
```

Then in the Slack app settings, set Event Subscriptions to
`https://<your-tunnel>/slack/events`. Slack immediately sends a
`url_verification` challenge, which the webhook answers, so the URL turns green.
Subscribe to the `app_mention` bot event and reinstall if prompted.

Now mention the bot in the channel. What happens:

1. Slack POSTs the event to your tunnel
2. the webhook verifies the signature, stores the request, queues it, answers 200
3. `LocalTaskQueue` POSTs the request ID to the worker on 8081
4. the worker claims it, runs the agent against Vertex, posts the reply in-thread

Both allowlists must match your real workspace and channel, or the webhook
answers 200 and deliberately creates no work. That is the failure to expect if
nothing happens: check `SLACK_ALLOWED_TEAM_IDS` and `SLACK_ALLOWED_CHANNEL_IDS`.

A free ngrok URL changes every restart, so the Slack Event Subscriptions URL has
to be re-saved each time.

### Things worth demonstrating

| What to show | How |
|---|---|
| A cited answer | the command above |
| The fixed human-review reply | restart the worker with `WORKER_FAKE_FIXTURE=sensitive` |
| A refused prompt injection | restart the worker with `WORKER_FAKE_FIXTURE=prompt-injection` |
| A forged request is rejected | add `--signing-secret wrong-secret`, and the webhook answers 401 with nothing stored |
| Another channel is ignored | add `--channel-id C-other`, and the webhook answers 200 but creates no work |
| A stale worker cannot reply twice | `uv run demo-state-machine` |

`WORKER_FAKE_FIXTURE` chooses which canned decision the fake model returns, so
the question you type does not change the answer in fixture mode. Swap to
`WORKER_MODEL_SOURCE=configured` with Google Cloud credentials to make the model
real, and `WORKER_SLACK_SINK=slack` with a bot token to make the reply real. They
are independent, so real model plus recorded reply is a supported combination.

### Notes

The webhook is `POST /slack/events`. It verifies the Slack signature over the raw
body, stores the request, hands the queue a request ID, and acknowledges. It
never calls a model, which is what keeps it inside Slack's three second window.

Google Cloud has no supported Cloud Tasks emulator and the course does not add a
third-party one, so `LocalTaskQueue` is the explicit local stand-in. Cloud Tasks
replaces that one class and nothing else. Tasks live in memory, so a restart
loses anything undelivered.

`TASK_QUEUE_BACKEND` chooses between them, and `api/main.py` is the only module
that names either class. `cloud-tasks` also needs `GOOGLE_CLOUD_PROJECT`,
`TASK_QUEUE_LOCATION`, and `TASK_OIDC_SERVICE_ACCOUNT`, and a `WORKER_BASE_URL`
pointing at the deployed worker; without them the process refuses to start. The
worker is private, so each task carries an OIDC token minted for the webhook's
service account.

The worker checks that token. `WORKER_TASK_AUTH` chooses how:

| Value | What the worker checks | Where it is used |
|---|---|---|
| `google-oidc` (default) | A Google-signed OIDC token in `Authorization`: signature, expiry, audience, issuer, and the service account email | Deployed |
| `static` | A shared string in `X-Worker-Task-Identity` | Local only |

`google-oidc` needs `WORKER_BASE_URL`, which is the audience Cloud Tasks put in
the token, and `TASK_OIDC_SERVICE_ACCOUNT`, which is the one identity allowed to
enqueue work. Without them the worker refuses to start. It is the default, so a
deployment cannot fall back to the shared string by forgetting to set anything;
a local run asks for `static` on purpose. Either way, a missing, forged, or
wrong-identity token is a 401 before the worker touches the request.

[docs/worker-authentication.md](docs/worker-authentication.md) shows how to run
the worker with the deployed check against a real Google-minted token, and what
each unauthorized call answers.

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

The image holds the application, its dependencies, and the operator files, and
nothing else. No `.env`, no credential, and no `support_agent_app/testing`: the
fixture adapters are deleted from the image, so a deployment cannot answer an
employee from a canned model even if `WORKER_MODEL_SOURCE=fixture` is set by
mistake. The demo commands are in the image and fail the same way, which is the
point.

`migrations/` and `policies/` are in the image at `/srv/migrations` and
`/srv/policies`, and no runtime reads either. They are there because
`apply-migrations` and `seed-policies` run from this same image as Cloud Run
jobs, and a job cannot apply a migration it does not carry. Both commands take
`--migrations-dir` and `--policies-dir`, so the job names the path rather than
relying on a relative resolution that inside the image lands in the virtual
environment.

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

The worker uses the real model and posts to Slack by default
(`WORKER_MODEL_SOURCE=configured`, `WORKER_SLACK_SINK=slack`). Without cloud
credentials in the container it will accept a request, claim it, and record
`model_configuration` as the failure, which is the correct loud answer rather
than a canned reply. Add `-e WORKER_SLACK_SINK=record` to keep the reply in
Postgres instead of sending it.

## Deploy to Cloud Run

Two services and two jobs, all from the image above:

```bash
SLACK_ALLOWED_TEAM_IDS=T... SLACK_ALLOWED_CHANNEL_IDS=C... \
  scripts/deploy-dev.sh

TAG=abc1234 scripts/deploy-dev.sh          # deploy a specific build
scripts/deploy-dev.sh --skip-migrations    # services only, schema unchanged
```

It applies the schema and seeds the policy set as two Cloud Run jobs **before**
either service exists, then deploys the private worker, grants the one identity
that may invoke it, and deploys the public webhook last. Each of the four runs
as its own service account and reads only the secrets that identity is allowed
to read. Nothing downloads a service-account key.

[docs/deploying-to-cloud-run.md](docs/deploying-to-cloud-run.md) explains the
order, the OIDC audience, and the one organization policy the script cannot
change for you, and holds the recorded proof of a task running from a signed
Slack event to a cited reply with nothing running locally.

## Run the examples

Install the Python dependencies:

```bash
uv sync
cp examples/.env.sample examples/.env
```

Run an example:

```bash
uv run python examples/lesson-02/01_basic_model_call.py
```

Examples are grouped by the lesson that uses them, so `examples/lesson-05/`
holds the four retrieval examples.

The model examples require the matching provider credentials.
The whole-document, vector, and hybrid RAG examples use the OpenAI API.
The SQL RAG example uses an in-memory SQLite database and needs no setup.

## Verify the repository

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
uv run python examples/lesson-05/02_sql_rag.py
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
config.toml          Safe application defaults loaded by Pydantic Settings
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
examples/            Small standalone examples, one folder per lesson
  demos/             Runnable demos of the application slices
slack/               Bootstrap and deployment-stage Slack app manifests
Dockerfile           One image, both runtimes, selected by the command
scripts/             Provision the cloud environment, build the image, deploy it
docs/                Application docs and the implementation contract
MEMORY.md            Sanitized, non-authoritative coordination log
tests/unit/          No network, no database, no model
tests/functional/    Real Postgres, stubbed agent
tests/evals/         Real model, skipped without credentials
```

The recovery and retention jobs, their schedules, and the operational checks are added by later linked implementation tasks.
