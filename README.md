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

See [docs/final-agent-spec.md](docs/final-agent-spec.md) for the complete implementation contract and [docs/course-code-map.md](docs/course-code-map.md) for the short lesson-to-code map.
Use [docs/slack-setup.md](docs/slack-setup.md) and the versioned manifests in `slack/` to configure the course Slack app without enabling event delivery before the webhook exists.

## Run the local policy agent

The first application slice runs with synthetic fixtures and a deterministic Pydantic AI model.
It needs no Slack, Google Cloud, database, model credentials, or network access.

```bash
uv run python -m unittest tests.test_support_workflow
uv run python -m support_agent_app.demo --fixture documented
uv run python -m support_agent_app.demo --fixture unsupported
uv run python -m support_agent_app.demo --fixture prompt-injection
```

See [docs/local-policy-agent.md](docs/local-policy-agent.md) for the optional Postgres and Google Cloud model paths.

## Run the local worker

The worker loads a synthetic request that is already stored in Postgres.
Its default model and Slack adapters are deterministic fakes, so it makes no Google Cloud or Slack call.

```bash
DATABASE_URL="postgresql://..." uv run python -m unittest tests.test_worker tests.test_slack_actions tests.test_worker_auth
DATABASE_URL="postgresql://..." uv run python -m support_agent_app.demo_worker --fixture documented
DATABASE_URL="postgresql://..." uv run python -m support_agent_app.demo_worker --fixture human-review
DATABASE_URL="postgresql://..." uv run python -m support_agent_app.demo_worker --fixture uncertain-send
DATABASE_URL="postgresql://..." uv run uvicorn support_agent_app.worker:app --port 8081
```

The local HTTP endpoint is `POST /tasks/process-support-request`.
Its JSON body contains only `request_id`, and local calls provide `X-Worker-Task-Identity: local-development-task`.
The identity check is an explicit local seam that a later task replaces with Google OIDC verification.

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
uv run python -m unittest discover -s tests
uv run python -m compileall -q examples support_agent_app tests
uv run python examples/06b_sql_rag.py
```

## Repository structure

```text
brief.md       Customer problem and first-release requirements
examples/      Small standalone AI engineering examples
  policies/    Sample data used only by retrieval examples
support_agent_app/  Local policy workflow, worker, and repository adapters
slack/         Bootstrap and deployment-stage Slack app manifests
docs/          Application docs, approved policy fixtures, and implementation contract
MEMORY.md      Sanitized, non-authoritative coordination log
tests/         Checks for examples and repository contracts
```

Slack ingress, queues, cloud deployment, and operational checks are added by later linked implementation tasks.
