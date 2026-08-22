# Set up the PostgreSQL document store

Lesson 05 uses one small PostgreSQL table for approved policy documents.
It deliberately does not add chunks, embeddings, or pgvector.

## Create the local database

Start your local PostgreSQL server, then create one database for both retrieval lessons:

```bash
createdb rag_lesson
```

If `rag_lesson` already exists, continue to the next command.
The examples use your operating-system user and the normal local PostgreSQL socket, so they do not need a password or connection URL.

## Apply the raw SQL

```bash
psql rag_lesson < examples/lesson-05/01_setup.sql
```

The SQL creates `lesson_05.support_documents` with a stable ID, title, summary, complete body, content hash, and update time.

## Load the policies

```bash
uv run python examples/lesson-05/populate_database.py
```

Expected result:

```text
Loaded 14 complete documents into Postgres.
```

The population command reads the canonical Markdown files in `policies/`.
Running it again replaces the lesson's document rows with the current approved policies.

Inspect the document index:

```bash
psql rag_lesson -c \
  'select id, title, summary from lesson_05.support_documents order by title;'
```

Lesson 05 now has everything the agent needs to list the available documents and load one complete policy by ID.

## Use a different local connection

The examples default to `postgresql:///rag_lesson`.
Set `RAG_DATABASE_URL` in `examples/.env` when your local server uses another user, host, port, or database:

```dotenv
RAG_DATABASE_URL=postgresql://postgres:password@localhost:5432/rag_lesson
```

Do not commit a real database password.

## Ask a coding agent to set this up

Copy this prompt into Codex or another coding agent from the repository root:

```text
Set up the Lesson 05 PostgreSQL example on my machine.

First inspect my operating system, installed PostgreSQL tools, running server, and existing databases.
Use my native local PostgreSQL installation, not Docker.
Create the rag_lesson database only if it does not exist.
Apply examples/lesson-05/01_setup.sql, run the population script, and show me the document count.
Do not delete or overwrite any existing database, role, schema, or configuration.
If PostgreSQL is missing or needs a system-level change, explain the exact command and wait for my approval.
Finish by giving me the commands I can use next time.
```
