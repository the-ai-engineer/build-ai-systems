# Course Code Map

This repository has two kinds of code.

The current `examples/` files are small standalone programs for AI foundations.
The deployable HR policy assistant is added through later linked tasks without making the examples import application code.

## Current Coverage

The customer problem lives in `brief.md`.
Examples 01 through 07 are runnable now.
The production contract lives in `docs/final-agent-spec.md`.
Application code, migrations, and deployment resources are future task outputs.

## Lesson Map

| Lesson | Current or planned shape | Outcome |
|---|---|---|
| Customer brief and design | `brief.md`, student-created `ARCHITECTURE.md` | Turn business needs into approved boundaries, invariants, acceptance criteria, and linked tasks |
| Basic model call | `examples/01_basic_model_call.py` | Call a model through a small boundary |
| Structured output | `examples/02_structured_outputs.py` | Return a typed HR scope decision |
| Workflow and agent comparison | `examples/03_deterministic_workflow.py` | Compare deterministic code with agent decisions |
| Agent by hand | `examples/04_agent_by_hand.py` | Expose the tool-calling loop |
| Pydantic AI agent | `examples/05_first_framework_agent.py` | Keep tools stable while changing direct providers |
| Whole-document RAG | `examples/06a_file_rag.py`, `examples/policies/` | List and read a small visible policy set |
| SQL RAG | `examples/06b_sql_rag.py` | Retrieve exact policy facts from local SQLite |
| Optional vector RAG | `examples/07a_vector_rag.py` | Rank policies by embedding similarity |
| Optional hybrid RAG | `examples/07b_hybrid_rag.py` | Fuse keyword and vector rankings |
| Local policy application | Future application modules and Postgres migrations | Produce verified decisions, durable requests, and fenced claims |
| Worker boundary | Future private HTTP handler | Process only `request_id` and load durable state from Postgres |
| Development deployment | Future private Cloud Run service | Invoke the worker manually through the supported Cloud Run proxy or an authenticated request |
| Queue adapter | Future Cloud Tasks adapter | Prove OIDC invokes the same worker before Slack is connected |
| Slack ingress | Future public webhook and Slack setup | Verify events, create requests, and produce named tasks |
| Reliability and evals | Future integration suite and scheduled jobs | Prove one action, reconciliation, recovery, retention, privacy, and concurrency |
| Production hardening | Deployment resources and runbooks | Apply least privilege, monitoring, scaling, and end-to-end proof |

## Local-First Application Thread

```text
design and linked tasks
-> local policy agent and Postgres knowledge base
-> worker HTTP handler accepting request_id
-> direct local calls without a webhook
-> explicit local queue adapter and separate worker process
-> private development Cloud Run service
-> authenticated manual worker call
-> Cloud Tasks delivery with OIDC
-> public Slack webhook as producer
-> production hardening
```

The worker, queue, and Slack ingress are tested independently in that order.
Real Slack may reach a local webhook through a temporary HTTPS tunnel after the worker and queue paths work.

Google Cloud does not provide a supported Cloud Tasks emulator.
Do not add a third-party emulator.
The local queue adapter is a teaching and development seam, not a production architecture change.

## Application Boundaries

The future application uses explicit adapters for:

- Postgres policy and request repositories
- local queue delivery
- Cloud Tasks delivery
- Slack verification and replies
- model execution
- time and identity checks used by tests

The core workflow owns policy decisions and state transitions.
Adapters own network and storage mechanics.
The model owns neither durable state nor Slack actions.

## Finished-App Model Contract

The finished application uses Pydantic AI's Google Cloud provider.
Its current tested default model is configurable `google-cloud:gemini-3.5-flash`.
`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` supply the project and location.

Local deterministic tests use a fake model and require no cloud credentials.
Authenticated local integration uses Application Default Credentials.
The Cloud Run worker uses its runtime service identity and does not use a separate Gemini API key.

Gemini Flash is the primary choice because model selection is an architecture and operating-cost decision.
The selection rule is the smallest model that passes the HR support evals, not model prestige.

Application run records include model ID, input and output tokens, duration, finish reason, and tool-call count without employee or policy text.
Cost evals also consider retrieved context size, model and tool turns, retries, latency, and escalation rate.
They use a dated price configuration to report estimated cost per request and per resolved answer without putting current price figures in long-lived prose.

## Production Roles

One Python codebase and image serve four production roles:

- public Cloud Run webhook service
- private Cloud Run worker service
- scheduled recovery Cloud Run Job
- scheduled retention Cloud Run Job

Cloud Tasks calls the worker with OIDC and a body containing only `request_id`.
Postgres remains authoritative for requests, claims, decisions, and outbound actions.

## Evidence Thread

Every supported answer records:

- policy document ID
- readable source filename
- exact document revision or content hash
- verified supporting excerpt

Every human-review result records a reason and contains no generated policy answer.
Application code mentions the configured HR support user group in the original Slack thread.

## Example Isolation Rule

Files in `examples/` stay runnable and readable on their own.
They do not import the future application package.
Small duplicated teaching helpers are preferable to pulling production abstractions into the early lessons.
