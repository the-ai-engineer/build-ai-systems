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
- Unsupported, sensitive, or conflicting questions produce human review with no automated answer and a fixed reply asking the employee to contact HR.
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

### 2026-08-14: Issue #19 Postgres request lifecycle

- Store each accepted Slack event once by a database unique constraint on `slack_event_id`.
- Keep the request state machine explicit: `accepted` to `queued` to `processing`, then `completed`, `failed`, or `reconciliation`.
- Mark complete question text for expiry 30 days after acceptance and return only the internal request ID and creation flag from acceptance.
- Record each successful claim as a historical row with a unique token, increasing lease version, expiry, business attempt number, and release time.
- Count business attempts only when a worker obtains a claim and insert the matching attempt row in the claim transaction.
- Limit workflow claims to five business attempts and make the next claim return `permanent-failure` without incrementing the count.
- Persist safe agent-run metadata, selected document IDs and revisions, and the typed decision in one fenced transaction.
- Record retrieved context tokens with an injectable counter and use a visible UTF-8 byte estimate divided by four for the local provider-independent path.
- Persist exact outbound text and its SHA-256 hash together when the reply action is created.
- Permit only one non-cancelled reply action per request and only one known successful reply in database constraints.
- Replace a known failed reply only through a fenced transaction that cancels it and creates the next action generation with identical text and hash.
- Keep uncertain sends non-cancelled in `reconciliation`; they are never converted into an automatic retry.

Transaction boundaries are:

- Acceptance inserts or finds one request in one transaction.
- Claiming locks the request row, checks terminal state and the latest lease, inserts the new claim and attempt, and moves the request to `processing` in one transaction.
- Agent run, source revisions, and decision are written together after validating the current fence.
- Reply action text and hash are created together after validating the current fence.
- Sending, known failure, uncertain outcome, and known success each validate the current fence before changing state.
- Known success updates the action, attempt, claim release, and request terminal state in one transaction.
- Safe retry replacement cancels the known failed action and inserts the next pending generation in one transaction.

The fencing rule is that every worker-owned mutation locks the request row and compares the newest claim token and lease version.
The claim must be unreleased, unexpired, and attached to a request in `processing`.
After a newer lease version exists, an older worker cannot write a result, create or start an action, record failure or uncertainty, or complete the request.

Alternatives rejected:

- Process-local locks were rejected because they do not survive process failure or coordinate Cloud Run instances.
- A status-only claim was rejected because an expired worker could still write after another worker restarted the request.
- Updating without a request-row lock was rejected because concurrent deliveries could both observe claimable work.
- Rebuilding outbound text during retry was rejected because reconciliation requires the exact planned content and hash.
- Treating an uncertain send as retryable was rejected because the first Slack call may have succeeded.
- Keeping a retryable known-failed action as the active action was rejected after review proved that the next claim could not start it.

### 2026-08-15: Human-review Slack fallback

- Keep `human_review` as the typed internal outcome and keep it structurally unable to carry an automated answer or sources.
- For every non-off-topic human-review result, reply exactly: “I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team.”
- Do not tag a Slack user or user group in the fallback.
- Version 1 has no support-group setting and no paid Slack user-group dependency.

### 2026-08-15: Issue #21 local stored-request worker

- Keep FastAPI parsing, task authentication, orchestration, policy workflow, durable state, and Slack delivery as separate teachable boundaries.
- The HTTP body contains only the internal `request_id`.
- The local identity header is a replaceable test seam and is not presented as production Google OIDC verification.
- Use the deterministic fake model and fake Slack client by default.
- Keep configured Gemini and real Slack Web API adapters available behind the same injected interfaces.
- Format supported replies from validated decisions with a visible `Sources` section and readable policy filenames.
- Format non-off-topic human review with the fixed V1 fallback and no user or group mention.
- Resume a persisted verified decision without another model call after a lease expires.
- Retry a known failed send from the exact stored text and hash without another model call.
- Move an old pending or sending action to `reconciliation` instead of automatically sending it from a newer claim.
- Leave enough deadline budget to record the Slack result after the network call.
- Treat any ambiguous send or unrecorded send result as reconciliation.

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

### 2026-08-14: Issue #19 Postgres request lifecycle

- Started from the latest merged `origin/main` at commit `5f9c5a9` and read issue #19, repository rules, and the final application contract before editing.
- Added an ordered SQL migration, migration runner, small Postgres request repository, focused integration tests, and a local stale-worker demo.
- Kept Slack calls, Cloud Tasks, model execution, deployment, recovery scheduling, and other external calls outside this task.
- The first proof run found no lifecycle failures.
- Expanding `INV-7` proof to uniqueness across action generations exposed and fixed a conflict-query parameter mistake.
- The first independent review reproduced a real `AC-5` failure: a new claim could not retry a reply after a known failed send because the old failed action remained active and owned by the old claim.
- The retry path now has an explicit fenced transaction that cancels the known-failed action and creates the next generation with the same exact text and hash.
- The review also identified the required coordination log as missing while review was still in progress.
  This entry supplies the state machine, transaction boundaries, fencing rule, rejected alternatives, review finding, and current proof.
- Stale-claim coverage now includes result writes, action creation, action start, known action failure, uncertain action outcome, workflow failure, and completion.
- The second independent review found that `retrieved_context_tokens` always used the database default of zero.
  The workflow record now carries a non-negative retrieved-context count, the repository writes it explicitly, and the integration test proves a nonzero value is preserved.
- The local workflow uses a documented provider-independent estimate and accepts an injected counter so a provider-aware implementation can supply its own measurement without changing the durable repository contract.
- The stale-claim regression now also covers the known-failed reply replacement transaction.
- A final fresh independent review inspected the complete corrected diff and returned `Approve` with no findings.

### 2026-08-15: Issue #21 local stored-request worker

- Started from the pinned merged default branch at commit `44adec3`.
- Read issue #21, issues #18 and #19, their merged implementations, repository rules, and the approved final application contract before editing.
- Added a private FastAPI handler, deadline-aware orchestration, task-authentication seam, fake and configured Slack adapters, three local demos, and focused tests.
- The synthetic claim sequence is claim, load durable input, run or resume the agent decision, persist the exact action, mark sending, call the injected Slack adapter, then finalize under the same fence.
- Supported formatting includes `Sources` and verified filenames while full excerpts remain in Postgres.
- Human review uses the exact fixed fallback with no mention syntax.
- A five-second synthetic deadline proves the worker records retryable state before starting the model or send.
- A timeout after the fake send begins records one attempt, marks the action uncertain, and moves the request to reconciliation.
- An expired claim with a recorded decision resumes without another model run.
- An expired claim with a pending action enters reconciliation without a model or Slack call.
- A clear temporary Slack failure retries the identical persisted reply under a newer action generation without another model call.
- The application code adds no message, answer, excerpt, payload, or credential logging.
- The first fresh review reproduced a transient database failure before Slack that left a pending action and then entered reconciliation on retry despite zero send attempts.
- The worker now records both `pending` and `sending` states as a known unsent failure when `mark_action_sending` fails before the Slack adapter is called.
- The regression proves the first call remains retryable, Slack receives zero attempts, and the next claim sends the exact stored reply without another model call.
- The next fresh review reproduced Slack starting after a database step consumed its send budget and a connect timeout entering reconciliation even though no request reached Slack.
- Worker-owned Postgres connections now receive the remaining budget as connection and statement timeouts.
- The complete Pydantic AI run is bounded by the remaining worker budget, including its model turns and deadline-aware Postgres policy tools.
- The worker recomputes the Slack timeout after the database send transition and records a known unsent failure if no send budget remains.
- Slack connect and pool timeouts are clear retryable failures; read and write timeouts remain uncertain and enter reconciliation.
- The third fresh review found that invalid typed model output and configuration errors were still classified as temporary.
- Invalid typed output, usage-limit violations, non-retryable provider responses, and configuration errors now fail permanently with safe categories.
- Provider, database, concurrency, and deadline failures remain retryable, including provider `408`, `409`, `429`, and `5xx` responses.
- The invalid-output regression proves one business attempt, no Slack call, terminal failure, and no second model run on duplicate delivery.
- The fourth fresh review reproduced a non-ASCII identity causing `compare_digest` to raise and return `500`.
- Task identities are now compared as UTF-8 bytes, so arbitrary invalid header text receives `401` without reaching the processor.

## Manual Setup

### 2026-08-14: Issue #16

No Slack app, Google Cloud resource, secret, OAuth grant, tunnel, or database was created for this documentation task.
Later tasks must document manual setup with sanitized resource names and placeholders only.
Temporary tunnel URLs, service URLs, workspace identifiers, and credentials must not be recorded here.

### 2026-08-14: Issue #18 initial proof

No Slack app, Google Cloud resource, Cloud Task, Cloud Run service, database, model credential, or external message was created or requested.
Optional Postgres and authenticated Google Cloud commands use environment configuration supplied outside the repository.
No live model or database integration was run for the default deterministic proof.

### 2026-08-14: Issue #19 local Postgres proof

- Used a temporary local PostgreSQL 15 database with no repository credential or external service.
- Created no Slack app, Cloud Task, Cloud Run service, model invocation, deployment, scheduler, or outbound network call.
- Database connection details remained in the local environment and were not written to the repository.

### 2026-08-15: Issue #21 local worker proof

- Used one temporary local PostgreSQL 15 database containing only synthetic policy and request fixtures.
- Started the FastAPI worker on loopback, called it with valid and invalid local identities, then stopped it.
- Made no Google Cloud, real Slack, Cloud Tasks, deployment, release, or credential call.
- Database connection details and synthetic UUIDs were not recorded in the repository.

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

### 2026-08-14: Issue #19 proof after review fixes

- `DATABASE_URL="postgresql://..." uv run python -m unittest tests.test_support_repository tests.test_worker_claims tests.test_outbound_actions` passed 14 focused PostgreSQL tests.
- `DATABASE_URL="postgresql://..." uv run python -m support_agent_app.demo_state_machine` printed worker A at lease version 1, worker B at lease version 2, and an explicit stale-worker rejection before worker B created one pending action.
- `DATABASE_URL="postgresql://..." uv run python -m unittest discover -s tests` passed 48 tests.
- `uv run python -m compileall -q examples support_agent_app tests` passed.
- `uv run python examples/06b_sql_rag.py` passed and returned the expected local annual-leave result.
- Ruff check and format checks passed for all new Python files.
- `git diff --check` passed.
- The credential-pattern audit passed.
- The focused tests prove duplicate event acceptance, 30-day question expiry, auditable timestamps, safe run metadata and source revisions, atomic claims, active-lease rejection, increasing expired-lease reclaim, complete stale-worker fencing, five-attempt exhaustion, exact outbound text and hash, action uniqueness, known failure retry, uncertain-send reconciliation, duplicate completion, and every explicit lifecycle outcome.
- The repository integration proof stores a nonzero retrieved-context token value instead of relying on a database default.
- A final fresh independent review returned `Approve` with no Must, Should, or Could findings.

### 2026-08-15: Issue #21 initial local proof

- `DATABASE_URL="postgresql://..." uv run python -m unittest tests.test_worker tests.test_slack_actions tests.test_worker_auth` passed 27 focused tests against PostgreSQL 15.
- The documented demo printed one completed fake thread reply with `Sources` and `annual-leave-policy.md`.
- The human-review demo printed the exact fixed HR fallback with one fake send and no mention.
- The uncertain-send demo printed `reconciliation` and exactly one send attempt.
- A live loopback Uvicorn check returned `200 duplicate-complete` for the valid local identity and `401` for an invalid identity.
- `DATABASE_URL="postgresql://..." uv run python -m unittest discover -s tests` passed 81 tests.
- `uv run python -m compileall -q examples support_agent_app tests` passed.
- `uv run python examples/06b_sql_rag.py` passed and returned the expected local annual-leave result.
- Ruff check, changed-file format check, and `git diff --check` passed.

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

### 2026-08-15: Keep the worker sequence visible

- Teach FastAPI as parsing and status mapping only.
- Teach authentication as an injected boundary before any claim or model work.
- Teach the worker service as explicit orchestration over small repository, model, and Slack interfaces.
- Inspect the fake Slack attempt in demos instead of logging production content.
- Show that the action text and hash exist before the fake network call.
- Show that known failures can reuse exact stored text, while uncertain sends cannot be retried automatically.

## Unresolved Questions

- Confirm the 30-day retention period before using the system with real employee data.
- Decide whether a later version should re-read an edited or deleted Slack message before replying.
- Decide whether human review should also post to a private HR channel after the first version.

## Issue #17 Slack app setup

### Decisions

- The signed-in Gradientwork Slack app-management page showed one unrelated existing app and safe team ID `T0B2CKH25KK`.
- Its non-secret manifest had extra history and assistant scopes, direct-message events, interactivity, and Socket Mode, so it was not a matching course app and was left unchanged.
- The course app is named `HR Policy Assistant` and uses only `app_mentions:read` and `chat:write` bot scopes.
- Direct messages, the App Home Messages tab, incoming webhooks, interactive components, shortcuts, slash commands, Socket Mode, organization deployment, MCP, and multi-workspace distribution remain disabled.
- Slack currently rejects a manifest with bot events unless it also has a request URL or Socket Mode.
- The bootstrap manifest therefore creates the minimal app without event delivery.
- The deployment-stage manifest adds only `app_mention` and uses a non-routable placeholder that must be replaced locally after the HTTPS webhook exists.

### Current UI path and manual checkpoints

- The checked creation path is **Your Apps → Create New App → From a manifest → Continue**.
- The current manifest screen places the JSON or YAML editor above a **Workspace** selector, then proceeds to a review step.
- Inspect and compare existing apps before selecting **Create and Install**.
- Stop immediately before the final **Create and Install** action unless the user has just confirmed that workspace change.
- Stop whenever Slack shows an OAuth consent or workspace installation approval screen.
- The user must approve installation themselves after confirming that only the two course bot scopes are requested.
- The operator enters local Slack credentials directly into the gitignored `support_agent_app/.env` file without exposing their values to an agent.
- Deployed Slack credentials belong in Secret Manager.
- Event delivery stays disabled until a deployed HTTPS `/slack/events` endpoint passes Slack's URL-verification challenge.
- The app ID, team ID, bot user ID, and dedicated channel ID are safe to record.
- Credential values, messages, payloads, and request URLs are not recorded.
- The installed course app has safe app ID `A0BQF2X29MF` in team `T0B2CKH25KK`.
- Slack's current web profile did not expose **Copy member ID** for the bot; after the operator stores the bot credential locally, call `auth.test` from a process that prints only `user_id`.
- Do not treat the app's direct-message channel ID as the bot user ID.
- Human-review replies need no Slack user-group setup or identifier.

### Teaching notes

- A manifest is useful evidence of requested capabilities, but installed OAuth grants can remain broader until the app is reinstalled.
- Separating the bootstrap manifest from the deployment-stage manifest makes the missing public webhook visible instead of hiding it behind Socket Mode.
- The Slack app list is the first duplicate-prevention checkpoint.
- Installation approval and secure credential entry remain operator actions, even when a browser agent performs the surrounding setup.

### Initial proof

- Verified the current signed-in Slack app list and manifest-creation path in Chrome on 14 August 2026.
- Confirmed the unrelated existing app and left it unchanged.
- Slack accepted the bootstrap manifest through its review step and showed exactly `app_mentions:read` and `chat:write`, with zero event responses.
- The first browser pass stopped at **Create and Install** for action-time confirmation, before any app or credential was created.
- After confirmation, Slack created `HR Policy Assistant`; the user approved the separate OAuth screen and completed installation.
- The installed settings show exactly `app_mentions:read` and `chat:write`, with no user scopes.
- App Home messages, interactivity, slash commands, Events API delivery, Socket Mode, and public distribution are off.
- The application settings pages were inspected without reading or exposing any credential field.
- `uv run python -m unittest tests.test_slack_setup` passed 3 focused manifest tests.
- `uv run python -m unittest discover -s tests` passed 51 tests with 14 expected database skips.
- `uv run python -m compileall -q examples tests` passed.
- `uv run python examples/06b_sql_rag.py` passed and returned the expected local annual-leave result.
- Ruff check and format checks passed for the focused test file.
- `git check-ignore support_agent_app/.env`, `git diff --check`, and the credential-pattern audit passed.
- Added focused manifest contract tests and the repository setup guide.
- No Slack credential, OAuth code, customer message, complete event payload, group membership, or deployed request URL was recorded.
- A fresh final independent review found no actionable findings and returned `Approve`.
