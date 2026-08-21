# Lesson 04: Build AI Agents

`01_agent_by_hand.py` implements the agent loop directly in Python.
It uses the OpenAI SDK so every message, tool call, tool result, and stopping
condition stays visible.

`adk_support_agent/agent.py` is lesson 04.02.
It keeps the same support-document domain and tools, but Google ADK owns the
agent loop and runs Gemini on Google Cloud.

## Set up Google Cloud for lesson 04.02

You need a Google Cloud project with billing enabled.
Your user needs the Agent Platform User role, `roles/aiplatform.user`, in that
project.

Install and initialize the Google Cloud CLI, then run:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

ADK uses Application Default Credentials.
Do not create or store a Gemini API key for this lesson.

From the repository root, create the local agent environment file from the
committed example:

```bash
cp examples/lesson-04/adk_support_agent/.env.example \
  examples/lesson-04/adk_support_agent/.env
```

Edit `GOOGLE_CLOUD_PROJECT` in `.env` if you use a different project.
ADK Web loads this file from the agent package.

`gemini-3.5-flash` is the tested default.
Override it only when you deliberately want to evaluate another Gemini model:

```bash
export SUPPORT_AGENT_MODEL=gemini-3.5-flash
```

## Run lesson 04.02 in ADK Web

Start the development UI from the directory that contains the agent package:

```bash
cd examples/lesson-04
uv run adk web --port 8000
```

Open `http://localhost:8000`, select `adk_support_agent`, and try:

> Can I return a backpack if I opened the box but have not used it?

ADK Web is a local development and debugging tool.
This small lesson example leaves out the explicit model-turn, tool-call, timeout,
and structured-output limits that the production policy agent adds later.
The production course application still runs its private worker on Cloud Run.
