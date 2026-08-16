# Python AI Application Standards

Version 1.0, August 2026.
A reusable set of coding and project structure standards for Python AI applications.

## 1. Use one house style across every project

Coding agents can produce working code quickly, but they do not automatically give every repository the same shape.
One agent creates a `services.py`, another puts everything in `main.py`, and a third invents `helpers/`, `core/`, and `utils/`.
Each choice may work on its own. The collection becomes difficult for a human or another agent to understand.

These standards provide an opinionated default for Python web services, asynchronous workers, AI applications, and data-backed APIs.
The goal is simple: if you understand one project, you should be able to find your way around every other project that follows the same structure.

The standard is deliberately specific.
A useful house style makes common decisions once, while still allowing a project to record a justified exception.

## 2. Ten core rules

1. Prefer clarity over cleverness.
2. Give every component one clear owner and responsibility.
3. Make runtime entry points, external integrations, and data ownership visible in the directory structure.
4. Keep HTTP handling, business orchestration, AI behaviour, persistence, and external clients separate.
5. Use explicit dependency construction instead of hidden global state.
6. Keep production code separate from tests, examples, generated files, and local artifacts.
7. Store each document, fixture, prompt, and configuration value in one canonical place.
8. Add a directory only when it owns real code.
9. Do not add empty directories for possible future work.
10. Make every file and interface earn its boundary. Prefer fewer, clearer files.
11. When the standard would make the code harder to read, deviate and record why in `ARCHITECTURE.md`.

## 3. Default repository layout

This is a starting shape, not a target to fill in.
Omit any component the application does not need.
A synchronous API without a background worker should not contain an empty `worker/` directory.

The file names under each component show what that component can own once it is
large enough to need the separation. They are not a required file set.
A component with one route belongs in one file. Splitting it into `main.py`,
`routes.py`, `schemas.py`, and `auth.py` to match the tree below makes it harder
to read, not easier, and is a deviation in the wrong direction.

```
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
    api/           main.py routes.py schemas.py auth.py
    application/   protocols.py process_request.py
    worker/        main.py routes.py schemas.py auth.py
    agent/         agent.py prompts.py tools.py schemas.py evidence.py
    database/      connection.py repositories/
    integrations/  messaging.py task_queue.py model_provider.py
    commands/      seed_data.py
    settings.py

migrations/
tests/
  unit/         api/ application/ agent/ worker/
  integration/  api/ database/ integrations/ worker/
infra/
examples/
```

`<package>` is the importable Python package name, in lowercase words separated by underscores.

| Boundary | Owns |
|---|---|
| `api` | Accept and validate public HTTP requests |
| `worker` | Accept and process asynchronous jobs |
| `commands` | Run deliberate operator actions |
| `application` | Coordinate use cases and define protocols |
| `agent` | Own prompts, tools, evidence, and model behaviour |
| `database` | Persist and retrieve durable data |
| `integrations` | Talk to messaging systems, model providers, queues, and other services |

## 4. Root documents

**`ARCHITECTURE.md` describes the current system**, not a hoped-for future one.
It explains runtime services and how they communicate, what each component owns, dependency direction, important request and background-job flows, durable data and its owner, external systems and trust boundaries, authentication and authorization boundaries, retry and recovery behaviour, deployment topology, and the architectural rules future changes must preserve.
Update it when a change alters ownership, dependencies, interfaces, stored data, trust boundaries, or deployment topology.

**`README.md` gets a developer running.**
What the application does, how to install it, how to run each service locally, how to run tests, and where to find the architecture.
It is not a design specification or a development diary.

**`AGENTS.md` points to durable instructions.**
When this document is the complete coding policy, `AGENTS.md` needs only one instruction linking to it.

## 5. Component ownership

**`api/`** verifies request identity, validates HTTP input, calls an application capability, and translates the result into an HTTP response.
It must not contain AI prompts, SQL, background-job orchestration, or provider clients created inside route functions.
Long-running work must not hide inside a synchronous request path.
Use a small `main.py` as the composition root.

**`application/`** contains named use cases, protocols implemented by adapters, transaction and side-effect sequencing, and application-level result types.
It must not import the web framework, provider SDKs, concrete agents, concrete database connections, or runtime entry points.
Name use cases after the action they perform. Avoid a generic `service.py`.

**`worker/`** authenticates queue invocations, validates a small task payload, calls an application use case, and returns the status the queue expects.
It should pass a durable identifier rather than a complete sensitive payload.
It must not contain provider-specific messaging, model, or queue code, and must not treat an in-memory queue as the production source of truth.

**`agent/`** owns agent construction, system instructions, prompt templates, model tools, structured schemas, deterministic output validation, source verification, and model usage limits.
It implements an application-owned protocol and is injected at a composition root.
Treat model output as untrusted input and validate it before any external side effect.
Keep prompts in named constants or prompt files.

**`database/`** owns connection creation, transaction boundaries, repository implementations, row mapping, and migration support.
Name repositories after the capability they provide.
Keep SQL close to the repository or migration that owns it, use parameterized queries, and never build SQL from untrusted strings.

**`integrations/`** owns external clients. Provider request formats, authentication headers, SDK exceptions, retry details, and timeouts stay inside the integration.
Each exposes a small application-facing interface.
Keep clients independent so a test can combine a real model with a fake messaging client.

**`commands/`** covers deliberate operator actions such as seeding data, running retention, or reconciling failed work.
They call the same application capabilities the runtime services use and must not become a second implementation of the business rules.

## 6. Dependency direction

```
api, worker, commands   ->  application use cases
application             ->  defines behaviour and protocols
agent, database, integrations  ->  implement those protocols
```

- API routes, worker routes, and commands may depend on application interfaces, not concrete provider clients.
- Agent code may implement or use application protocols, but must not depend on a concrete Postgres repository.
- Application use cases must not import concrete agent, database, or integration adapters.
- Integration clients must not import API routes or worker entry points.
- Database repositories must not invoke messaging or model providers.
- Composition roots may import concrete implementations, because their job is to wire the application.
- Avoid circular imports and import-time side effects.
- Keep `__init__.py` files empty or limited to a deliberate public interface.

Use `Protocol` or an abstract base class when more than one implementation exists, a boundary needs a deterministic fake, or a use case would otherwise import a concrete adapter and lose its independence.
Do not introduce an interface for every class by default.

Prefer structural typing. Do not make a class inherit from a `Protocol` to prove
it complies: a `Protocol` subclass silently inherits `...` bodies for anything it
fails to implement, so a missing method returns `None` at runtime instead of
failing. A type checker verifies the match where the adapter is passed in.

## 7. Settings

Use `pydantic-settings`. Do not scatter `os.getenv()` and `os.environ` through the application.
Put settings classes in `app/<package>/settings.py`, using separate classes when runtime services need different configuration or permissions.

- Commit `.env.example` with safe placeholder values.
- Never commit `.env` or provider credentials.
- Use `.env` for local development only.
- Use normal environment variables for non-secret production configuration.
- Use a cloud secret manager for production secrets.
- Validate required configuration when a process starts.
- Pass settings into composition roots and constructors.
- Do not create provider clients or settings as import-time side effects.
- Use `SecretStr` for secrets and avoid printing settings that contain them.

## 8. Migrations

Store schema migrations in the root `migrations/` directory. Do not maintain duplicate production schemas in several folders.

- Treat migrations as immutable after they have run outside local development.
- Include a migration and a verification path with every schema change.
- Give destructive migrations an explicit rollback or recovery plan.
- Enforce important invariants with database constraints where practical.
- Do not silently rewrite production schemas during application startup.

Store application-owned static data in one clearly named location.
Tests and examples reference or deliberately derive from that canonical source instead of copying it.

## 9. Tests

Organize first by purpose, then by component: `tests/unit/`, `tests/integration/`, `tests/fakes/`.

Unit tests must not require a network, cloud account, or external database.
Integration tests use real boundaries where the integration behaviour matters.

API tests cover validation, authentication, status codes, and response contracts.
Worker tests cover retries, duplicate delivery, concurrency, and partial failure.
Agent tests use deterministic models where possible and verify evidence, tool limits, and structured outputs.

Do not put real customer data or secrets in fixtures.
Do not make production modules import from `tests/`.
If a deterministic local mode is a supported part of the application, place its adapters in a clearly named `testing/` package and exclude them from production composition.

## 10. Examples

The root `examples/` directory is optional. Use it for standalone examples that teach one idea and can run independently.

Examples must not become a production dependency, contain the only copy of production behaviour, or share mutable state with running services.
Use `examples/` for teaching samples and `commands/` for supported application operations.
Do not add a separate `playground/` directory.

## 11. Infrastructure

Use `infra/` for versioned infrastructure and deployment configuration.

- Do not store secrets in infrastructure files.
- Give each runtime its own least-privilege identity.
- Make public and private services explicit.
- Keep project, region, service name, and resource settings configurable.
- Document manual deployment steps until they are automated.
- Do not create `infra/` until the repository contains infrastructure files.
- Do not use both `deployment/` and `infra/` for the same purpose.

Keep a single root `Dockerfile` when all runtimes use the same image.

## 12. Naming

Prefer names such as `messaging.py`, `document_repository.py`, `evidence.py`, and `process_request.py`.
Avoid generic dumping grounds such as `utils.py`, `helpers.py`, `common.py`, `misc.py`, a global `models.py`, or a global `services.py`.
A component can use `schemas.py`, `models.py`, or `service.py` when its package supplies the missing context, such as `api/schemas.py`.

A file reaching roughly 300 to 400 lines should trigger a responsibility review.
Split it when it owns separate concepts, changes for unrelated reasons, or is difficult to test independently.
The line count alone is not a reason to split it.

- `snake_case` for modules, functions, and variables
- `PascalCase` for classes and exceptions
- `UPPER_CASE` for constants
- names ending in `Settings` for settings classes
- names ending in `Repository` for persistence boundaries
- names ending in `Client` for external service clients

## 13. Dependencies and tooling

Declare runtime and development dependencies in `pyproject.toml`.
Commit `uv.lock` for applications and use `uv` for environment and command execution.

Projects using the `app/<package>/` layout must configure package discovery explicitly:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app/<package>"]

[tool.pyright]
extraPaths = ["app"]
```

Run `uv sync` so the package is installed in the project environment.
Application imports use `<package>`, never `app.<package>`.

Use Ruff for linting and formatting and Pyright for static type checking.
Use either the standard-library `unittest` runner or pytest consistently within a project.

The default verification shape is:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python -m unittest discover -s tests
```

Omit a command only when the project does not configure that tool, and say what was not run.

## 14. Generated and local files

Do not commit environment files, virtual environments, bytecode, test and lint caches, coverage output, local databases, generated package metadata, cloud credentials, or editor-specific workspace state.
Keep `.gitignore` current.
Every generated file should have a named source and a reproducible generation command.

## 15. Justified exceptions

Consistency is the goal, but a rule that makes code worse has failed at its job.
When following this document would produce something a reader finds harder to
follow, deviate. Record the deviation in `ARCHITECTURE.md` with the reason.
An unexplained deviation is a mistake; an explained one is a decision.

Signs the standard is being applied against its own purpose:

- a file that exists only to hold a docstring or a single small function
- a component split into the reference file set before it has the code to justify it
- an interface with one implementation, no fake, and no dependency to invert
- a layer boundary maintained by copying a signature list by hand
- a module moved so the tree matches the example rather than so the code reads better

These standards favour consistency, but they should not force meaningless structure.
A library, command-line tool, notebook project, small set of teaching examples, or framework with a strong convention may need a smaller or different layout.

Record material exceptions in `ARCHITECTURE.md`.
State why the standard does not fit and what convention replaces it.
Do not create a one-off structure without explaining how a future contributor should extend it.

## 16. Agent checklist

Before changing code:

- read `ARCHITECTURE.md`, `README.md`, and the relevant component
- identify which component owns the change
- identify the runtime and external boundaries affected
- confirm the change follows the existing dependency direction

While changing code:

- put new code under the component that owns it
- ask whether each new file makes the code easier to read; if not, do not create it
- keep route handlers and runtime entry points small
- use settings instead of direct environment access
- keep provider details inside integrations
- avoid duplicate fixtures, prompts, policies, and schemas
- add tests at the correct level

Before finishing:

- run focused tests and the repository verification commands
- update `ARCHITECTURE.md` when an architectural boundary changes
- update `.env.example` when configuration changes
- update the README when setup or run instructions change
- inspect the diff for misplaced files, secrets, generated artifacts, and unrelated changes
