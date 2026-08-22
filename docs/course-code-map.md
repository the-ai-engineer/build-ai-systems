# Course Code Map

Canonical lesson content lives in
`/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/`.
This file maps each numbered lesson to the code in this repository.

Examples live in one folder per lesson, so `examples/lesson-05/` is exactly
what lesson 5 uses. Every path below was checked against the tree. If a lesson links to a file,
that link and this table have to agree.

| # | Lesson | Code |
|---|---|---|
| 1 | Introduction to Build AI Systems | `brief.md` |
| 2 | Use AI Models and SDKs | `examples/lesson-02/01_basic_model_call.py`, `examples/lesson-02/02_structured_outputs.py` |
| 3 | AI System Design Patterns | `examples/lesson-03/01_deterministic_workflow.py` |
| 4 | Build AI Agents | `examples/lesson-04/01_agent_by_hand.py`, `examples/lesson-04/adk_support_agent/agent.py` |
| 5 | Agentic RAG with PostgreSQL | `examples/lesson-05/step_01_setup.sql`, `examples/lesson-05/step_02_populate_database.py`, `examples/lesson-05/step_03_agentic_search.py`, `docs/rag/postgres-document-store.md`, `docs/rag/agentic-search.md`, `policies/` |
| 6 | Vector, Keyword, and Hybrid Search | `examples/lesson-06/step_01_setup.sql`, `examples/lesson-06/step_02_chunk_text.py`, `examples/lesson-06/step_03_populate_database.py`, `examples/lesson-06/step_04_vector_search.py`, `examples/lesson-06/step_05_keyword_search.py`, `examples/lesson-06/step_06_hybrid_search.py`, `docs/rag/postgres-and-pgvector.md`, `docs/rag/vector-search.md`, `docs/rag/keyword-search.md`, `docs/rag/hybrid-search.md`, `policies/` |
| 7 | Design and Plan the Production System | `brief.md`, `ARCHITECTURE.md`, `docs/final-agent-spec.md` |
| 8 | Run and Understand the Local Policy Assistant | `migrations/`, `app/support_agent_app/worker/`, `app/support_agent_app/database/`, `app/support_agent_app/demos/run_workflow.py`, `app/support_agent_app/demos/seed_request.py` |
| 9 | Deploy the Private Worker to Google Cloud | `Dockerfile`, `scripts/provision-dev.sh`, `scripts/build-and-push.sh`, `scripts/deploy-dev.sh`, `docs/worker-authentication.md`, `docs/resources/deploy-with-codex-prompt.md` |
| 10 | Connect and Deploy the Slack Webhook | `app/support_agent_app/api/`, `app/support_agent_app/api/task_queue.py`, `slack/`, `docs/slack-setup.md`, `app/support_agent_app/demos/send_slack_event.py`, `docs/deploying-to-cloud-run.md` |
| 11 | Test and Evaluate the Complete System | `tests/unit/`, `tests/functional/`, `tests/evals/`, `app/support_agent_app/testing/fixtures.py`, `app/support_agent_app/demos/run_state_machine.py`, `docs/resources/hr-policy-demo-questions.md` |
| 12 | Operate and Improve the Cloud System | `ARCHITECTURE.md`, `docs/final-agent-spec.md`, `docs/deploying-to-cloud-run.md`. Planned: recovery and retention jobs, dashboards, alerts, load checks, and operational runbooks |

## Commands the lessons tell students to run

```bash
uv sync
cp examples/.env.sample examples/.env

uv run python examples/lesson-02/01_basic_model_call.py
uv run python examples/lesson-02/02_structured_outputs.py
uv run python examples/lesson-03/01_deterministic_workflow.py
uv run python examples/lesson-04/01_agent_by_hand.py
(cd examples/lesson-04 && uv run adk web --port 8000)
createdb rag_lesson
psql rag_lesson < examples/lesson-05/step_01_setup.sql
uv run python examples/lesson-05/step_02_populate_database.py
uv run python examples/lesson-05/step_03_agentic_search.py
psql rag_lesson < examples/lesson-06/step_01_setup.sql
uv run python examples/lesson-06/step_02_chunk_text.py
uv run python examples/lesson-06/step_03_populate_database.py
uv run python examples/lesson-06/step_04_vector_search.py
uv run python examples/lesson-06/step_05_keyword_search.py
uv run python examples/lesson-06/step_06_hybrid_search.py

uv run python -m unittest discover -s tests/unit -t .
uv run demo-workflow --fixture documented
uv run demo-workflow --fixture unsupported
uv run demo-workflow --fixture invalid-evidence
uv run demo-seed-request
./demo.sh
scripts/deploy-dev.sh --worker-only
```

Fixture names are `documented`, `unsupported`, `sensitive`, `conflicting`,
`prompt-injection`, and `invalid-evidence`, defined in
`app/support_agent_app/testing/fixtures.py`.

## Known gap

Lesson 12 still needs recovery and retention jobs, dashboards, alerts, load checks, and operational runbooks.
