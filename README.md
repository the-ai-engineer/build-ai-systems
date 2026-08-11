# Build AI Systems

Public project repository for the Build AI Systems course.

The course builds and deploys a professional HR policy assistant that employees use through Slack.
The assistant answers from trusted company policies, refuses off-topic requests, and sends uncertain or sensitive questions to a person.

## A realistic freelance AI project

This course simulates the kind of AI system an independent engineer or small consultancy could build for a business.
The goal is not to create a generic SaaS product or another chatbot demonstration.

Students receive a customer problem and take it through a complete professional delivery process:

1. Understand the business problem and agree how success will be measured.
2. Turn the customer brief into a technical architecture.
3. Make explicit product, security, authority, and reliability decisions.
4. Break the design into tasks with acceptance criteria.
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

The proposed instructor design lives in
[`docs/system-design/index.html`](docs/system-design/index.html) on the reference
branch. Review it before turning the build phases into implementation tickets.

The repository intentionally does not contain `ARCHITECTURE.md` yet.
The first course design exercise creates it from the customer brief.

The starting repository contains small Python examples for the core AI concepts.
It does not contain a finished application, deployment, database schema, or Slack integration.
Students design and build those parts during the course.

## Course build

The project advances through four phases.

### 1. Design the system

Students turn the customer brief into `ARCHITECTURE.md`.
They make the important product and engineering decisions, define boundaries, identify failure cases, and decide how the system will be tested.

The reviewed architecture is then broken into small tasks and tickets with acceptance criteria.

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

### 3. Build the product

Students use coding agents to implement the reviewed tickets.
They set up the Slack application and build:

- Signed Slack events and fast acknowledgement.
- Durable asynchronous processing.
- Trusted policy retrieval.
- Safe thread replies.
- Fixed off-topic refusals.
- Human referral for unsupported or sensitive requests.
- Retries and duplicate-event handling.

Students run the complete system locally before deploying it.
Local testing proves the Slack event, background worker, retrieval, and reply path as one system.

### 4. Deploy and prove it

Students deploy the working system to Google Cloud.
They then add production evidence:

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

- A real Slack event is accepted quickly.
- The request is stored durably and processed asynchronously.
- The system answers, refuses, or refers the question correctly.
- Every policy answer is supported by approved evidence.
- Sensitive and unsupported questions are sent to the agreed human route.
- Retries do not produce duplicate replies.
- Failures can be inspected and recovered.
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
The Postgres retrieval examples also require a local Postgres database with `pgvector`.

## Verify the starting repository

```bash
uv run python -m unittest discover -s tests
uv run python -m compileall -q examples tests
```

## Repository structure

```text
brief.md       Customer problem and product requirements
examples/      Small standalone AI engineering examples
  policies/    Sample data used only by the retrieval examples
tests/         Checks for the teaching examples and clean starting state
```

`ARCHITECTURE.md`, application code, production policy sources, database migrations, deployment files, and operational checks are outputs of the course.
