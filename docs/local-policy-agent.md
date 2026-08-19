# Local Policy Agent

This is the first runnable slice of the HR policy assistant.
It has no Slack, Cloud Tasks, or Cloud Run dependency.

The default commands use a deterministic Pydantic AI `FunctionModel` and the synthetic policies in `policies/`.
They need no model credentials, database credentials, or network access.

```bash
uv run python -m unittest tests.test_support_workflow
uv run demo-workflow --fixture documented
uv run demo-workflow --fixture unsupported
uv run demo-workflow --fixture prompt-injection
```

The documented fixture prints an answer, verified filename, exact excerpt, and content revision.
The unsupported and prompt-injection fixtures print `human_review` with no automated answer.

## Postgres policy registry

Set `DATABASE_URL` outside the repository, then create and seed the active policy registry:

```bash
uv run python -m support_agent_app.seed_policies
uv run demo-workflow --fixture documented --repository postgres
```

The Postgres adapter exposes only the active document index and single-document lookup.
Its SQL is fixed and parameterized.

## Optional Google Cloud model run

The configured model defaults to `google-cloud:gemini-3.5-flash`.
Pydantic AI uses Application Default Credentials with `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
No Gemini API key is required or stored by this application.

After configuring Application Default Credentials outside the repository, run:

```bash
uv run demo-workflow --fixture documented --live-model
```

Set `SUPPORT_AGENT_MODEL` or pass `--model` to evaluate another compatible model without changing the workflow.
The live model must pass the deterministic and support evaluation checks before deployment.

Every run records the model ID, token counts, duration, finish reason, tool calls, model turns, and selected document revisions.
It does not record the complete question or policy text in run metadata.
The demo estimates request cost from a dated price file in `support_agent_app/prices/`.
