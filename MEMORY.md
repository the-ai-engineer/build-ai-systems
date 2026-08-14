# Course Build Memory

This file is the sanitized coordination log for the Build AI Systems course application.
Every implementation task must append its decisions, steps, commands, proof, manual setup, and teaching notes.

Slack tokens, signing secrets, OAuth values, database credentials, complete customer or employee messages, complete Slack event payloads, policy excerpts, and other secrets must never be recorded here.
Use placeholders for identifiers and describe test inputs without copying employee content.

## Decisions

### 2026-08-14: Canonical application contract

- Slack is the only canonical employee channel for the finished HR policy assistant.
- Google Cloud is the production deployment target.
- The public Cloud Run webhook verifies Slack requests, stores accepted work, and creates a named Cloud Task.
- The private Cloud Run worker exposes an HTTP handler that accepts only `request_id`.
- Scheduled Cloud Run Jobs recover stranded work and remove retained sensitive content.
- Postgres is authoritative for policies, support requests, fenced claims, decisions, and outbound actions.
- Worker ownership uses an increasing lease version and unique claim token so stale workers cannot update state or send replies.
- The five-attempt business limit counts both started workflow claims and task generations that exhaust before application code obtains a claim.
- Supported answers name the policy source file and include an excerpt verified against the loaded document.
- Unsupported, sensitive, or conflicting questions produce human review and mention the configured Slack HR support user group.
- The standalone examples through `examples/07b_hybrid_rag.py` remain independent teaching programs.

### 2026-08-14: Local-first development and deployment seam

- Design the system and split it into linked tasks before implementation.
- Build the local policy agent and Postgres knowledge base first.
- Test the worker HTTP handler locally with stored `request_id` values before adding a webhook.
- Deploy that same handler to a private development Cloud Run service as an early development deployment.
- Invoke the development worker manually through the supported `gcloud run services proxy` flow or another authenticated request.
- Add Cloud Tasks next and prove that OIDC invokes the same private worker handler.
- Connect the public Slack webhook only after the worker and queue boundaries work independently.
- A temporary HTTPS tunnel may expose the local webhook to real Slack when useful.
- Google Cloud does not provide a supported Cloud Tasks emulator, so the course does not add a third-party emulator.
- The later production hardening lesson adds final IAM, recovery, retention, observability, load proof, and operational checks.
- This teaching sequence does not change the approved production architecture.

### 2026-08-14: Finished-app model provider

- Slack remains the application interface.
- The finished application uses Pydantic AI's Google Cloud provider.
- The current tested default is configurable `google-cloud:gemini-3.5-flash`.
- `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` supply the project and location.
- Local authenticated integration uses Application Default Credentials.
- Cloud Run uses the worker runtime service identity and does not require a separate Gemini API key.
- Local deterministic fake-model tests remain required and are the default proof path.
- Gemini Flash is primary because model selection is an architecture and operating-cost decision.
- Choose the smallest model that passes the HR support evals, not a model based on prestige.
- Cost drivers are input tokens, retrieved context size, output tokens, tool and model turns, retries, latency, and escalation rate.
- Record model ID, input tokens, output tokens, duration, finish reason, and tool-call count without recording employee or policy text.
- Evals estimate cost per request and per resolved answer from a dated price configuration.
- Do not place current model price figures in long-lived course prose.

## Implementation Log

### 2026-08-14: Issue #16 course contract migration

- Read issue #16, the approved asynchronous Slack support design, the customer brief, and repository instructions before editing.
- Fetched the latest default branch and preserved its HR policy assistant direction and simplified standalone examples.
- Preserved the intentional deletion of the old deployable support application, e-commerce policies, SQL schema, and stale container entrypoint.
- Added the required course outline, course map, final application specification, deployment prompt, and root coordination log.
- Rewrote AGENTS.md, the README, and tests so Slack is the canonical application channel without introducing application code.
- Recorded the local-first worker, development Cloud Run, Cloud Tasks, and Slack ingress sequence without changing production architecture.
- Replaced the finished-app provider contract with Gemini through Google Cloud and retained existing standalone examples unchanged.
- Independent review tightened stale `sending` recovery, the five-attempt business limit, local-first lesson ordering, and one non-cancelled reply action per `request_id`.

## Manual Setup

### 2026-08-14: Issue #16

No Slack app, Google Cloud resource, secret, OAuth grant, tunnel, or database was created for this documentation task.
Later tasks must document manual setup with sanitized resource names and placeholders only.
Temporary tunnel URLs, service URLs, workspace identifiers, and credentials must not be recorded here.

## Commands and Checks

### 2026-08-14: Issue #16

- `uv run python -m unittest discover -s tests` passed 15 tests.
- `uv run python -m compileall -q examples tests` passed.
- `uv run python examples/06b_sql_rag.py` passed and retrieved the annual-leave carry-over fact from local SQLite.
- The required stale-channel audit found no Gmail, Pub/Sub, or support-email application references in the audited contract files.
- `git diff --check` passed.
- `git diff --quiet origin/main -- examples` passed, confirming the standalone examples were preserved.
- Model-backed examples were not run because this documentation task changed no example code and had no provider credentials.
- No live Slack, Cloud Tasks, Cloud Run, Gemini, or Postgres integration was exercised because issue #16 changes the repository contract only.
- A fresh independent review returned `Approve` with no remaining findings after the documented fixes.

## Teaching Notes

### 2026-08-14: Independent boundaries before the end-to-end path

- Teach the worker first as an HTTP boundary that receives only `request_id` and loads durable state itself.
- Invoke the worker directly before adding any Slack webhook so retrieval, claims, decisions, and actions can be debugged independently.
- Use the private development Cloud Run deployment to introduce authenticated service calls before introducing a queue.
- Add Cloud Tasks as a delivery adapter and prove OIDC against the same worker handler.
- Add Slack ingress last as the task producer so webhook authentication and acknowledgement do not hide worker or queue bugs.
- Keep the model behind dependency injection so deterministic fake-model tests do not need Google Cloud access.
- Introduce Application Default Credentials only for the authenticated integration lesson.
- Teach the Cloud Run runtime service identity as the production Gemini credential boundary.
- Compare models with the support evals and operating evidence instead of model reputation.
- Keep dated price configuration separate from the long-lived architecture contract.
- Keep the local queue adapter small and explicit for local asynchronous tests.
- Treat the early development deployment as a teaching checkpoint, not the production hardening lesson.
- Keep queue delivery, durable business state, and Slack display state separate.
- Show why retries need fenced claims and why uncertain external sends require reconciliation instead of blind resend.
- Show grounding as evidence verification: a supported answer carries a policy file and an exact supporting excerpt.

## Unresolved Questions

- Confirm the 30-day retention period before using the system with real employee data.
- Decide whether a later version should re-read an edited or deleted Slack message before replying.
- Decide whether human review should also post to a private HR channel after the first version.
