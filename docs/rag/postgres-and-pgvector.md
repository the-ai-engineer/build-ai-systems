# Set up PostgreSQL and pgvector

This guide creates one local teaching database for every Lesson 05 example.
The database runs in Docker, while the Python examples run on your machine.

## What you will create

The raw SQL in [`01_setup.sql`](../../examples/lesson-05/01_setup.sql) creates:

- `lesson_05.support_documents` for complete approved policies
- `lesson_05.support_document_chunks` for paragraph-sized chunks
- a GIN index for PostgreSQL full-text search
- an HNSW index for pgvector cosine search

The `lesson_05` schema keeps this teaching data separate from the production application schema.

## 1. Configure Google Cloud

The examples use Vertex AI through Application Default Credentials.
No Gemini API key is required.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project build-ai-systems-dev
```

Copy the example environment file and set the project:

```bash
cp examples/.env.sample examples/.env
```

```dotenv
GOOGLE_GENAI_USE_ENTERPRISE=TRUE
GOOGLE_CLOUD_PROJECT=build-ai-systems-dev
GOOGLE_CLOUD_LOCATION=global
RAG_DATABASE_URL=postgresql://rag:rag@localhost:5433/rag_lesson
```

The database username and password above are only for the disposable local container.
Do not reuse them for a deployed database.

## 2. Start PostgreSQL

```bash
docker compose -f examples/lesson-05/compose.yaml up -d --wait
```

Check that it is healthy:

```bash
docker compose -f examples/lesson-05/compose.yaml ps
```

The `postgres` service should report `healthy`.
It listens on local port `5433` to avoid clashing with a PostgreSQL server on the default port.

## 3. Apply the raw SQL

```bash
docker compose -f examples/lesson-05/compose.yaml exec -T postgres \
  psql -U rag -d rag_lesson < examples/lesson-05/01_setup.sql
```

This command is safe to run again.
The tables and indexes use `if not exists`.

Inspect the schema:

```bash
docker compose -f examples/lesson-05/compose.yaml exec postgres \
  psql -U rag -d rag_lesson -c '\d lesson_05.support_document_chunks'
```

## 4. Seed documents and embeddings

```bash
uv run python examples/lesson-05/02_seed_documents.py
```

Expected result:

```text
Loaded 3 documents and 9 chunks into Postgres.
```

The seed command reads the canonical Markdown files in `policies/`.
It stores each whole document, splits it on paragraph boundaries, and asks `gemini-embedding-001` for a 768-dimensional embedding for each chunk.
Running it again updates current documents, replaces their chunks, and removes policies that are no longer in the approved directory.

Inspect the data:

```bash
docker compose -f examples/lesson-05/compose.yaml exec postgres \
  psql -U rag -d rag_lesson -c \
  'select document_id, count(*) from lesson_05.support_document_chunks group by document_id order by document_id;'
```

## How the ingestion path works

```mermaid
flowchart LR
    M["Markdown policies"] --> D["support_documents"]
    M --> P["Split on paragraphs"]
    P --> G["Gemini document embeddings"]
    G --> C["support_document_chunks"]
    C --> V["HNSW vector index"]
    C --> K["GIN full-text index"]
```

Document embeddings use the `RETRIEVAL_DOCUMENT` task type.
Search questions use `RETRIEVAL_QUERY`.
That distinction gives the embedding model the correct role for each input.

## Troubleshooting

`connection refused` means the container is not healthy or the URL uses the wrong port.
Run `docker compose -f examples/lesson-05/compose.yaml ps` and check for port `5433`.

`type "vector" does not exist` means the SQL was applied to a PostgreSQL server without pgvector.
Use the provided Compose image and re-run `01_setup.sql`.

An authentication or quota-project error means Application Default Credentials are missing or stale.
Run the two `gcloud auth application-default` commands again.

To stop the database without deleting it:

```bash
docker compose -f examples/lesson-05/compose.yaml stop
```

To delete the disposable lesson database and start clean:

```bash
docker compose -f examples/lesson-05/compose.yaml down --volumes
```

The final command permanently removes the local lesson data.
