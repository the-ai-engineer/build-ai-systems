-- Lesson 05 owns a small document store for the agentic RAG example.
create schema if not exists lesson_05;

create table if not exists lesson_05.support_documents (
    id text primary key,
    title text not null,
    summary text not null,
    body text not null,
    content_hash text not null,
    updated_at timestamptz not null default now()
);
