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
| 4 | Build an AI Agent by Hand | `examples/lesson-04/01_agent_by_hand.py`, `examples/lesson-04/02_first_framework_agent.py` |
| 5 | Retrieval-Augmented Generation | `examples/lesson-05/01_file_rag.py`, `examples/lesson-05/02_sql_rag.py`, `examples/lesson-05/03_vector_rag.py`, `examples/lesson-05/04_hybrid_rag.py`, `policies/` |
| 6 | Design the Production Slack Assistant | `brief.md`, `ARCHITECTURE.md`, `docs/final-agent-spec.md` |
| 7 | Build the Slack Assistant | `app/support_agent_app/api/`, `slack/manifest.json`, `app/support_agent_app/demos/send_slack_event.py` |
| 8 | Connect the Agent and Knowledge Base | `app/support_agent_app/worker/agent/`, `policies/`, `app/support_agent_app/demos/run_workflow.py` |
| 9 | Add the Queue and Background Worker | `app/support_agent_app/api/task_queue.py`, `app/support_agent_app/worker/`, `app/support_agent_app/demos/run_state_machine.py` |
| 10 | Complete the Production Behaviour | `app/support_agent_app/application/lifecycle.py`, `app/support_agent_app/database/repositories/`, `tests/functional/database/` |
| 11 | Test and Evaluate the AI System | `app/support_agent_app/testing/fixtures.py`, `tests/unit/worker/agent/test_support_workflow.py`, `tests/evals/` |
| 12 | Deploy and Operate on Google Cloud | `Dockerfile`, `scripts/provision-dev.sh`, `scripts/build-and-push.sh`, `scripts/deploy-dev.sh`, `docs/deploying-to-cloud-run.md`, `docs/worker-authentication.md`. Planned: recovery and retention jobs, their schedules, operational checks |

## Commands the lessons tell students to run

```bash
uv sync
cp examples/.env.sample examples/.env

uv run python examples/lesson-02/01_basic_model_call.py
uv run python examples/lesson-02/02_structured_outputs.py
uv run python examples/lesson-03/01_deterministic_workflow.py
uv run python examples/lesson-04/01_agent_by_hand.py
uv run python examples/lesson-04/02_first_framework_agent.py
uv run python examples/lesson-05/01_file_rag.py
uv run python examples/lesson-05/02_sql_rag.py --category annual_leave --field carry_over_days
uv run python examples/lesson-05/03_vector_rag.py
uv run python examples/lesson-05/04_hybrid_rag.py

uv run python -m unittest discover -s tests/unit -t .
uv run demo-workflow --fixture documented
uv run demo-workflow --fixture unsupported
uv run demo-workflow --fixture invalid-evidence
```

Fixture names are `documented`, `unsupported`, `sensitive`, `conflicting`,
`prompt-injection`, and `invalid-evidence`, defined in
`app/support_agent_app/testing/fixtures.py`.

## Known gaps

- `README.md` refers to `demo-worker`, `demo-end-to-end`, and
  `tests/integration`. None of the three exist: the installed demo commands are
  `demo-workflow`, `demo-state-machine`, `demo-seed-request`, and
  `demo-slack-event`, and the test directories are `tests/unit`,
  `tests/functional`, and `tests/evals`.
- Lesson 12 has no code yet.
