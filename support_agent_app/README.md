# Support Agent App

This directory contains the integrated application used in the later AI Architect lessons.

The standalone files in `examples/` teach one idea at a time.
This application combines those ideas into one system that can be tested, deployed, and operated.

## Target System

```text
Gmail support inbox
-> Gmail push notification through Pub/Sub
-> authenticated Cloud Run webhook
-> ticket stored in Postgres
-> Pydantic AI support agent
-> support document retrieved from Postgres
-> grounded reply drafted and checked
-> Gmail reply with AI Answered label
-> or Human Needed label for human review
```

The finished application should also record structured logs, traces, model usage, and eval results.

## Current State

The current code is the lesson 06B application baseline that later lessons build on.
The vector and hybrid retrieval examples for lesson 07 remain standalone teaching samples.

It currently provides:

- a FastAPI service with `/health` and `/support-email` endpoints
- a signed Slack Events API endpoint with a minimal mention and direct-message echo bot
- support policy loading from markdown or Postgres
- a Pydantic AI agent definition with direct OpenAI and Anthropic providers
- a deterministic local draft and reply check
- a policy ingestion command
- a Cloud Run-compatible Dockerfile

It does not yet provide:

- a connection between the FastAPI workflow and the Pydantic AI agent
- Gmail OAuth, message fetching, replies, or labels
- a Pub/Sub push-message handler
- ticket persistence or duplicate-event protection
- production guardrails and evals
- deployment scripts, migrations, or observability configuration

Do not enable automatic customer replies until those parts are implemented and tested.

## Layout

```text
support_agent_app/
  api.py                 FastAPI entrypoint
  config.py              environment configuration
  main.py                local command-line entrypoint
  ingest_policies.py     policy ingestion command
  agents/                Pydantic AI agent definitions
  services/              application and domain logic
  integrations/          Postgres, Gmail, and cloud boundaries
```

The finished application specification is in [`docs/final-agent-spec.md`](../docs/final-agent-spec.md).
The lesson mapping is in [`docs/course-code-map.md`](../docs/course-code-map.md).

## Local Setup

Run commands from the repository root.

```bash
uv sync --extra app
```

Without a local `.env` file, the app uses policy markdown from `docs/policies`.
This is the simplest way to run the current local skeleton.

```bash
uv run python -m support_agent_app.main
uv run --extra app uvicorn support_agent_app.api:app --reload --port 8080
```

Check the service:

```bash
curl http://localhost:8080/health

curl http://localhost:8080/support-email \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{
    "sender": "customer@example.com",
    "subject": "Return question",
    "body": "Can I return an opened item?"
  }'
```

## Minimal Slack Bot

The first Slack milestone is deliberately small:

```text
Slack mention or direct message
-> POST /slack/events
-> verify Slack's request signature
-> echo the message in the same thread
-> acknowledge the event
```

Create a Slack app at `api.slack.com/apps`.
Copy its signing secret from **Basic Information** into `support_agent_app/.env`:

```dotenv
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=
```

Run the FastAPI app, then expose port `8080` through an HTTPS tunnel for local development.
Under **Event Subscriptions**, turn on events and set Slack's Request URL to:

```text
https://your-public-url.example/slack/events
```

Slack sends a signed URL-verification request before accepting the endpoint.
After Slack verifies it, subscribe to these bot events:

- `app_mention`
- `message.im`

Add these bot token scopes under **OAuth & Permissions**:

- `app_mentions:read`
- `chat:write`
- `im:history`

Under **App Home**, turn on the Messages tab and allow users to send messages to the app.
Then select **Install App**, install it to your workspace, and copy the generated **Bot User OAuth Token**.
Reinstall the app whenever you change its OAuth scopes.

Add the token to `support_agent_app/.env`, then restart the local app:

```dotenv
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...
```

To test a channel mention, invite the bot to the channel with `/invite @YourBotName`, then mention it.
To test a direct message, open the bot from Slack's Apps section and send it a message.

This minimal version posts the echo before returning `200`, with a two-second Slack API timeout.
That keeps the work inside the Cloud Run request lifecycle and avoids losing an in-process background task after the response.
It is only suitable for the first milestone.
The next production step is to store or enqueue each accepted event before returning, then run retrieval and model calls in a private worker.

For a Cloud Run smoke test, build and deploy the dedicated Slack image:

```bash
uv run --extra app uvicorn support_agent_app.api:slack_app --host 0.0.0.0 --port "${PORT:-8080}"

docker build -f Dockerfile.slack -t YOUR_IMAGE_URL .
docker push YOUR_IMAGE_URL

gcloud secrets create slack-signing-secret --data-file=/secure/path/slack-signing-secret.txt
gcloud secrets create slack-bot-token --data-file=/secure/path/slack-bot-token.txt

gcloud secrets add-iam-policy-binding slack-signing-secret \
  --member serviceAccount:SLACK_SERVICE_ACCOUNT \
  --role roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding slack-bot-token \
  --member serviceAccount:SLACK_SERVICE_ACCOUNT \
  --role roles/secretmanager.secretAccessor

gcloud run deploy ai-system-slack-ingress \
  --image YOUR_IMAGE_URL \
  --allow-unauthenticated \
  --service-account SLACK_SERVICE_ACCOUNT \
  --set-secrets SLACK_SIGNING_SECRET=slack-signing-secret:latest,SLACK_BOT_TOKEN=slack-bot-token:latest
```

Allow unauthenticated invocation of that service because Slack cannot provide Google IAM credentials.
The route authenticates Slack using its request signature.
Use an existing dedicated runtime service account in place of `SLACK_SERVICE_ACCOUNT`.
If either secret already exists, add a new version instead of running `gcloud secrets create` again.
Do not expose the combined `support_agent_app.api:app` publicly in production because it also contains the local `/support-email` teaching endpoint.

## Postgres Policies

Create the local database and schema:

```bash
createdb ai_architect
psql -d ai_architect -f sql/001_support_document_registry.sql
```

Skip `createdb` when the database already exists.

Create the app environment file and set its database connection:

```bash
cp support_agent_app/.env.sample support_agent_app/.env
```

Preview and ingest the support policies:

```bash
uv run python -m support_agent_app.ingest_policies --dry-run
uv run python -m support_agent_app.ingest_policies
```

Set `DATABASE_URL` in `support_agent_app/.env` before running the real ingestion command.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `AI_ARCHITECT_MODEL` | Pydantic AI provider and model | `openai:gpt-5.6` |
| `OPENAI_API_KEY` | OpenAI model access | none |
| `ANTHROPIC_API_KEY` | Anthropic model access | none |
| `DATABASE_URL` | Postgres connection string | markdown fallback |
| `POLICY_DIR` | support policy directory | `docs/policies` |
| `SLACK_SIGNING_SECRET` | verifies inbound Slack requests | none |
| `SLACK_BOT_TOKEN` | posts messages through Slack's Web API | none |

Use one model provider at a time.
Changing the model setting does not make provider-specific tools and behaviour identical, so run the same evals after a provider change.

## Verification

```bash
uv run python -m unittest discover -s tests
uv run python -m compileall -q support_agent_app tests
uv run python -m support_agent_app.ingest_policies --dry-run
uv run python -m support_agent_app.main
```

## Production Path On Google Cloud

Use one Google Cloud project for the course deployment.
Keep the first production version small and complete before adding optional infrastructure.

1. Connect the API workflow to the Pydantic AI agent and return a typed processing result.
2. Add deterministic escalation rules and eval cases before allowing any reply to be sent.
3. Add Postgres tables for tickets, messages, processing attempts, and Gmail history state.
4. Add Gmail authorization, message fetching, reply sending, and label application.
5. Add a Pub/Sub endpoint that decodes Gmail notifications and processes events idempotently.
6. Keep `.dockerignore` current, run the container as a non-root user, and keep secrets out of image layers.
7. Store model and Gmail credentials in Secret Manager.
8. Create Cloud SQL Postgres, apply migrations, and ingest the support policies.
9. Deploy a public Slack ingress service that verifies every Slack signature, plus a separate private worker service that only Pub/Sub can invoke.
10. Renew the Gmail mailbox watch daily with Cloud Scheduler.
11. Add structured logs, traces, error reporting, budgets, and alerts.
12. Run an end-to-end test email and confirm the ticket, retrieval, decision, reply or escalation, labels, and logs.

The first deployment milestone should accept a simulated support email on Cloud Run and complete the safe agent workflow against Cloud SQL.
Add Gmail and Pub/Sub after that path is reliable.
