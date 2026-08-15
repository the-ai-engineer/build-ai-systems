# Python Application Standards

These standards define the default structure for Python applications built and maintained by people and coding agents.
They are intentionally opinionated.
The goal is that someone who understands one project can quickly understand every other project that follows the same structure.

Use these defaults for Python web services, asynchronous workers, AI applications, and data-backed APIs.
Libraries, command-line tools, notebooks, and collections of standalone examples may use a smaller structure when the default application layout does not fit.

## 1. Core rules

1. Prefer clarity over cleverness.
2. Give every component one clear owner and responsibility.
3. Make runtime entry points, external integrations, and data ownership visible in the directory structure.
4. Keep HTTP handling, business orchestration, AI behavior, persistence, and external clients separate.
5. Use explicit dependency construction instead of hidden global state.
6. Keep production code separate from tests, examples, generated files, and local artifacts.
7. Store each document, fixture, prompt, and configuration value in one canonical place.
8. Add a directory only when it owns real code.
9. Do not add empty directories as placeholders for possible future work.
10. Record justified exceptions in the root `ARCHITECTURE.md`.

## 2. Standard repository layout

Use this layout by default:

```text
ARCHITECTURE.md
README.md
AGENTS.md
PYTHON_STANDARDS.md
.env.example
.gitignore
pyproject.toml
uv.lock

app/
  <package>/
    __init__.py

    api/
      __init__.py
      main.py
      routes.py
      schemas.py
      auth.py

    application/
      __init__.py
      protocols.py
      process_request.py

    worker/
      __init__.py
      main.py
      routes.py
      schemas.py
      auth.py

    agent/
      __init__.py
      agent.py
      prompts.py
      tools.py
      schemas.py
      evidence.py

    database/
      __init__.py
      connection.py
      repositories/

    integrations/
      __init__.py
      slack.py
      cloud_tasks.py
      gemini.py

    commands/
      __init__.py
      seed_data.py

    settings.py

migrations/
tests/
  unit/
    api/
    application/
    agent/
    worker/
  integration/
    api/
    database/
    integrations/
    worker/

infra/
examples/
```

`<package>` is the importable Python package name.
Use lowercase words separated by underscores.

This is a default, not a requirement to create every directory.
For example, a synchronous API without a background worker must omit `worker/`.

## 3. Root files

### `ARCHITECTURE.md`

Every application repository must have `ARCHITECTURE.md` at its root.
It describes the system that exists today, not a hoped-for future system.

It must explain:

- the runtime services and how they communicate
- the components and what each component owns
- dependency direction
- important request and background-job flows
- durable data and which component owns it
- external systems and trust boundaries
- authentication and authorization boundaries
- retry, failure, and recovery behavior
- deployment topology
- architectural rules that future changes must preserve

Update `ARCHITECTURE.md` when a change alters ownership, dependencies, interfaces, stored data, trust boundaries, or deployment topology.

### `README.md`

The README is the operator and contributor starting point.
It should explain what the application does, how to install it, how to run each service locally, how to run tests, and where to find the architecture.

Do not turn the README into a design specification or a development diary.

### `AGENTS.md`

Keep agent instructions short.
When these standards are the complete coding policy, `AGENTS.md` should contain one instruction that links to this file.

### `PYTHON_STANDARDS.md`

Keep this document generic enough to reuse across projects.
Put product behavior, architecture decisions, and repository-specific commands in their appropriate project documents.

## 4. Component ownership

### `api/`

The API package owns public HTTP boundaries.

It may:

- verify request identity and signatures
- parse and validate HTTP input
- call an application capability
- translate results into HTTP responses
- define API request and response schemas

It must not:

- contain AI prompts or agent tools
- contain SQL
- implement background-job orchestration
- construct provider clients inside route functions
- hide long-running work inside a synchronous request path

Use a small `main.py` as the composition root for the API process.
Create the FastAPI application and wire its dependencies there.
Group routes with `APIRouter` when the service has more than one boundary.

### `application/`

The application package owns use cases and business orchestration shared by runtime boundaries.

It contains:

- named use cases such as `process_request.py`
- protocols implemented by database and external integration adapters
- transaction and side-effect sequencing
- application-level result and failure types

It must not import FastAPI, provider SDKs, concrete database connections, or runtime entry points.
API routes, worker routes, and commands call application use cases instead of duplicating orchestration.
Keep use cases named after the action they perform rather than collecting them in a generic `service.py`.

### `worker/`

The worker package owns asynchronous job handling.

It may:

- authenticate a queue or scheduler invocation
- validate a small task payload
- call the appropriate application use case
- translate application outcomes into queue responses
- return the status expected by the queue

It must not:

- accept complete sensitive payloads when a durable identifier is sufficient
- contain provider-specific Slack, model, or queue code
- duplicate the API's request acceptance logic
- treat an in-memory queue as the production source of truth

Use a separate `main.py` for the worker process.
The API and worker may be deployed independently even when they share one Python package.

### `agent/`

The agent package owns AI behavior.

It contains:

- agent construction
- system instructions and prompt templates
- tools exposed to the model
- structured input and output schemas
- deterministic validation of model output
- source and evidence verification
- model usage limits

It must not import FastAPI routes, Cloud Tasks handlers, Slack clients, or concrete database connections.
Treat model output as untrusted input and validate it before any external side effect.

Keep prompts in named constants or prompt files.
Do not scatter prompt fragments across API handlers and worker services.

### `database/`

The database package owns persistence mechanics.

It contains:

- connection creation
- transaction boundaries
- repository implementations
- database row mapping
- migration execution support

Repositories should be named after the capability they provide, such as `SupportRequestRepository` or `PolicyRepository`.
Do not create a generic repository that hides important transaction and concurrency behavior.

Keep SQL close to the repository or migration that owns it.
Use parameterized queries.
Never build SQL from untrusted strings.

### `integrations/`

The integrations package owns clients for systems outside the application.

Examples include:

- Slack
- Google Cloud Tasks
- Gemini and other model providers
- email providers
- payment providers
- object storage

Each integration must expose a small application-facing interface.
Provider request formats, authentication headers, SDK exceptions, and timeout details stay inside the integration.

Keep integrations independent.
Configuration must allow a real model with a fake Slack client or a fake model with a real local database when that combination is useful for testing.

### `commands/`

Commands own deliberate operator actions such as seeding data, running retention, or reconciling failed work.

Commands must call the same application capabilities used by runtime services.
They must not become a second implementation of the business rules.

Expose frequently used commands through `pyproject.toml` entry points when that improves usability.

## 5. Dependency direction

Dependencies should point inward toward application behavior and outward only through explicit interfaces.

```text
API, worker, and commands
          |
          v
Application use cases and protocols
          |
          v
      Agent behavior

Database and integration adapters
implement application protocols and are
wired at the runtime composition roots.
```

Follow these rules:

- API routes may depend on application interfaces, not worker internals or concrete provider clients.
- Worker routes and commands may depend on application use cases, not concrete provider clients.
- Agent code may depend on protocols owned by the application package, not Postgres implementations.
- Database and integration adapters may depend on application protocols that they implement.
- Application use cases must not import concrete database or integration adapters.
- Integration clients must not import API routes or worker entry points.
- Database repositories must not invoke Slack or model providers.
- Composition roots may import concrete implementations because their job is to wire the application.
- Avoid circular imports and import-time side effects.
- Keep `__init__.py` files empty or limited to a small deliberate public interface.

Use `Protocol` or an abstract base class when more than one implementation exists or when a boundary needs a deterministic fake.
Do not introduce an interface for every class by default.

## 6. Settings and environment configuration

Use `pydantic-settings` for application configuration.
Do not call `os.getenv()` or read `os.environ` throughout the application.

Put settings classes in `app/<package>/settings.py`.
Use separate settings classes when runtime services require different configuration or permissions.
For example, an API may require a Slack signing secret while a worker requires a Slack bot token.

Use this pattern:

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    slack_bot_token: SecretStr
    google_cloud_project: str
    google_cloud_location: str
    model_name: str
```

Standards for configuration:

- Commit `.env.example` with safe placeholder values.
- Never commit `.env`.
- Add `.env` and provider credential files to `.gitignore`.
- Use `.env` for local development only.
- Use normal environment variables for non-secret Cloud Run configuration.
- Use Google Secret Manager for production secrets.
- Validate required configuration when a process starts.
- Pass settings into composition roots and constructors.
- Do not create provider clients or settings objects as hidden import-time side effects.
- Use `SecretStr` for secret values and avoid printing settings objects containing secrets.
- Use typed URLs and identifiers where useful.

One root `.env` file is the default for local development.
Do not create several overlapping environment files unless separate local runtimes genuinely need them.

## 7. Database migrations and data files

Store schema migrations in the root `migrations/` directory.
Use one ordered migration history.
Do not maintain duplicate production schemas in several folders.

Migration rules:

- migrations are immutable after they have been applied outside local development
- every schema change includes a migration and a verification path
- destructive migrations require an explicit rollback or recovery plan
- constraints should enforce important invariants where practical
- application startup must not silently rewrite production schemas

Store application-owned static data in one clearly named location.
Tests and examples should reference or deliberately derive from the canonical data instead of copying it.

## 8. Tests

Organize tests by purpose and component:

```text
tests/
  unit/
    api/
    application/
    agent/
    worker/
  integration/
    api/
    database/
    integrations/
    worker/
  fakes/
```

Testing rules:

- unit tests do not require a network, cloud account, or external database
- integration tests use real boundaries where the integration behavior matters
- organize tests by test type first and by application component second
- API tests exercise validation, authentication, status codes, and response contracts
- worker tests exercise retry, idempotency, concurrency, and partial failure
- agent tests use deterministic models and verify evidence, tool limits, and structured outputs
- tests mirror the production component they verify
- shared fakes live under `tests/fakes/` unless they are required by a supported local runtime mode
- test fixtures must not contain real customer data or secrets
- assertions should prove behavior visible to a caller or a documented internal contract

Do not make production modules import from `tests/`.
If a deterministic local mode is part of the supported application, place its adapters in a clearly named `testing/` package and exclude them from production composition.

## 9. Examples and teaching code

The root `examples/` directory is optional.
Use it for standalone examples that teach one idea and can run independently.

Examples must not:

- become a dependency of the production application
- contain the only copy of production behavior
- share mutable state with production services
- require readers to understand the entire application

Do not create a `playground/` directory.
Use `examples/` for teaching examples and `commands/` for supported application operations.

## 10. Google Cloud infrastructure

Use `infra/` for versioned Google Cloud infrastructure and deployment configuration.

It may contain:

- Terraform
- Cloud Run service definitions
- Cloud Tasks queue configuration
- Cloud SQL configuration
- IAM bindings
- Cloud Scheduler jobs
- monitoring and alerting configuration

Keep a single root `Dockerfile` when all runtimes use the same image.
Use clearly named Dockerfiles under `infra/` when runtimes need different images.

Infrastructure rules:

- do not store secrets in infrastructure files
- grant each runtime its own least-privilege service identity
- make public and private services explicit
- keep region, project, service name, and resource settings configurable
- document manual deployment steps until they are automated
- do not create `infra/` until the repository contains infrastructure files

Do not use both `deployment/` and `infra/` for the same purpose.

## 11. Module and naming rules

Use names that state ownership and purpose.

Prefer:

- `slack.py`
- `policy_repository.py`
- `evidence.py`
- `process_request.py`

Avoid generic dumping grounds:

- `utils.py`
- `helpers.py`
- `common.py`
- a global `models.py`
- a global `services.py`
- `misc.py`

A component may use `schemas.py`, `models.py`, or `service.py` when the containing package supplies the missing context, such as `api/schemas.py` or `application/models.py`.

Keep modules small enough that their responsibility is obvious.
A file reaching roughly 300 to 400 lines triggers a responsibility review.
This is not an automatic requirement to split the file.
Split it when it owns separate concepts, changes for unrelated reasons, or is difficult to test independently.

Use:

- `snake_case` for modules, functions, and variables
- `PascalCase` for classes and exceptions
- `UPPER_CASE` for constants
- names ending in `Settings` for settings classes
- names ending in `Repository` for persistence boundaries
- names ending in `Client` for external service clients

## 12. Dependencies and tooling

Declare runtime and development dependencies in `pyproject.toml`.
Commit `uv.lock` for applications.
Use `uv` for environment and command execution.

Projects using the standard `app/<package>/` layout must configure package discovery explicitly.
Use Hatchling as the default build backend and tell Pyright where importable code lives:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app/<package>"]

[tool.pyright]
extraPaths = ["app"]
```

Replace `<package>` with the real import package name.
Run `uv sync` before running the application or tests so the package is installed in the project environment.
Application imports use `<package>`, never `app.<package>`.

Default tooling:

- Ruff for linting and formatting
- Pyright for static type checking
- the project's chosen standard-library `unittest` or pytest test runner

New projects should configure these tools when the project is created.
Existing projects should adopt them during a deliberate maintenance change rather than expanding an unrelated task.

Run the repository's documented verification commands before reporting a change.
The default verification shape is:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python -m unittest discover -s tests
```

Omit a command only when the project does not use or configure that tool, and state what was not run.

## 13. Generated and local files

Do not commit:

- `.env`
- virtual environments
- Python bytecode
- test and lint caches
- coverage output
- local databases
- generated package metadata
- cloud credentials
- editor-specific workspace state

Keep `.gitignore` current.
Generated files must have a named source and reproducible generation command.

## 14. Exceptions

These standards favor consistency, but they must not force meaningless structure.

A project may deviate when:

- it is a library rather than an application
- it is a command-line tool with no long-running service
- it contains only standalone teaching examples
- a framework imposes a different conventional layout
- a component is too small to justify its own package

Document material exceptions in `ARCHITECTURE.md`.
State the reason and the replacement convention.
Do not create one-off structures without recording how future contributors should extend them.

## 15. Agent checklist

Before changing code:

- read `ARCHITECTURE.md`, `README.md`, and the relevant component
- identify which component owns the change
- identify the runtime and external boundaries affected
- confirm that the change follows the existing dependency direction

While changing code:

- put new code under the component that owns it
- keep route handlers and runtime entry points small
- use settings instead of direct environment access
- keep provider details inside integrations
- avoid duplicate fixtures, prompts, policies, and schemas
- add tests at the correct level

Before finishing:

- run focused tests and the repository verification commands
- update `ARCHITECTURE.md` when an architectural boundary changed
- update `.env.example` when configuration changed
- update the README when run or setup instructions changed
- inspect the final diff for misplaced files, secrets, generated artifacts, and unrelated changes

## References

- [Python Packaging User Guide: `src` layout versus flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [Python documentation: packages](https://docs.python.org/3/tutorial/modules.html#packages)
- [FastAPI documentation: bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [pytest documentation: good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
