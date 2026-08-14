create table if not exists support_requests (
    request_id uuid primary key,
    slack_event_id text not null unique,
    slack_team_id text not null,
    slack_channel_id text not null,
    slack_message_ts text not null,
    slack_thread_ts text not null,
    slack_user_id text not null,
    question_text text not null,
    content_expires_at timestamptz not null,
    status text not null check (
        status in ('accepted', 'queued', 'processing', 'completed', 'failed', 'reconciliation')
    ),
    task_generation integer not null default 1 check (task_generation > 0),
    confirmed_task_name text,
    business_attempt_count integer not null default 0 check (
        business_attempt_count between 0 and 5
    ),
    last_error_category text,
    created_at timestamptz not null default now(),
    queued_at timestamptz,
    processing_at timestamptz,
    completed_at timestamptz,
    failed_at timestamptz
);

create table if not exists support_request_claims (
    request_id uuid not null references support_requests (request_id),
    claim_token uuid not null,
    lease_version bigint not null check (lease_version > 0),
    lease_expires_at timestamptz not null,
    business_attempt_number integer not null check (business_attempt_number between 1 and 5),
    claimed_at timestamptz not null default now(),
    released_at timestamptz,
    primary key (request_id, lease_version),
    unique (claim_token),
    unique (request_id, claim_token),
    unique (request_id, business_attempt_number)
);

create table if not exists support_attempts (
    attempt_id uuid primary key,
    request_id uuid not null references support_requests (request_id),
    task_generation integer not null check (task_generation > 0),
    claim_token uuid,
    attempt_kind text not null check (attempt_kind in ('workflow', 'delivery_exhausted')),
    outcome text not null check (
        outcome in ('processing', 'completed', 'retryable', 'permanent_failure', 'reconciliation')
    ),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    foreign key (request_id, claim_token)
        references support_request_claims (request_id, claim_token),
    unique (claim_token)
);

create unique index if not exists support_attempts_delivery_generation_uidx
    on support_attempts (request_id, task_generation)
    where attempt_kind = 'delivery_exhausted';

create table if not exists agent_runs (
    agent_run_id uuid primary key,
    request_id uuid not null references support_requests (request_id),
    claim_token uuid not null,
    model_id text not null,
    model_location text not null,
    service_tier text not null,
    input_tokens integer not null check (input_tokens >= 0),
    retrieved_context_tokens integer not null check (retrieved_context_tokens >= 0),
    output_tokens integer not null check (output_tokens >= 0),
    duration_ms integer not null check (duration_ms >= 0),
    finish_reason text not null,
    tool_call_count integer not null check (tool_call_count >= 0),
    model_turn_count integer not null check (model_turn_count >= 0),
    created_at timestamptz not null default now(),
    foreign key (request_id, claim_token)
        references support_request_claims (request_id, claim_token),
    unique (request_id, claim_token)
);

create table if not exists agent_run_sources (
    agent_run_id uuid not null references agent_runs (agent_run_id) on delete cascade,
    document_id text not null,
    document_revision text not null,
    primary key (agent_run_id, document_id)
);

create table if not exists support_decisions (
    decision_id uuid primary key,
    request_id uuid not null references support_requests (request_id),
    claim_token uuid not null,
    decision text not null check (decision in ('answer', 'human_review')),
    reason_code text check (
        reason_code is null
        or reason_code in ('off_topic', 'unsupported', 'sensitive', 'conflict', 'invalid_evidence')
    ),
    answer text,
    reason text not null,
    sources jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    foreign key (request_id, claim_token)
        references support_request_claims (request_id, claim_token),
    unique (request_id, claim_token),
    check (
        (decision = 'answer' and answer is not null and reason_code is null)
        or (decision = 'human_review' and answer is null and reason_code is not null)
    )
);

create table if not exists outbound_actions (
    action_id uuid primary key,
    request_id uuid not null references support_requests (request_id),
    action_generation integer not null check (action_generation > 0),
    claim_token uuid not null,
    action_type text not null check (action_type = 'reply'),
    status text not null check (
        status in ('pending', 'sending', 'succeeded', 'failed', 'uncertain', 'cancelled')
    ),
    outbound_text text not null,
    content_hash text not null,
    slack_message_ts text,
    last_error_category text,
    started_at timestamptz,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    foreign key (request_id, claim_token)
        references support_request_claims (request_id, claim_token)
);

create unique index if not exists outbound_actions_one_live_reply_uidx
    on outbound_actions (request_id)
    where action_type = 'reply' and status <> 'cancelled';

create unique index if not exists outbound_actions_one_successful_reply_uidx
    on outbound_actions (request_id)
    where action_type = 'reply' and status = 'succeeded';

create index if not exists support_request_claims_latest_idx
    on support_request_claims (request_id, lease_version desc);

create index if not exists outbound_actions_request_idx
    on outbound_actions (request_id, action_generation);
