#!/usr/bin/env bash
#
# Provision the development environment for the Slack support agent on Google
# Cloud. One script, no Terraform: the course teaches the application, not an
# infrastructure tool.
#
# Safe to run again. Every step looks for the resource first and skips it when
# it is already there, so a second run reports "exists" and changes nothing.
#
#   scripts/provision-dev.sh
#   PROJECT_ID=... REGION=... ENV_FILE=... scripts/provision-dev.sh
#
# Slack credentials are read from ENV_FILE and piped into Secret Manager on
# stdin. No secret value is printed, logged, or placed on a command line.
#
# Tear the billable parts down with scripts/teardown-dev.sh.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-build-ai-systems-dev}"
REGION="${REGION:-europe-west1}"
ENV_FILE="${ENV_FILE:-${repo_root}/.env}"

AR_REPOSITORY="${AR_REPOSITORY:-support-agent}"
SQL_INSTANCE="${SQL_INSTANCE:-support-agent-dev}"
SQL_TIER="${SQL_TIER:-db-f1-micro}"
SQL_DATABASE_VERSION="${SQL_DATABASE_VERSION:-POSTGRES_17}"
SQL_DATABASE="support_agent"
SQL_USER="support_agent_app"
TASK_QUEUE="${TASK_QUEUE:-support-requests}"

WEBHOOK_SA="support-webhook"
WORKER_SA="support-worker"
MAINTENANCE_SA="support-maintenance"

SECRET_SLACK_BOT_TOKEN="slack-bot-token"
SECRET_SLACK_SIGNING_SECRET="slack-signing-secret"
SECRET_DATABASE_URL="database-url"

REQUIRED_APIS=(
  artifactregistry.googleapis.com
  run.googleapis.com
  sqladmin.googleapis.com
  cloudtasks.googleapis.com
  cloudscheduler.googleapis.com
  secretmanager.googleapis.com
  aiplatform.googleapis.com
  iam.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
)

step() { printf '\n== %s\n' "$1"; }
ok() { printf '   %s\n' "$1"; }
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }

gcloud_q() { gcloud --project "$PROJECT_ID" --quiet "$@"; }

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"; }

# Read one KEY=value from ENV_FILE without sourcing it. Returns 1 when the key
# is absent. The value is returned on stdout and never logged.
env_value() {
  local key="$1" line value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$ENV_FILE" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1
  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  [[ -n "$value" ]] || return 1
  printf '%s' "$value"
}

require_tools() {
  command -v gcloud >/dev/null 2>&1 || fail "gcloud is not installed"
  command -v openssl >/dev/null 2>&1 || fail "openssl is not installed"
  command -v curl >/dev/null 2>&1 || fail "curl is not installed"
  gcloud --quiet auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
    || fail "no active gcloud account. Run: gcloud auth login"
  gcloud --quiet projects describe "$PROJECT_ID" >/dev/null 2>&1 \
    || fail "cannot reach project ${PROJECT_ID}"
}

enable_apis() {
  step "APIs"
  local enabled missing=()
  enabled="$(gcloud --quiet services list --enabled --project "$PROJECT_ID" --format='value(config.name)')"
  local api
  for api in "${REQUIRED_APIS[@]}"; do
    if grep -qx "$api" <<<"$enabled"; then
      ok "${api} enabled"
    else
      missing+=("$api")
    fi
  done
  if ((${#missing[@]})); then
    ok "enabling ${#missing[@]}: ${missing[*]}"
    gcloud_q services enable "${missing[@]}"
  fi
}

create_service_accounts() {
  step "Service accounts"
  local pair name description
  for pair in \
    "${WEBHOOK_SA}:Public Slack webhook runtime identity" \
    "${WORKER_SA}:Private policy worker runtime identity" \
    "${MAINTENANCE_SA}:Scheduled recovery and retention identity"
  do
    name="${pair%%:*}"
    description="${pair#*:}"
    if gcloud --quiet iam service-accounts describe "$(sa_email "$name")" --project "$PROJECT_ID" >/dev/null 2>&1; then
      ok "${name} exists"
    else
      gcloud_q iam service-accounts create "$name" --display-name "$description" >/dev/null
      ok "${name} created"
    fi
  done
}

# add-iam-policy-binding on an existing binding is harmless, but it still writes
# a new policy. Read first so a second run of this script writes nothing.
has_binding() {
  local role="$1" member="$2" group="$3" target="$4"
  gcloud --quiet "$group" get-iam-policy "$target" --project "$PROJECT_ID" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${role} AND bindings.members=${member}" \
    --format='value(bindings.members)' 2>/dev/null | grep -q .
}

grant_project_role() {
  local account="$1" role="$2" member
  member="serviceAccount:$(sa_email "$account")"
  if has_binding "$role" "$member" projects "$PROJECT_ID"; then
    ok "${account} already has ${role}"
    return
  fi
  gcloud_q projects add-iam-policy-binding "$PROJECT_ID" \
    --member "$member" \
    --role "$role" \
    --condition None >/dev/null
  ok "${account} -> ${role}"
}

grant_secret_access() {
  local secret="$1" account="$2" member role=roles/secretmanager.secretAccessor
  member="serviceAccount:$(sa_email "$account")"
  if has_binding "$role" "$member" secrets "$secret"; then
    ok "${account} already reads ${secret}"
    return
  fi
  gcloud_q secrets add-iam-policy-binding "$secret" \
    --member "$member" \
    --role "$role" \
    --condition None >/dev/null
  ok "${account} -> read ${secret}"
}

create_artifact_registry() {
  step "Artifact Registry"
  if gcloud --quiet artifacts repositories describe "$AR_REPOSITORY" \
      --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    ok "${AR_REPOSITORY} exists"
    return
  fi
  gcloud_q artifacts repositories create "$AR_REPOSITORY" \
    --repository-format docker \
    --location "$REGION" \
    --description "Container images for the Slack support agent" >/dev/null
  ok "${AR_REPOSITORY} created"
}

create_sql_instance() {
  step "Cloud SQL"
  if gcloud --quiet sql instances describe "$SQL_INSTANCE" --project "$PROJECT_ID" >/dev/null 2>&1; then
    ok "${SQL_INSTANCE} exists"
  else
    ok "creating ${SQL_INSTANCE}, this takes several minutes"
    # The smallest instance that runs Postgres. Zonal, no read replica, no
    # backups: this is a development database and the policy set is seeded
    # from the repository.
    gcloud_q sql instances create "$SQL_INSTANCE" \
      --database-version "$SQL_DATABASE_VERSION" \
      --edition enterprise \
      --tier "$SQL_TIER" \
      --region "$REGION" \
      --storage-size 10GB \
      --storage-type SSD \
      --availability-type zonal \
      --no-backup >/dev/null
    ok "${SQL_INSTANCE} created"
  fi

  if gcloud --quiet sql databases describe "$SQL_DATABASE" \
      --instance "$SQL_INSTANCE" --project "$PROJECT_ID" >/dev/null 2>&1; then
    ok "database ${SQL_DATABASE} exists"
  else
    gcloud_q sql databases create "$SQL_DATABASE" --instance "$SQL_INSTANCE" >/dev/null
    ok "database ${SQL_DATABASE} created"
  fi
}

# `gcloud sql users create` takes the password as a command-line argument, where
# any other process on the machine can read it out of the process list. The REST
# call does the same job with the password on stdin. The generated password is
# alphanumeric, so it needs no JSON escaping.
create_sql_user() {
  local password="$1" token
  token="$(gcloud --quiet auth print-access-token)"
  printf '{"name":"%s","password":"%s"}' "$SQL_USER" "$password" \
    | curl --fail --silent --show-error \
        --header "Authorization: Bearer ${token}" \
        --header "Content-Type: application/json" \
        --request POST \
        --data @- \
        "https://sqladmin.googleapis.com/v1/projects/${PROJECT_ID}/instances/${SQL_INSTANCE}/users" \
        >/dev/null
}

# The application user's password lives in the database-url secret and nowhere
# else. It is generated once and reused on every later run, so re-running this
# script does not rotate a credential the deployed services are holding.
configure_sql_user_and_url() {
  step "Database credentials"
  local connection_name url password
  connection_name="$(gcloud --quiet sql instances describe "$SQL_INSTANCE" \
    --project "$PROJECT_ID" --format='value(connectionName)')"

  if url="$(gcloud --quiet secrets versions access latest \
      --secret "$SECRET_DATABASE_URL" --project "$PROJECT_ID" 2>/dev/null)"; then
    password="${url#postgresql://${SQL_USER}:}"
    password="${password%%@*}"
    if [[ "$password" == "$url" || -z "$password" ]]; then
      fail "${SECRET_DATABASE_URL} is not in the expected postgresql://user:password@... form"
    fi
    ok "reusing the stored password"
  else
    password="$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)"
    ok "generated a new password"
  fi

  if gcloud --quiet sql users list --instance "$SQL_INSTANCE" --project "$PROJECT_ID" \
      --format='value(name)' | grep -qx "$SQL_USER"; then
    ok "user ${SQL_USER} exists"
  else
    create_sql_user "$password"
    ok "user ${SQL_USER} created"
  fi

  # Cloud Run reaches Cloud SQL over a unix socket, so the host is the socket
  # directory rather than an IP address.
  url="postgresql://${SQL_USER}:${password}@/${SQL_DATABASE}?host=/cloudsql/${connection_name}"
  sync_secret "$SECRET_DATABASE_URL" "$url"
}

create_task_queue() {
  step "Cloud Tasks"
  local state
  if state="$(gcloud --quiet tasks queues describe "$TASK_QUEUE" \
      --location "$REGION" --project "$PROJECT_ID" --format='value(state)' 2>/dev/null)"; then
    ok "${TASK_QUEUE} exists"
    if [[ "$state" == "PAUSED" ]]; then
      gcloud_q tasks queues resume "$TASK_QUEUE" --location "$REGION" >/dev/null
      ok "${TASK_QUEUE} resumed"
    fi
    return
  fi
  # Ten concurrent tasks and five dispatches per second, from the spec. The
  # worker holds a 55 second application deadline inside a longer platform one.
  gcloud_q tasks queues create "$TASK_QUEUE" \
    --location "$REGION" \
    --max-concurrent-dispatches 10 \
    --max-dispatches-per-second 5 \
    --max-attempts 5 \
    --min-backoff 10s \
    --max-backoff 300s \
    --max-doublings 3 >/dev/null
  ok "${TASK_QUEUE} created"
}

# Write a value only when it differs from the version already stored, so a
# second run does not pile up identical secret versions.
sync_secret() {
  local name="$1" value="$2" current
  if ! gcloud --quiet secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud_q secrets create "$name" --replication-policy automatic >/dev/null
    printf '%s' "$value" | gcloud_q secrets versions add "$name" --data-file=- >/dev/null
    ok "${name} created"
    return
  fi
  if current="$(gcloud --quiet secrets versions access latest --secret "$name" \
      --project "$PROJECT_ID" 2>/dev/null)" && [[ "$current" == "$value" ]]; then
    ok "${name} up to date"
    return
  fi
  printf '%s' "$value" | gcloud_q secrets versions add "$name" --data-file=- >/dev/null
  ok "${name} new version added"
}

store_slack_secrets() {
  step "Slack secrets"
  [[ -f "$ENV_FILE" ]] || fail "no env file at ${ENV_FILE}. Set ENV_FILE to the file holding SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET."
  local token signing
  token="$(env_value SLACK_BOT_TOKEN)" || fail "SLACK_BOT_TOKEN is missing from ${ENV_FILE}"
  signing="$(env_value SLACK_SIGNING_SECRET)" || fail "SLACK_SIGNING_SECRET is missing from ${ENV_FILE}"
  sync_secret "$SECRET_SLACK_BOT_TOKEN" "$token"
  sync_secret "$SECRET_SLACK_SIGNING_SECRET" "$signing"
}

grant_roles() {
  step "IAM"
  # The webhook stores a request and enqueues a task. It never calls a model.
  grant_project_role "$WEBHOOK_SA" roles/cloudsql.client
  grant_project_role "$WEBHOOK_SA" roles/cloudtasks.enqueuer
  # The worker reads policies, writes results, calls Gemini, and replies.
  grant_project_role "$WORKER_SA" roles/cloudsql.client
  grant_project_role "$WORKER_SA" roles/aiplatform.user
  # Maintenance only touches the database.
  grant_project_role "$MAINTENANCE_SA" roles/cloudsql.client

  # Each identity reads only the secrets it needs. Only the webhook verifies a
  # Slack signature and only the worker posts a reply.
  grant_secret_access "$SECRET_SLACK_SIGNING_SECRET" "$WEBHOOK_SA"
  grant_secret_access "$SECRET_SLACK_BOT_TOKEN" "$WORKER_SA"
  grant_secret_access "$SECRET_DATABASE_URL" "$WEBHOOK_SA"
  grant_secret_access "$SECRET_DATABASE_URL" "$WORKER_SA"
  grant_secret_access "$SECRET_DATABASE_URL" "$MAINTENANCE_SA"
}

summary() {
  step "Done"
  ok "project           ${PROJECT_ID}"
  ok "region            ${REGION}"
  ok "images            ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}"
  ok "cloud sql         ${SQL_INSTANCE} (${SQL_TIER}), database ${SQL_DATABASE}"
  ok "queue             ${TASK_QUEUE} in ${REGION}"
  ok "identities        ${WEBHOOK_SA}, ${WORKER_SA}, ${MAINTENANCE_SA}"
  ok "secrets           ${SECRET_SLACK_BOT_TOKEN}, ${SECRET_SLACK_SIGNING_SECRET}, ${SECRET_DATABASE_URL}"
  printf '\nCloud SQL bills whether or not anything is running.\n'
  printf 'Tear it down when you are finished: scripts/teardown-dev.sh\n'
}

main() {
  require_tools
  printf 'Provisioning %s in %s\n' "$PROJECT_ID" "$REGION"
  enable_apis
  create_service_accounts
  create_artifact_registry
  create_task_queue
  create_sql_instance
  store_slack_secrets
  configure_sql_user_and_url
  grant_roles
  summary
}

main "$@"
