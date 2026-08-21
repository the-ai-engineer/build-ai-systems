# Set up the PostgreSQL document store

Lesson 05 uses one small PostgreSQL table for approved policy documents.
It deliberately does not add chunks, embeddings, or pgvector.

## Start PostgreSQL

```bash
docker compose -f examples/lesson-05/compose.yaml up -d --wait
```

The disposable database listens on local port `5433`.

## Apply the raw SQL

```bash
docker compose -f examples/lesson-05/compose.yaml exec -T postgres \
  psql -U rag -d rag_lesson < examples/lesson-05/01_setup.sql
```

The SQL creates `lesson_05.support_documents` with a stable ID, title, summary, complete body, content hash, and update time.

## Load the policies

```bash
uv run python examples/lesson-05/02_seed_documents.py
```

Expected result:

```text
Loaded 3 complete documents into Postgres.
```

The seed command reads the canonical Markdown files in `policies/`.
Running it again updates current documents and removes policies that are no longer approved.

Inspect the document index:

```bash
docker compose -f examples/lesson-05/compose.yaml exec postgres \
  psql -U rag -d rag_lesson -c \
  'select id, title, summary from lesson_05.support_documents order by title;'
```

Lesson 05 now has everything the agent needs to list the available documents and load one complete policy by ID.

To delete the disposable database:

```bash
docker compose -f examples/lesson-05/compose.yaml down --volumes
```

This final command permanently removes the local lesson data.
