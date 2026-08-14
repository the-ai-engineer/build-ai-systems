# Course Outline

## Course Project

Build AI Systems follows one professional delivery project from customer brief to production evidence.
The customer needs an HR policy assistant that employees use in a dedicated Slack channel.

An employee mentions the assistant with a general policy question.
The system accepts the event quickly, processes it asynchronously, retrieves active company policies, and replies in the Slack thread.
Off-topic requests receive a fixed refusal.
Unsupported, sensitive, personal, or conflicting requests are referred to the configured HR support user group without an automated policy answer.

## What the Course Teaches

The course is about system boundaries and engineering judgment, not one model or framework.
Students learn to:

- turn a customer brief into a reviewed architecture
- split the design into linked tasks with acceptance criteria
- expose model calls behind small typed boundaries
- distinguish deterministic workflows from agent loops
- retrieve and verify approved evidence
- separate fast ingress from slow AI work
- persist business state independently from queue delivery
- fence stale workers and reconcile uncertain external actions
- test locally before introducing managed services
- deploy and prove the complete business outcome

Python keeps the code readable.
Pydantic AI becomes the application framework after students build one agent loop by hand.
Google Cloud is the production target.

The finished application's current tested default model is configurable `google-cloud:gemini-3.5-flash` through Pydantic AI's Google Cloud provider.
The project and location come from `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
Local authenticated runs use Application Default Credentials.
Cloud Run uses the worker runtime service identity and does not need a separate Gemini API key.
Deterministic fake-model tests remain required and do not depend on cloud credentials.

## Finished Production Flow

```text
Employee mentions the assistant in Slack
-> public Cloud Run webhook verifies signature, age, team, channel, and event
-> webhook stores one support request in Postgres
-> webhook creates one named Cloud Task containing request_id
-> private Cloud Run worker authenticates the task and claims the request
-> policy agent loads approved documents from Postgres
-> application validates the source filenames, revisions, and excerpts
-> application records one outbound Slack action
-> assistant posts one answer or HR referral in the original thread
-> scheduled jobs recover stranded work and expire sensitive fields
```

The webhook never calls the model or retrieves policies.
Cloud Tasks delivers work, but Postgres owns the durable business state.
The model never sends Slack messages or changes application state directly.

## Local-First Development Sequence

The production architecture is introduced through independently testable seams.

```text
customer brief and approved design
-> linked implementation tasks
-> local policy agent and Postgres knowledge base
-> worker HTTP handler accepting only request_id
-> direct local worker calls without a webhook
-> local queue adapter and separate worker process
-> private development Cloud Run worker
-> authenticated manual invocation through the Cloud Run proxy
-> Cloud Tasks invoking the same worker with OIDC
-> public Slack webhook as the task producer
-> real Slack through a temporary HTTPS tunnel when useful
-> production hardening and deployment proof
```

Google Cloud does not provide a supported Cloud Tasks emulator.
The local course path uses an explicit queue adapter and never introduces a third-party emulator.

The private development Cloud Run worker is an early teaching deployment.
It proves the HTTP and identity boundary before the public webhook exists.
The later production lesson adds final IAM, recovery, retention, observability, concurrency proof, and operational checks.

## Lessons

| # | Lesson | Main idea | Code or artifact |
|---|---|---|---|
| 00 | Customer brief and architecture | Define the business outcome, authority boundaries, failure cases, acceptance criteria, and linked tasks | `brief.md`, student-created `ARCHITECTURE.md` |
| 01 | Basic model calls | Treat the model as a component behind a small boundary | `examples/01_basic_model_call.py` |
| 02 | Structured outputs | Return a typed HR scope decision | `examples/02_structured_outputs.py` |
| 03 | Calls, workflows, and agents | Compare one call, deterministic orchestration, and an agent | `examples/03_deterministic_workflow.py` |
| 04 | Agent by hand | Build a minimal tool-calling loop | `examples/04_agent_by_hand.py` |
| 05 | First framework agent | Move the same idea into Pydantic AI and show provider boundaries before the finished app adopts Gemini on Google Cloud | `examples/05_first_framework_agent.py` |
| 06 | Whole-document and SQL retrieval | Read approved files and retrieve exact structured facts | `examples/06a_file_rag.py`, `examples/06b_sql_rag.py` |
| 07 | Optional vector and hybrid retrieval | Compare semantic and fused rankings without making them mandatory | `examples/07a_vector_rag.py`, `examples/07b_hybrid_rag.py` |
| 08 | Local policy application | Build the Postgres knowledge base, constrained agent, verified citations, request state, and fenced claims | Future application modules |
| 09 | Worker boundary and development deployment | Test the `request_id` HTTP handler locally, then deploy and invoke the private development Cloud Run worker | Future worker module and development service |
| 10 | Queue and Slack ingress | Add Cloud Tasks with OIDC, then connect the signed Slack webhook as the task producer | Future adapters and Slack setup |
| 11 | Reliability and evaluation | Add one outbound action, reconciliation, recovery, retention, evals, tracing, and concurrency proof | Future integration and evaluation suite |
| 12 | Production hardening | Apply least-privilege IAM, production configuration, monitoring, runbooks, and end-to-end proof | `docs/resources/deploy-with-codex-prompt.md` |

## Retrieval Progression

Retrieval is not automatically vector search.

The course compares:

- whole-document tools for a small visible policy set
- SQL retrieval for exact structured facts
- vector similarity for semantic search
- hybrid ranking for mixed keyword and semantic needs

The finished application uses constrained Postgres policy tools.
The agent can list the active policy index and load at most three complete documents.
It cannot issue arbitrary SQL.

A supported answer must name each source file and preserve a supporting excerpt that application code verifies against the exact loaded revision.
Missing evidence or conflicting policies leads to HR referral.

## Worker and Queue Progression

The worker exists before the queue.
Its HTTP contract accepts only an internal `request_id` and loads the employee question, Slack identifiers, policies, and state from Postgres.

Students first call this handler directly.
They then deploy it privately to a development Cloud Run service and invoke it through `gcloud run services proxy` or another authenticated request.
Cloud Tasks is added only after that service boundary works.
The task uses OIDC and calls the same handler with the same minimal payload.

The public Slack webhook is connected last as the producer.
This order lets worker failures, queue failures, and Slack ingress failures be diagnosed independently.

## Finished-App Model Boundary

Pydantic AI owns the framework boundary.
The application model setting defaults to `google-cloud:gemini-3.5-flash` and remains configurable.
The Google Cloud project and location are environment configuration, not hard-coded values.

Local deterministic tests inject a fake model.
An authenticated local integration run uses Application Default Credentials.
The Cloud Run worker uses its runtime service identity, with the minimum model-invocation role, instead of a separate Gemini API key.

Gemini Flash is primary because model selection affects architecture and operating cost.
Students choose the smallest model that passes the HR support evals rather than choosing by prestige.
They compare input tokens, retrieved context size, output tokens, tool and model turns, retries, latency, and escalation rate.

The application records model ID, input and output token counts, duration, finish reason, and tool-call count without employee or policy text.
Evals apply a dated price configuration and report estimated cost per request and per resolved answer.
Long-lived course prose does not contain current price figures.

## Guardrails and Human Referral

The agent answers only general HR questions supported by active approved policies.
It cannot access employee records, calculate entitlements, approve requests, or make employment decisions.

Off-topic input receives a deterministic refusal.
Sensitive, personal, unsupported, ambiguous, or conflicting input produces `human_review`.
Application code posts a fixed thread message that mentions the configured HR support user group and contains no automated policy answer.

## Testing and Evals

Synthetic fixtures cover supported, off-topic, sensitive, unsupported, and conflicting questions.
Production Slack messages are never copied into fixtures.

Automated proof covers:

- Slack signature, timestamp, team, channel, and event validation
- deterministic task names and duplicate event handling
- the `request_id`-only worker contract
- current claim tokens and increasing lease versions
- policy tool and model-turn limits
- exact source filename, revision, and excerpt validation
- fixed refusal and human-review behavior
- one known successful outbound action
- uncertain-send reconciliation
- business-attempt exhaustion and recovery
- task-generation exhaustion before application code obtains a claim
- 30-day sensitive-field expiry
- identity separation and ten-request concurrency
- log and task-payload redaction

Human review checks whether an answer is clear, appropriately scoped, and useful to an employee.
The eval target is the whole business workflow, not the model in isolation.

## Teaching Principle

Build each boundary in isolation before connecting the end-to-end path.
Keep the mechanism visible, then swap adapters without changing the core contract.
