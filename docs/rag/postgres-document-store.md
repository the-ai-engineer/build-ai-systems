# Set up and run the PostgreSQL document store

Lesson 05 stores complete approved policies in one PostgreSQL table.
It does not use chunks, embeddings, or pgvector.

This guide starts with a machine that has the course repository but may not have PostgreSQL.
By the end, the database contains 14 policy documents and the agent can retrieve one to answer a question.

Run every repository command from the `build-ai-systems` root.
Except for commands explicitly labelled macOS or Linux, the shared commands use one-line syntax that works in a POSIX shell and PowerShell.

## 1. Install the project dependencies

Install `uv` if it is not already available, then create the project environment:

```bash
uv sync
```

## 2. Choose how to run PostgreSQL

Use either a local installation or Docker.
The Docker route uses host port 5433 so it does not collide with a direct installation on port 5432.

### Option A: Install PostgreSQL on your machine

Use the [official PostgreSQL downloads](https://www.postgresql.org/download/) for macOS, Windows, or your Linux distribution.
Start the server using the instructions for that installer.

On macOS, Homebrew is another direct installation route:

```bash
brew install postgresql@18
brew services start postgresql@18
export PATH="$(brew --prefix postgresql@18)/bin:$PATH"
```

Verify the client and server before creating anything:

```bash
psql --version
pg_isready
psql -d postgres -c '\conninfo'
psql -d postgres -c 'select current_user, current_database();'
```

The final two commands show the role and server that later commands will use.
A Homebrew installation normally creates a PostgreSQL role with the same name as your operating-system user.
It does not normally create a role named `postgres`.

If those connection checks work, create the lesson database with that verified local role:

```bash
createdb rag_lesson
psql rag_lesson -c '\conninfo'
```

If `createdb` reports that `rag_lesson` already exists, keep it and run the connection check.
The local route does not need another database role or password because it uses your existing local role and Unix socket.

#### If the installer created only a postgres administrator

Some Linux and Windows installers create a `postgres` administrator instead of a role matching your operating-system user.
Use the administrator only to create an explicit local lesson role and database.

On Linux packages that use peer authentication, open `psql` with:

```bash
sudo -u postgres psql -d postgres
```

On Windows or another installer that gave you a password for `postgres`, use:

```bash
psql -U postgres -d postgres
```

At the `psql` prompt, create the role and database:

```sql
create role rag_user with login password 'rag_password';
create database rag_lesson owner rag_user;
\q
```

`rag_password` is only for this local teaching database.
Do not reuse it or commit a real password.

Copy the example environment file if you do not already have one:

```bash
cp examples/.env.sample examples/.env
```

Add this connection to `examples/.env`:

```dotenv
RAG_DATABASE_URL=postgresql://rag_user:rag_password@localhost:5432/rag_lesson
```

Verify the explicit role:

```bash
psql -h localhost -U rag_user -d rag_lesson -c '\conninfo'
```

Do not create a `postgres` role when your direct installation already works with your operating-system role.

### Option B: Run PostgreSQL in Docker

The pgvector project publishes a PostgreSQL 18 image that also supports Lesson 06.
Create a container, lesson role, password, and database in one command:

```bash
docker run --name rag-postgres --env POSTGRES_USER=rag_user --env POSTGRES_PASSWORD=rag_password --env POSTGRES_DB=rag_lesson --publish 5433:5432 --detach pgvector/pgvector:pg18
```

`rag_password` is a local teaching password.
Do not reuse it or commit a real password.

Verify the container and connection:

```bash
docker exec rag-postgres pg_isready -U rag_user -d rag_lesson
docker exec rag-postgres psql -U rag_user -d rag_lesson -c '\conninfo'
```

The first port in `5433:5432` is the host port used by the Python examples.
The second is PostgreSQL's port inside the container.

Copy the example environment file if you do not already have one:

```bash
cp examples/.env.sample examples/.env
```

Add the Docker connection to `examples/.env`:

```dotenv
RAG_DATABASE_URL=postgresql://rag_user:rag_password@localhost:5433/rag_lesson
```

The Python examples read `RAG_DATABASE_URL`.
They do not read `DATABASE_URL` for this lesson.

## 3. Create the document schema

For a local PostgreSQL installation, run:

```bash
psql rag_lesson -f examples/lesson-05/01_setup.sql
```

If your direct installation uses the explicit `rag_user`, run:

```bash
psql -h localhost -U rag_user -d rag_lesson -f examples/lesson-05/01_setup.sql
```

For Docker, copy the SQL file into the container and apply it:

```bash
docker cp examples/lesson-05/01_setup.sql rag-postgres:/tmp/lesson-05-setup.sql
docker exec rag-postgres psql -U rag_user -d rag_lesson -f /tmp/lesson-05-setup.sql
```

The SQL creates `lesson_05.support_documents` with a stable ID, title, summary, complete body, content hash, and update time.
It is safe to run again because the schema and table use `if not exists`.

## 4. Prepare approved Markdown

This example starts with approved Markdown in `policies/`.
Real source material often arrives as PDF, DOCX, PPTX, spreadsheets, HTML, email, or scanned images.

[Docling](https://github.com/docling-project/docling) can parse those formats and export structured Markdown or JSON.
Use a conversion tool like Docling, then review and approve the converted text before inserting it into PostgreSQL.
Do not make the retrieval agent parse source files during a question because that mixes ingestion, approval, and answer-time retrieval.

The demo policies are already approved Markdown, so they are ready to load.

## 5. Load the approved policies

Run the population command:

```bash
uv run python examples/lesson-05/populate_database.py
```

Expected result:

```text
Loaded 14 complete documents into Postgres.
```

The command reads the Markdown files in `policies/`.
Running it again replaces the Lesson 05 rows with the current approved policies, so it does not create duplicates.

For a local PostgreSQL installation, inspect the document catalogue with:

```bash
psql rag_lesson -c 'select id, title, summary from lesson_05.support_documents order by title;'
```

If your direct installation uses the explicit `rag_user`, run:

```bash
psql -h localhost -U rag_user -d rag_lesson -c 'select id, title, summary from lesson_05.support_documents order by title;'
```

For Docker, use:

```bash
docker exec rag-postgres psql -U rag_user -d rag_lesson -c 'select id, title, summary from lesson_05.support_documents order by title;'
```

Each command should return 14 rows.

## 6. Configure Google Cloud

Lesson 05 uses Gemini through Google ADK and Google Cloud Application Default Credentials.
It does not use a Gemini API key.

Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) if `gcloud` is not available.
Replace the example project ID in these commands with your course project:

```bash
gcloud auth login
gcloud config set project build-ai-systems-dev
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
gcloud auth application-default set-quota-project build-ai-systems-dev
```

Copy the example environment file if you did not do this for the Docker route:

```bash
cp examples/.env.sample examples/.env
```

Set these values in `examples/.env`, replacing the example project ID with your course project:

```dotenv
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=build-ai-systems-dev
GOOGLE_CLOUD_LOCATION=global
```

Keep the `RAG_DATABASE_URL` line too if PostgreSQL runs in Docker or uses a non-default host, port, role, or database.

## 7. Run agentic search

Ask a question that an approved policy answers:

```bash
uv run python examples/lesson-05/agentic_search.py "How many days of annual leave can I carry into next year?"
```

The agent should list the policy catalogue, choose `annual-leave-policy`, read that complete document, and cite its title in the answer.

Then test the unsupported path:

```bash
uv run python examples/lesson-05/agentic_search.py "Does the company provide a bicycle repair allowance?"
```

The answer should say that it could not find an approved policy.
It must not promise to contact or connect a representative because the example has no tool that can do that.

## 8. Inspect the agent in ADK Web

The command-line script and ADK Web load the same `policy_agent` package and `prompt.txt` file.
Start the development UI from the directory that contains the package:

```bash
cd examples/lesson-05
uv run adk web --port 8000
```

Open `http://localhost:8000`, select `policy_agent`, and ask the two test questions above.
The event view shows the document-list call, document-read call, tool results, and final response.

ADK Web is a local development and debugging interface.
It is not the production application UI.

## 9. Run the demo again

You do not need to tear down PostgreSQL between runs.
The setup SQL and population command are repeatable.

For a local installation, PostgreSQL can keep running for the next lesson.
For Docker, stop and restart the same container without losing the lesson data:

```bash
docker stop rag-postgres
docker start rag-postgres
```

## Troubleshooting

`role "postgres" does not exist` means the command requested a role that your installation did not create.
Try the default connection checks without `-U postgres`.
If they work, use that operating-system role and do not create another one.

`role "your-name" does not exist` means the installer created only its `postgres` administrator.
Use the operating-system-specific administrator command above to create `rag_user` and `rag_lesson`, then set `RAG_DATABASE_URL` in `examples/.env`.

`connection refused` or `no response` from `pg_isready` means the server is not running at the selected host and port.
Start the local service or Docker container, then rerun the connection checks before creating the schema.

`database "rag_lesson" does not exist` means the local route still needs `createdb rag_lesson`, or the Docker command did not finish successfully.

`relation "lesson_05.support_documents" does not exist` means `examples/lesson-05/01_setup.sql` has not been applied to the same database used by the Python script.
Check `RAG_DATABASE_URL` in `examples/.env` and rerun the matching schema command.

`Set GOOGLE_CLOUD_PROJECT in examples/.env` means the setting is missing from `examples/.env`.
The Lesson 05 scripts do not load the repository-root `.env`.

## Ask a coding agent to set this up

Copy this prompt into Codex or another coding agent from the repository root:

```text
Set up and run the Lesson 05 PostgreSQL example on my machine.

First inspect my operating system, installed PostgreSQL tools, running servers, connection identity, and existing databases.
Ask whether I want a native local installation or Docker if neither is already running.
Do not start a second server on the same port.
Create rag_lesson only if it does not exist.
Apply examples/lesson-05/01_setup.sql, run examples/lesson-05/populate_database.py, and prove that it loaded 14 documents.
Configure Google Cloud through Application Default Credentials and examples/.env without printing credentials.
Run examples/lesson-05/agentic_search.py with one supported and one unsupported question.
Start ADK Web from examples/lesson-05 and confirm that policy_agent loads.
Do not delete or overwrite any unrelated database, role, schema, or configuration.
Ask before installing software or making a system-level change.
Finish with the verification results and the commands I can use next time.
```
