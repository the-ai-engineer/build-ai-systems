# Course Code Map

Canonical lesson content lives in `/Users/owainlewis/Code/github/owainlewis/slip/content/build-ai-systems/`.
This file only maps high-level lesson names to code in this repository.

| Lesson | Code |
|---|---|
| Customer brief and design | `brief.md`, student-created `ARCHITECTURE.md` |
| Basic model call | `examples/01_basic_model_call.py` |
| Structured output | `examples/02_structured_outputs.py` |
| Workflow and agent comparison | `examples/03_deterministic_workflow.py` |
| Agent by hand | `examples/04_agent_by_hand.py` |
| Pydantic AI agent | `examples/05_first_framework_agent.py` |
| Whole-document RAG | `examples/06a_file_rag.py`, `examples/policies/` |
| SQL RAG | `examples/06b_sql_rag.py` |
| Optional vector RAG | `examples/07a_vector_rag.py` |
| Optional hybrid RAG | `examples/07b_hybrid_rag.py` |
| Local policy application | `support_agent_app/`, `docs/policies/`, `tests/test_support_workflow.py` |
| Worker | `support_agent_app/worker.py`, `support_agent_app/worker_service.py`, `support_agent_app/demo_worker.py` |
| Queue and Slack ingress | Planned Cloud Tasks adapter and public Slack webhook |
| Reliability and evaluation | Planned integration tests, scheduled jobs, and evals |
| Production deployment | Planned Google Cloud deployment configuration and operational checks |
