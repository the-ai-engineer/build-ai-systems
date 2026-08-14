# Deploy With Codex Prompt

Use this prompt after the Slack support application and its deployment scripts exist.
Read `docs/final-agent-spec.md` before using it.
Complete the documented local webhook, queue-adapter, separate-worker, and real Slack checks before replacing the local adapters with Google Cloud services.

The goal is to use Codex as an implementation partner while the engineer supervises architecture, IAM, privacy, and verification.

```text
You are helping me deploy the asynchronous Slack support agent in this repository to Google Cloud.

Goal:
Deploy the public Slack webhook, private Cloud Tasks worker, Postgres database, recovery job, and retention job.
Verify one synthetic Slack mention from acceptance through one cited thread reply or human-review notification.

Repository:
<repository URL>

Canonical architecture:
- Slack Events API sends signed app_mention callbacks.
- A public Cloud Run webhook verifies the signature, timestamp, event type, bot identity, and configured team allowlist.
- The webhook stores one support request in Cloud SQL Postgres.
- The webhook creates a named Cloud Task containing only request_id.
- Cloud Tasks invokes a private Cloud Run worker with OIDC.
- The worker obtains a fenced Postgres claim before running Pydantic AI.
- Pydantic AI uses its Google Cloud provider with configurable google-cloud:gemini-3.5-flash as the current tested default.
- GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION supply the model project and location.
- The worker runtime service identity invokes Gemini without a separate API key.
- Model selection uses the smallest model that passes the HR support evals.
- Run metadata records model ID, tokens, duration, finish reason, and tool-call count without employee or policy text.
- The agent loads no more than three trusted policy documents from Postgres.
- A supported answer has verified policy filenames and excerpts.
- Application code records one outbound action and replies in the original Slack thread.
- Human review contains no automated policy answer and mentions the configured HR support user group.
- Cloud Scheduler starts finite recovery and retention Cloud Run Jobs from the same application image.
- Secret Manager stores Slack and database credentials.

Constraints:
- Do not use destructive commands.
- Explain each cloud resource before creating it.
- Prefer least-privilege IAM and separate webhook, worker, task, and maintenance identities.
- Never ask me to paste Slack tokens, Slack signing secrets, OAuth values, model keys, or database credentials into chat.
- Do not create or request a Gemini API key.
- Never print, log, copy, or record secret values.
- When a secret value must be entered, give a command or console path that lets me enter it directly into Secret Manager without exposing it to you.
- Use placeholders in commands and reports.
- Do not put complete Slack messages, answers, policy excerpts, or event payloads in logs or reports.
- Make deployment reproducible with scripts or documented commands.
- Verify each major step before continuing.
- Stop for billing, project, region, IAM, or other material decisions that require my approval.

Tasks:
1. Inspect the repository and identify the application roles, container build, configuration, migrations, and existing deployment scripts.
2. Run the documented local tests and demos before provisioning cloud resources.
3. Confirm gcloud authentication, then ask which Google Cloud project and region to use.
4. Enable only the required Google Cloud APIs.
5. Create or confirm separate service accounts for the webhook, Cloud Tasks caller, worker, scheduler, and maintenance runtime.
6. Grant the worker runtime identity only the minimum Google Cloud role needed to invoke the configured Gemini model.
7. Configure the model string, GOOGLE_CLOUD_PROJECT, and GOOGLE_CLOUD_LOCATION without adding an API-key secret.
8. Create Secret Manager containers for the remaining secrets and give secure manual entry instructions without requesting or reading their values.
9. Create or connect Cloud SQL Postgres, apply migrations, and ingest the synthetic policy documents.
10. Build one application image and record its immutable digest.
11. Deploy the private worker with no public access and invoke it manually through the supported Cloud Run proxy or another authenticated request.
12. Grant only the expected Cloud Tasks caller identity, then verify missing, swapped, and correct worker identities.
13. Create the Cloud Tasks queue with five attempts, exponential backoff, ten concurrent tasks, and five dispatches per second.
14. Prove that Cloud Tasks OIDC invokes the same request_id worker handler.
15. Deploy the public webhook with only database and task-creation permissions, then verify its health endpoint.
16. Deploy the finite recovery and retention Cloud Run Jobs from the same image.
17. Schedule recovery every five minutes and retention once per day with the maintenance identity.
18. Verify that the maintenance identity cannot invoke the worker and that the task identity cannot start maintenance jobs.
19. Give the manual Slack configuration steps for the deployed event URL, app_mention subscription, bot scopes, one allowed team, one allowed channel, and HR support user group without reading credential values.
20. Run a synthetic signed webhook check without including complete message text in command output.
21. Complete one real mention smoke test in the dedicated course workspace.
22. Record only sanitized identifiers, state transitions, timings, source filenames, and final status as evidence.
23. Test duplicate delivery, stale-worker fencing, safe retries, retry exhaustion recovery, uncertain-send reconciliation, retention, and ten-request concurrency.
24. Create a dated model-price configuration from the current authoritative provider documentation without adding price figures to long-lived architecture prose.
25. Report estimated model cost per request and per resolved answer, including the effect of retries and escalations.
26. Check logs, traces, metrics, queue state, failed requests, reconciliation records, expired content counts, model usage, and estimated cost.
27. Produce a short deployment report with resource names, URLs, image digest, secret container names, verification evidence, and remaining manual steps.
28. Do not include any secret value or complete employee message in the report.

Output:
Work step by step.
Run checks.
Stop when a required decision or secure manual secret-entry step needs the operator.
```

Codex can help execute commands, but the engineer remains responsible for the design, credentials, IAM, verification, and operating decisions.
