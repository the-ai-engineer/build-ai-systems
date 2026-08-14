# Build AI Systems

Public project repository for the Build AI Systems course.

The course builds and deploys a professional HR policy assistant that employees use through Slack.
The assistant answers from trusted company policies, refuses off-topic requests, and sends uncertain, unsupported, sensitive, or conflicting questions to a person.

The finished flow is concrete:

```text
Employee mentions the assistant in Slack
-> public webhook verifies and stores the request
-> webhook queues one internal request ID
-> separate worker claims the request
-> policy agent retrieves approved documents from Postgres
-> application verifies the supporting filenames and excerpts
-> assistant replies in the original thread
-> or mentions the configured HR support user group without a policy answer
```

## A realistic freelance AI project

This course simulates the kind of AI system an independent engineer or small consultancy could build for a business.
The goal is not to create a generic SaaS product or another chatbot demonstration.

Students receive a customer problem and take it through a complete professional delivery process:

1. Understand the business problem and agree how success will be measured.
2. Turn the customer brief into a technical architecture.
3. Make explicit product, security, authority, and reliability decisions.
4. Break the design into linked tasks with acceptance criteria.
5. Use coding agents to implement and review the system.
6. Integrate it with the customer's existing tools.
7. Test normal behaviour, safety boundaries, and failure cases.
8. Deploy it and demonstrate the business outcome.

The finished system is built for one company's workflow and requirements.
Another customer might use different policy sources, escalation systems, security controls, or communication tools.
This variation is normal in professional AI consulting work.
The reusable skill is knowing how to design, build, evaluate, and operate the complete system.

## Start here

Read the [customer brief](brief.md).

Then use the repository contracts:

- [Course outline](docs/course-outline.md)
- [Course code map](docs/course-code-map.md)
- [Finished application specification](docs/final-agent-spec.md)
- [Deployment prompt](docs/resources/deploy-with-codex-prompt.md)
- [Sanitized implementation memory](MEMORY.md)

The first course design exercise creates `ARCHITECTURE.md` from the brief before application code is introduced.
The finished application specification records the approved reference decisions that later implementation tasks must preserve.

## Course build

The project advances through four phases.

### 1. Design the system

Students turn the customer brief into `ARCHITECTURE.md`.
They make the important product and engineering decisions, define boundaries, identify failure cases, and decide how the system will be tested.

The reviewed architecture is then broken into small linked tasks with acceptance criteria.

### 2. Understand the AI boundaries

The Python examples introduce the mechanisms used by the finished system:

1. Basic model calls.
2. Structured scope decisions.
3. Calls, workflows, and agents.
4. A hand-built agent loop.
5. A framework agent with Pydantic AI.
6. Grounding answers in trusted documents.
7. Optional vector and hybrid retrieval.

Coding agents can write much of the implementation.
Students still need to understand what data reaches the model, what contract comes back, who authorises tool calls, and how to prove the result is correct.

### 3. Build the product local-first

Students first build the local policy agent and Postgres knowledge base.
They then build the worker as an HTTP handler that accepts only `request_id` and test it directly without a webhook.
Local asynchronous tests use a small explicit queue adapter and a separate worker process.
Google Cloud does not provide a supported Cloud Tasks emulator, so the course does not add a third-party emulator.

Next, students deploy the private worker to a development Cloud Run service and invoke it manually through the supported Cloud Run proxy or another authenticated request.
They add Cloud Tasks and prove that OIDC invokes the same handler.
Only then do they connect the public Slack webhook as the task producer.
Real Slack may reach a local webhook through a temporary HTTPS tunnel.

This early development deployment proves the seams independently.
The later production lesson adds the complete IAM, recovery, retention, observability, and load-hardening work.

The finished application uses Pydantic AI with its Google Cloud provider.
Its current tested default is configurable `google-cloud:gemini-3.5-flash`.
`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` select the project and location.
Local authenticated integration uses Application Default Credentials.
Cloud Run uses the worker runtime service identity and does not require a separate Gemini API key.
Deterministic fake-model tests remain the default local proof.

Gemini Flash is the primary model because model choice is an architecture and operating-cost decision.
The course teaches choosing the smallest model that passes the HR support evals, not choosing by prestige.
Cost analysis includes input tokens, retrieved context size, output tokens, tool and model turns, retries, latency, and escalation rate.
The application records usage and timing metadata without employee or policy text.
Evals use a dated price configuration to estimate cost per request and per resolved answer, so long-lived prose does not embed current price figures.

The product includes:

- Signed Slack events and fast acknowledgement.
- A configured Slack team allowlist.
- Durable asynchronous processing.
- Fenced worker claims.
- Trusted policy retrieval with verified evidence.
- Safe thread replies and fixed off-topic refusals.
- HR referral for unsupported, sensitive, or conflicting requests.
- Retry exhaustion recovery and duplicate-event handling.
- Retention of employee message text for no longer than the agreed period.

### 4. Deploy and prove it

Students deploy the working system to Google Cloud.
Production uses a public Cloud Run webhook, a private Cloud Run worker, Cloud Tasks, Cloud SQL Postgres, and scheduled Cloud Run Jobs for recovery and retention.

Students then add production evidence:

- Behavioural evals.
- Integration and failure tests.
- Logs, traces, latency, and cost evidence.
- A live end-to-end demonstration.

## What the customer is buying

The customer is not buying a language model, a RAG pipeline, or a Slack bot.
The customer is buying:

- Fewer repetitive questions reaching HR.
- Faster answers for employees.
- Consistent answers from approved policies.
- Safe escalation when human judgement is required.
- Evidence that the system is reliable and behaving correctly.
- A system that works with the tools the company already uses.

Models, queues, retrieval methods, and cloud services support those outcomes.
They are not the outcome themselves.

## Definition of done

The project is complete when:

- A real Slack event is accepted quickly from the configured workspace.
- The request is stored durably and processed asynchronously.
- The system answers, refuses, or refers the question correctly.
- Every policy answer names approved evidence.
- Sensitive and unsupported questions mention the agreed HR route without an automated policy answer.
- Retries and stale workers do not produce duplicate known replies.
- Failures and exhausted retries can be inspected and recovered.
- Expired employee message text and user IDs are removed.
- The complete system runs locally and in its deployed environment.
- Evaluation results show that it meets the agreed customer requirements.

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

The model examples require the matching provider API key.
The whole-document, vector, and hybrid RAG examples use the OpenAI API.
The SQL RAG example uses an in-memory SQLite database and needs no setup.

## Verify the repository

```bash
uv run python -m unittest discover -s tests
uv run python -m compileall -q examples tests
```

## Repository structure

```text
brief.md       Customer problem and product requirements
examples/      Small standalone AI engineering examples
  policies/    Sample data used only by retrieval examples
docs/          Course sequence, finished contract, and deployment prompt
MEMORY.md      Sanitized implementation and teaching log
tests/         Checks for examples and repository contracts
```

Application code, production policy sources, database migrations, deployment files, and operational checks are added by the linked implementation tasks.
