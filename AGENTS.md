# AGENTS.md

This repository is the public project for the Build AI Systems course.

When writing or changing Python code, follow `PYTHON_STANDARDS.md`.
Read `ARCHITECTURE.md` before changing structure, ownership, or dependencies.

The code is designed for lessons, recordings, and student exercises.
Prefer clarity over cleverness.
Examples should be easy to read on screen and easy to run locally.

## Repository boundary

Canonical written lessons, diagrams, scripts, and teaching material live in `/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/`.
This repository owns runnable code, tests, policies, deployment configuration, and `docs/final-agent-spec.md` as the implementation contract.
`MEMORY.md` is a sanitized coordination log, not a source of truth.
Do not duplicate paid lesson prose in this public repository.
`ai-engineer-curriculum` is not part of the active Build AI Systems workflow and must not be modified for this project.

## Course direction

The course builds a professional HR policy assistant in Python.

An employee mentions the assistant in a dedicated Slack channel.
The system accepts the event quickly, processes it asynchronously, retrieves approved company policies, and replies in the Slack thread.
It refuses off-topic requests and gives uncertain, unsupported, sensitive, or conflicting requests a fixed reply that asks the employee to contact HR.

The public Cloud Run webhook verifies and stores the request, then creates a Cloud Task containing only the internal request ID.
The private Cloud Run worker claims the request with a fenced lease, runs the policy workflow, and records one controlled Slack action.
Postgres is the durable source of truth.

The customer problem and product requirements live in `brief.md`.
`docs/final-agent-spec.md` is the approved reference contract for the finished application and implementation tasks.
Students still create and review their own architecture document during the first design lesson before application code is introduced.
The repository's `ARCHITECTURE.md` is the reference they compare against afterwards.

Do not add application structure or infrastructure before the relevant linked task defines it.

## Teaching direction

- Use Python.
- Use configurable `google-cloud:gemini-3.5-flash` as the finished application's current tested default model.
- Use Pydantic AI's Google Cloud provider with Application Default Credentials.
- Supply the Google Cloud project and location through environment configuration.
- Cloud Run must use its runtime service identity and must not require a separate Gemini API key.
- Early standalone examples may retain their existing providers when provider mechanics are the lesson.
- Teach model selection as an architecture and operating-cost decision.
- Choose the smallest model that passes the support evals, not the model with the most prestige.
- Record usage metadata without recording employee questions, answers, or policy text.
- Introduce Pydantic AI after the hand-built agent lesson.
- Show provider boundaries without pretending provider capabilities are identical.
- Keep structured outputs, tool calls, and agent loops tied to real product decisions.
- Keep advanced vector and hybrid retrieval optional.
- Use Google Cloud as the deployment target.
- Keep the complete system runnable locally before cloud deployment.

Teach the application local-first.
Start with the design and linked tasks, then build the local policy agent, Postgres knowledge base, and worker HTTP handler that accepts only `request_id`.
Test that handler directly before adding a webhook.
Deploy the same private worker to a development Cloud Run service, invoke it through the supported Cloud Run proxy or another authenticated request, then add Cloud Tasks with OIDC.
Connect the public Slack webhook only after the worker and queue work independently.
A temporary HTTPS tunnel may expose a local webhook to real Slack.
Google Cloud does not provide a supported Cloud Tasks emulator, so do not introduce a third-party emulator.
Keep this early development deployment separate from the later production hardening lesson.
This sequence does not change the production architecture.

Coding agents may write much of the implementation.
Students must still understand the contracts, authority boundaries, failure behaviour, and evidence required to approve that work.

## Code style

- Keep lesson examples runnable from the command line.
- Prefer simple interfaces over framework magic.
- Do not introduce cloud dependencies into early lessons.
- Do not use em dashes in prose.
- Keep Markdown sentences on separate physical lines when files get long.
- Deliver complete changes without placeholders or fake TODOs.

## Repository structure

- `PYTHON_STANDARDS.md` is the coding and project structure standard.
- `ARCHITECTURE.md` describes the system that exists today.
- `brief.md` defines the customer problem and first-release scope.
- `app/support_agent_app/` is the deployable application, split by component ownership.
- `migrations/` holds the single SQL migration history.
- `examples/` contains standalone teaching examples for the AI foundations.
- `examples/demos/` contains runnable demos of the application slices.
- `policies/` is the single approved policy set, used by the application and the retrieval examples.
- `docs/course-code-map.md` contains only lesson names and their runnable or planned code.
- `docs/final-agent-spec.md` defines the finished application contract.
- `docs/resources/deploy-with-codex-prompt.md` contains the supervised deployment prompt.
- `MEMORY.md` is the sanitized, non-authoritative coordination log.
- `tests/` verifies the examples and repository contracts.

The examples must not import the future deployable application.
They should stay small even as the main project grows.

## Privacy

Never record Slack tokens, signing secrets, OAuth values, database credentials, complete employee messages, complete Slack event payloads, or policy excerpts in the repository, GitHub, logs, or `MEMORY.md`.

## Verification

Run this before reporting repository changes:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
```

Unit tests need no database. Integration tests skip unless `DATABASE_URL` is set.
`uv run pyright` is configured but not yet clean; see the exceptions in `ARCHITECTURE.md`.

Run a changed model example with the required provider credentials.

Run the retrieval examples that do not need an API key:

```bash
uv run python examples/06b_sql_rag.py
```

Run the whole-document, vector, and hybrid examples with `OPENAI_API_KEY` set.
