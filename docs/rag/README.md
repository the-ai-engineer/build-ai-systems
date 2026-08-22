# RAG implementation guides

The course separates the production retrieval choice from three optional alternatives.

- Lesson 05 uses [agentic search](agentic-search.md) over complete documents in PostgreSQL.
- Lesson 06 builds [vector search](vector-search.md), [keyword search](keyword-search.md), and [hybrid search](hybrid-search.md) as standalone alternatives.

## Choose a strategy

| Strategy | Retrieve | Best fit | Main tradeoff |
|---|---|---|---|
| [Agentic search](agentic-search.md) | A complete document chosen from titles and summaries | A small, curated policy set | More model decisions, but no chunk ranking |
| [Vector search](vector-search.md) | Semantically similar chunks | Questions and documents use different words | Exact identifiers and rare terms can rank poorly |
| [Keyword search](keyword-search.md) | Chunks containing matching words | Exact identifiers, names, and rare terms | Paraphrases can be missed |
| [Hybrid search](hybrid-search.md) | Chunks found by both semantic and keyword search | General-purpose search over mixed content | More moving parts to tune and observe |

Structured SQL retrieval is also a form of retrieval-augmented generation.
It is a good fit when the answer already lives in typed rows and columns, such as an order status or account balance.
It is mentioned in the lesson, but it is not a fourth demo because the course problem is document retrieval.

```mermaid
flowchart LR
    Q["Employee question"] --> C{"What shape is the knowledge?"}
    C -->|"Small set of complete policies"| A["Agentic search"]
    C -->|"Meaning matters"| V["Vector search"]
    C -->|"Exact words matter"| K["Keyword search"]
    C -->|"Meaning and exact words matter"| H["Hybrid search"]
    C -->|"Typed facts"| S["Direct SQL query"]
```

## Run Lesson 05

Start with the [PostgreSQL document store setup](postgres-document-store.md).
It creates one authoritative table:

```mermaid
erDiagram
    SUPPORT_DOCUMENTS {
        text id PK
        text title
        text summary
        text body
        text content_hash
    }
```

Then run the [agentic search example](agentic-search.md) from the command line.
This is the approach used by the production Slack assistant.

## Run Lesson 06

Start with the [PostgreSQL and pgvector setup](postgres-and-pgvector.md).
Lesson 06 creates a separate schema in the shared local `rag_lesson` database:

```mermaid
erDiagram
    SUPPORT_DOCUMENTS ||--o{ SUPPORT_DOCUMENT_CHUNKS : contains
    SUPPORT_DOCUMENTS {
        text id PK
        text title
        text summary
        text body
        text content_hash
    }
    SUPPORT_DOCUMENT_CHUNKS {
        text id PK
        text document_id FK
        integer chunk_index
        text content
        vector embedding
        tsvector search_vector
    }
```

The lesson follows five visible steps:

1. Split Markdown with `chunk_text()`.
2. Populate PostgreSQL with chunks and embeddings.
3. Run `vector_search()`.
4. Run `keyword_search()`.
5. Combine both rankings with `hybrid_search()` and Reciprocal Rank Fusion.

Later course lessons do not depend on Lesson 06.
