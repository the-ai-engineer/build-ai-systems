# AI Architect v2

Public code companion for the AI Architect course.

The course teaches how to build production-style AI systems by building one running project: an AI customer support agent.

The final demo is simple and concrete:

```text
Send an email to a support inbox
-> create a support ticket
-> look up the right support document
-> generate an answer with OpenAI
-> reply by email or escalate to a human
-> inspect logs, traces, evals, and deployment state
```

The course starts with small Python examples.
Then it moves into Pydantic AI, RAG, Gmail, Google Cloud, evals, tracing, and deployment.

## Start Here

Read the finished application spec:

- [docs/course-outline.md](docs/course-outline.md)
- [docs/ai-system-architecture-patterns/design.md](docs/ai-system-architecture-patterns/design.md)
- [docs/final-agent-spec.md](docs/final-agent-spec.md)
- [docs/course-code-map.md](docs/course-code-map.md)
- [docs/resources/deploy-with-codex-prompt.md](docs/resources/deploy-with-codex-prompt.md)

Run the first examples:

```bash
uv sync
cp examples/.env.sample examples/.env
uv run python examples/01_basic_model_call.py
uv run python examples/02_structured_outputs.py
uv run python examples/03_deterministic_workflow.py
uv run python examples/04_agent_by_hand.py
uv run python examples/05_first_framework_agent.py
uv run python examples/06a_file_rag.py
uv run python examples/06b_sql_rag.py
```

Load the sample support policies:

```bash
cp support_agent_app/.env.sample support_agent_app/.env
uv run python -m support_agent_app.ingest_policies --dry-run
createdb ai_architect || true
psql -d ai_architect -f sql/001_support_document_registry.sql
uv run python -m support_agent_app.ingest_policies
```

Run the Postgres retrieval examples:

These require Postgres with pgvector and an OpenAI API key.

```bash
uv run python examples/07a_vector_rag.py
uv run python examples/07b_hybrid_rag.py
```

Run the deployable app locally:

```bash
uv sync --extra app
uv run --extra app uvicorn support_agent_app.api:app --reload --port 8080
```

The app also includes the first Slack integration milestone.
See the [minimal Slack bot setup](support_agent_app/README.md#minimal-slack-bot) to connect Slack to the FastAPI `/slack/events` webhook.

Build the Cloud Run container:

```bash
docker build -t ai-architect-support-agent .
docker build -f Dockerfile.slack -t ai-architect-slack-bot .
```

Run tests:

```bash
uv run python -m unittest discover -s tests
```

## Teaching Stack

- Python for the examples.
- `uv` for package management and running commands.
- The ideas translate to other languages.
- OpenAI `gpt-5.6` as the default model provider.
- Pydantic AI for the agent framework once students understand the agent loop.
- OpenAI by default, with Anthropic shown as a direct provider switch.
- Gmail and Pub/Sub for asynchronous email ingestion.
- Cloud Run for deployment.
- Cloud SQL Postgres for state and support documents.
- pgvector for the vector search and hybrid search lessons.
- Cloud Logging, Cloud Trace, and Cloud Monitoring for observability.

## Repo Structure

- `examples/`: small runnable standalone lesson examples.
- [`support_agent_app/`](support_agent_app/README.md): integrated application for the later lessons.
- `support_agent_app/api.py`: FastAPI HTTP surface for Cloud Run.
- `support_agent_app/services/`: document registry, Gmail labels, and policy ingestion.
- `support_agent_app/agents/`: Pydantic AI agent definitions.
- `support_agent_app/integrations/`: external system boundaries.
- `docs/policies/`: editable support policy documents.
- `docs/resources/`: reusable course prompts and support material.
- `sql/`: Postgres schema.

## Repo Status

This repo is being built lesson by lesson.
Lessons 01 to 07 are runnable now.
Lessons 08 to 12 describe the target production shape and will fill in Gmail, Pub/Sub, guardrails, evals, observability, and deployment code as the course moves forward.
