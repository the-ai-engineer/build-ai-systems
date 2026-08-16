create table if not exists support_documents (
    id text primary key,
    source_file text not null,
    title text not null,
    category text not null,
    summary text not null,
    keywords text[] not null default '{}',
    body text not null,
    content_hash text not null,
    revision text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists support_documents_active_id_idx
    on support_documents (id)
    where is_active = true;
