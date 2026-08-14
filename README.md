# Build AI Systems

Public code repository for the Build AI Systems course.

The project builds a professional HR policy assistant in Python.
An employee mentions it in a dedicated Slack channel, the system processes the request asynchronously, retrieves approved policies from Postgres, and replies in the Slack thread.
It refuses off-topic requests and refers uncertain, unsupported, sensitive, or conflicting requests to the configured HR support user group.

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
uv run python -m compileall -q examples tests
uv run python examples/06b_sql_rag.py
```

## Repository structure

```text
brief.md       Customer problem and first-release requirements
examples/      Small standalone AI engineering examples
  policies/    Sample data used only by retrieval examples
docs/          Short code map, implementation contract, and deployment guidance
MEMORY.md      Sanitized, non-authoritative coordination log
tests/         Checks for examples and repository contracts
```

Application code, production policies, database migrations, deployment files, and operational checks are added by linked implementation tasks.
