# Agentic search over complete documents

Agentic search lets the model decide how to retrieve information through tools.
In this example the agent first sees a small index of titles and summaries, then loads one complete policy by ID.

## The retrieval path

```mermaid
sequenceDiagram
    participant U as Employee
    participant A as ADK agent
    participant D as PostgreSQL
    U->>A: Ask a policy question
    A->>D: list_support_documents()
    D-->>A: IDs, titles, summaries
    A->>A: Choose the relevant ID
    A->>D: read_support_document(ID)
    D-->>A: Complete approved policy
    A-->>U: Grounded answer with title
```

The list tool is a small catalogue.
The read tool is the authority boundary because it accepts only an exact document ID from the database.
The model never invents a file path or writes its own SQL.

## Why use complete documents

Whole-document retrieval is a strong default when:

- the approved collection is small
- each document is short and focused
- document boundaries carry useful meaning
- the complete document fits comfortably in the model context

It removes chunking, embedding, and ranking from the answer path.
That makes the behaviour easier to inspect and is why the production course application starts here.

## Run it

Complete the [database setup](postgres-and-pgvector.md), then run:

```bash
uv run python examples/lesson-05/03_agentic_rag.py \
  "How many days of annual leave can I carry into next year?"
```

The ADK agent should call `list_support_documents`, choose `annual-leave-policy`, call `read_support_document`, and answer from the returned policy.

Try an unsupported question:

```bash
uv run python examples/lesson-05/03_agentic_rag.py \
  "What is the company pension contribution?"
```

The expected answer says that no approved policy was found.
It must not promise to contact or connect a representative because the example has no tool that can perform that action.

## The important design choice

The model chooses a document, but the application controls what can be read.
That split is the useful part of the pattern.

Do not expose a general file reader, arbitrary SQL tool, or unrestricted search API just because the model can call tools.
Give it the narrowest retrieval operations that solve the product problem.

## When to move beyond it

As documents become numerous or long, listing every summary and loading a complete document stops scaling.
Use [vector search](vector-search.md) to retrieve smaller passages.
Use [hybrid search](hybrid-search.md) when both semantic meaning and exact terminology matter.
