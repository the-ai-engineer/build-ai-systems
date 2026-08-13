# AGENTS.md

This repository is the public project for the Build AI Systems course.

The code is designed for lessons, recordings, and student exercises.
Prefer clarity over cleverness.
Examples should be easy to read on screen and easy to run locally.

## Course direction

The course builds a professional HR policy assistant in Python.

An employee asks a question in a dedicated Slack channel.
The system accepts the event quickly, processes it asynchronously, retrieves approved company policies, and replies in the Slack thread.
It refuses off-topic requests and sends uncertain, unsupported, or sensitive requests to a person.

The customer problem and product requirements live in `brief.md`.
Students create `ARCHITECTURE.md` during the first design lesson.
Once reviewed, `ARCHITECTURE.md` becomes the technical source of truth.

Do not add application structure or infrastructure before the architecture defines it.

## Teaching direction

- Use Python.
- Use OpenAI as the default teaching model.
- Introduce Pydantic AI after the hand-built agent lesson.
- Show provider boundaries without pretending provider capabilities are identical.
- Keep structured outputs, tool calls, and agent loops tied to real product decisions.
- Keep advanced vector and hybrid retrieval optional.
- Use Google Cloud as the deployment target.
- Keep the complete system runnable locally before cloud deployment.

Coding agents may write much of the implementation.
Students must still understand the contracts, authority boundaries, failure behaviour, and evidence required to approve that work.

## Code style

- Keep lesson examples runnable from the command line.
- Prefer simple interfaces over framework magic.
- Do not introduce cloud dependencies into early lessons.
- Do not use em dashes in prose.
- Keep Markdown sentences on separate physical lines when files get long.
- Deliver complete changes without placeholders or fake TODOs.

## Repository structure

- `brief.md` defines the customer problem and first-release scope.
- `examples/` contains standalone teaching examples for the AI foundations.
- `examples/policies/` contains sample data for the retrieval examples only.
- `tests/` verifies the examples and starting repository.
- `ARCHITECTURE.md` is intentionally absent until the first design lesson.

The examples must not import the future deployable application.
They should stay small even as the main project grows.

## Verification

Run this before reporting repository changes:

```bash
uv run python -m unittest discover -s tests
uv run python -m compileall -q examples tests
```

Run a changed model example with the required provider credentials.

Run the retrieval examples that do not need an API key:

```bash
uv run python examples/06b_sql_rag.py
```

Run the whole-document, vector, and hybrid examples with `OPENAI_API_KEY` set.
