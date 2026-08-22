-- Step 1: Create the Lesson 06 search schema and indexes.
create extension if not exists vector;
create schema if not exists lesson_06;

create table if not exists lesson_06.support_documents (
    id text primary key,
    title text not null,
    summary text not null,
    body text not null,
    content_hash text not null,
    updated_at timestamptz not null default now()
);

create table if not exists lesson_06.support_document_chunks (
    id text primary key,
    document_id text not null references lesson_06.support_documents(id) on delete cascade,
    chunk_index integer not null check (chunk_index >= 0),
    content text not null,
    embedding_model text not null,
    embedding vector(768) not null,
    search_vector tsvector generated always as (
        to_tsvector('english', content)
    ) stored,
    unique (document_id, chunk_index)
);

create index if not exists support_document_chunks_document_id_idx
    on lesson_06.support_document_chunks (document_id);

create index if not exists support_document_chunks_keyword_idx
    on lesson_06.support_document_chunks using gin (search_vector);

create index if not exists support_document_chunks_embedding_idx
    on lesson_06.support_document_chunks
    using hnsw (embedding vector_cosine_ops);
