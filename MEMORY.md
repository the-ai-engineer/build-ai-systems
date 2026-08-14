# Course Build Memory

This file is the sanitized coordination log for the Build AI Systems course application.
Every implementation task must append its decisions, steps, commands, proof, manual setup, and teaching notes.
This file is not a source of truth.

Slack tokens, signing secrets, OAuth values, database credentials, complete customer or employee messages, complete Slack event payloads, policy excerpts, and other secrets must never be recorded here.
Use placeholders for identifiers and describe test inputs without copying employee content.

## Decisions

### 2026-08-14: Repository boundary

- Canonical written lessons, diagrams, scripts, and teaching material live in `/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/`.
- This public repository owns runnable code, tests, policies, deployment configuration, and `docs/final-agent-spec.md` as the implementation contract.
- `MEMORY.md` remains a sanitized coordination log and is not authoritative.
- Do not duplicate paid lesson prose in this repository.
- `ai-engineer-curriculum` is not part of the active Build AI Systems workflow and must not be modified for this project.

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

### 2026-08-14: Issue #18 local policy workflow

- Keep one explicit workflow instead of adding a registry, graph framework, or Slack abstraction.
- Use typed domain input without Slack fields and a discriminated typed result for `answer` or `human_review`.
- Give the Pydantic AI agent only `list_support_documents()` and `get_support_document(document_id)`.
- Limit one run to three loaded documents, six model requests, five single tool calls, a 20-second model timeout, and 500 output tokens per model response.
- Configure `google-cloud:gemini-3.5-flash` by default and construct the Google Cloud provider explicitly from project and location configuration so authenticated runs use Application Default Credentials.
- Use a deterministic Pydantic AI `FunctionModel` and file repository for the default proof path.
- Keep the same workflow replaceable with the active Postgres repository and live Google Cloud model adapters.
- Verify document ID, title, filename, revision, active state, and exact excerpt occurrence in application code before accepting an answer.
- Convert invalid citation evidence to `human_review` with no automated answer.
- Store a dated price input outside long-lived prose and estimate request cost from recorded input and output tokens.
- Record the actual injected model ID and reject an explicit label that does not match it.
- Record model location and service tier, use separate dated global and non-global rates, and force live Google Cloud requests to standard on-demand routing.
- Reject answers and excerpts that contain only whitespace before deterministic evidence checks.
- Strip and reject whitespace-only decision reasons so every human-review result remains inspectable.
- Mark both retrieval tools as sequential execution barriers so parallel model tool calls cannot bypass the three-document limit.

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
- Removed the detailed course outline and reduced the course code map and README to implementation-facing information.
- Recorded the boundary between the private lesson source and this public code repository without modifying any other repository.

### 2026-08-14: Issue #18 local policy workflow

- Fetched the latest merged default branch and created `codex/issue-18-policy-agent` from commit `140ec61`.
- Read issue #18, the customer brief, final agent specification, canonical private Slip design, repository rules, and existing coordination memory before editing.
- Added the local typed workflow, constrained retrieval tools, policy repository adapters, deterministic model fixtures, evidence validation, safe run metadata, dated cost input, CLI, synthetic policies, SQL schema, and focused tests.
- Preserved the standalone examples and kept Slack, Cloud Tasks, Cloud Run, request state, worker leases, and outbound actions out of this slice.
- The public browser fetch for the private canonical design returned a not-found response, so the same file was read through the authenticated GitHub API without copying private lesson prose into this repository.
- The first CLI proof exposed an `unknown` finish reason because the workflow inspected the final output-tool acknowledgement.
  The workflow now selects the last model response and records its finish reason.
- The provider review found that a bare provider string could allow an unrelated Google API key to take precedence.
  Live runs now construct the Google Cloud provider explicitly from project and location configuration to select Application Default Credentials.
- The first independent review reproduced an injected-model identity mismatch, regional cost misclassification, and acceptance of a whitespace-only answer.
  The workflow now derives and validates model identity, records location and tier for price selection, and rejects blank answers.
- The second independent review reproduced a newline-only citation that matched Markdown and found that the default Google Cloud routing could use provisioned capacity while metadata claimed standard pricing.
  Citation validation now requires visible excerpt text in both schema and application checks, and live model settings force on-demand routing.
- Each review cycle required current proof to be appended to this log before publication.
- The next independent review reproduced acceptance of a whitespace-only human-review reason.
  Model-facing and final decision schemas now strip and reject blank reasons.
- A later independent review reproduced four concurrent document loads passing the shared three-document check.
  Both retrieval tools now run sequentially, and a real agent-loop regression proves that the fourth simultaneous request is rejected after three loads.

## Manual Setup

### 2026-08-14: Issue #16

No Slack app, Google Cloud resource, secret, OAuth grant, tunnel, or database was created for this documentation task.
Later tasks must document manual setup with sanitized resource names and placeholders only.
Temporary tunnel URLs, service URLs, workspace identifiers, and credentials must not be recorded here.

### 2026-08-14: Issue #18 initial proof

No Slack app, Google Cloud resource, Cloud Task, Cloud Run service, database, model credential, or external message was created or requested.
Optional Postgres and authenticated Google Cloud commands use environment configuration supplied outside the repository.
No live model or database integration was run for the default deterministic proof.

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
- The repository-boundary update passed 16 unit tests, byte-compilation, the local SQL RAG run, stale-channel audit, example-preservation check, and `git diff --check`.

### 2026-08-14: Issue #18

- `uv run python -m unittest tests.test_support_workflow` passed 13 focused tests.
- `uv run python -m support_agent_app.demo --fixture documented` returned a grounded answer with verified document identity, filename, revision, and excerpt.
- `uv run python -m support_agent_app.demo --fixture unsupported` returned `human_review` without an automated answer.
- `uv run python -m support_agent_app.demo --fixture prompt-injection` returned `human_review` without an automated answer.
- `uv run python -m unittest discover -s tests` passed 29 tests.
- `uv run python -m compileall -q examples support_agent_app tests` passed.
- `uv run python examples/06b_sql_rag.py` passed and preserved the standalone SQL lesson.
- `git diff --check` passed.
- The credential-pattern audit passed.
- Model-backed and Postgres integration paths were not run because the requested deterministic proof needs no credentials or external services.

### 2026-08-14: Issue #18 final local proof

- `uv run python -m unittest tests.test_support_workflow` passed 18 focused tests after the independent review fixes.
- All three exact issue fixture commands passed after the review fixes.
- `uv run python -m unittest discover -s tests` passed 34 tests.
- `uv run python -m compileall -q examples support_agent_app tests` passed.
- `uv run python examples/06b_sql_rag.py` passed.
- `git diff --check` and the credential-pattern audit passed.
- The focused regressions cover model identity mismatch, global and non-global pricing, blank answers, blank excerpts, blank human-review reasons, forced Google Cloud on-demand routing, and concurrent document-limit enforcement.
- Live Google Cloud ADC invocation and real Postgres execution remain intentionally unverified because this proof does not use external credentials or services.
- After two time-boxed review attempts were interrupted, a bounded fresh reviewer returned `Approve` with no Must or Should findings from its completed inspection.

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

### 2026-08-14: Keep code and lesson content separate

- Keep this repository focused on runnable application code and its implementation contract.
- Keep the public lesson-to-code map to lesson names and code locations only.
- Develop detailed lesson prose, diagrams, and scripts in the canonical private lesson source instead of copying them here.

### 2026-08-14: Make evidence and capability boundaries visible

- Keep the model fixture inside Pydantic AI so tests exercise the real agent loop, tool dispatch, typed output, usage limits, and run accounting.
- Show the document index and full-document lookup as the only model capabilities.
- Keep the active-document rule in the repository and enforce the loaded-document limit again in the workflow.
- Treat a model citation as a proposal until deterministic application code verifies every identity and excerpt field.
- Keep `human_review` structurally unable to carry an answer or sources.
- Record document IDs and revisions for audit while excluding the complete question, answer, and policy content from run metadata.
- Use the exact fixture CLI before adding Postgres, a live model, worker state, Slack, or cloud infrastructure.

## Unresolved Questions

- Confirm the 30-day retention period before using the system with real employee data.
- Decide whether a later version should re-read an edited or deleted Slack message before replying.
- Decide whether human review should also post to a private HR channel after the first version.
