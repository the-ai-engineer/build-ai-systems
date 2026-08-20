#!/usr/bin/env bash
#
# Deploy the two runtimes to Cloud Run, after applying the schema.
#
# One image, four commands. The private worker and the public webhook are two
# Cloud Run services from the same digest, and the schema and policy set arrive
# through two Cloud Run jobs from that same digest.
#
#   scripts/deploy-dev.sh
#   TAG=abc1234 scripts/deploy-dev.sh
#   PROJECT_ID=... REGION=... scripts/deploy-dev.sh
#   scripts/deploy-dev.sh --skip-migrations   services only, schema unchanged
#
# The order is the point. Migrations and policy seeding finish before either
# service exists, so no request can ever reach a schema that is not there
# (ARCHITECTURE rule 7). Then the private worker, then the invoker binding that
# lets exactly one identity call it, then the public webhook that starts the
# traffic.
#
# Each service runs as its own service account and reads only the secrets that
# identity is allowed to read. Nothing here downloads a service-account key.
#
# Safe to run again: every step is a create-or-update, and re-running it with
# the same tag redeploys the same digest.
#
# The resources this deploys onto come from scripts/provision-dev.sh, and the
# image comes from scripts/build-and-push.sh.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJECT_ID="${PROJECT_ID:-build-ai-systems-dev}"
REGION="${REGION:-europe-west1}"
ENV_FILE="${ENV_FILE:-${repo_root}/.env}"

AR_REPOSITORY="${AR_REPOSITORY:-support-agent}"
IMAGE_NAME="${IMAGE_NAME:-support-agent}"
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/${IMAGE_NAME}"

SQL_INSTANCE="${SQL_INSTANCE:-support-agent-dev}"
TASK_QUEUE="${TASK_QUEUE:-support-requests}"

WORKER_SERVICE="${WORKER_SERVICE:-support-worker}"
WEBHOOK_SERVICE="${WEBHOOK_SERVICE:-support-webhook}"
MIGRATE_JOB="${MIGRATE_JOB:-support-migrate}"
SEED_JOB="${SEED_JOB:-support-seed-policies}"

WEBHOOK_SA="support-webhook"
WORKER_SA="support-worker"
MAINTENANCE_SA="support-maintenance"

SECRET_SLACK_BOT_TOKEN="slack-bot-token"
SECRET_SLACK_SIGNING_SECRET="slack-signing-secret"
SECRET_DATABASE_URL="database-url"

# Where the operator files live inside the image. The Dockerfile copies them to
# this path and the jobs below name it, so nothing resolves it by guesswork.
IMAGE_MIGRATIONS_DIR=/srv/migrations
IMAGE_POLICIES_DIR=/srv/policies

# Application defaults come from config.toml. Explicit shell overrides for the
# model, model location, and worker deadline are forwarded in deploy_worker.
# This is the platform request timeout outside the worker's own budget. Cloud
# Run must not cut the request off before the worker records what happened.
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
WORKER_REQUEST_TIMEOUT="${WORKER_REQUEST_TIMEOUT:-120s}"

# A development environment. Bounded so a runaway retry loop cannot bill for a
# hundred instances.
MAX_INSTANCES="${MAX_INSTANCES:-4}"

skip_migrations=false
case "${1:-}" in
  --skip-migrations) skip_migrations=true ;;
  "") ;;
  *) printf 'usage: %s [--skip-migrations]\n' "$0" >&2; exit 2 ;;
esac

step() { printf '\n== %s\n' "$1"; }
ok() { printf '   %s\n' "$1"; }
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }

gcloud_q() { gcloud --project "$PROJECT_ID" --quiet "$@"; }

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "$PROJECT_ID"; }

# Read one KEY=value from ENV_FILE without sourcing it. Only non-secret values
# are read this way; the credentials stay in Secret Manager and are never read
# by this script at all.
env_value() {
  local key="$1" line value
  [[ -f "$ENV_FILE" ]] || return 1
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
  gcloud --quiet auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
    || fail "no active gcloud account. Run: gcloud auth login"
  gcloud --quiet projects describe "$PROJECT_ID" >/dev/null 2>&1 \
    || fail "cannot reach project ${PROJECT_ID}"
}

# A valid Slack signature proves the request came from Slack, not that it came
# from the workspace and channel this deployment serves. Both allowlists are
# required, because an empty one would accept nothing and look like a silent
# deployment bug rather than a refusal.
resolve_allowlists() {
  SLACK_ALLOWED_TEAM_IDS="${SLACK_ALLOWED_TEAM_IDS:-$(env_value SLACK_ALLOWED_TEAM_IDS || true)}"
  SLACK_ALLOWED_CHANNEL_IDS="${SLACK_ALLOWED_CHANNEL_IDS:-$(env_value SLACK_ALLOWED_CHANNEL_IDS || true)}"
  [[ -n "$SLACK_ALLOWED_TEAM_IDS" ]] \
    || fail "SLACK_ALLOWED_TEAM_IDS is required. Set it in the environment or in ${ENV_FILE}."
  [[ -n "$SLACK_ALLOWED_CHANNEL_IDS" ]] \
    || fail "SLACK_ALLOWED_CHANNEL_IDS is required. Set it in the environment or in ${ENV_FILE}."
}

# Deploy the digest, not the tag. A tag can be moved between the two service
# deployments; a digest cannot, so "both services run the same image" stays
# true rather than being a thing this script hoped for.
resolve_image() {
  step "Image"
  local tag digest
  if [[ -n "${IMAGE_DIGEST:-}" ]]; then
    IMAGE="${IMAGE_PATH}@${IMAGE_DIGEST}"
    ok "using ${IMAGE}"
    return
  fi
  # The same rule scripts/build-and-push.sh uses to name what it pushed, so
  # the tag this looks for is the tag that build produced.
  tag="${TAG:-$(default_tag)}"
  digest="$(gcloud --quiet artifacts docker images describe "${IMAGE_PATH}:${tag}" \
    --project "$PROJECT_ID" --format='value(image_summary.digest)' 2>/dev/null || true)"
  [[ -n "$digest" ]] \
    || fail "no image ${IMAGE_PATH}:${tag}. Build and push it with scripts/build-and-push.sh, or set TAG."
  IMAGE="${IMAGE_PATH}@${digest}"
  ok "tag     ${tag}"
  ok "digest  ${digest}"
}

default_tag() {
  local commit suffix=""
  commit="$(git -C "$repo_root" rev-parse --short HEAD)" || fail "not a git repository"
  git -C "$repo_root" diff --quiet HEAD -- || suffix="-dirty"
  printf '%s%s' "$commit" "$suffix"
}

resolve_connection_name() {
  SQL_CONNECTION_NAME="$(gcloud --quiet sql instances describe "$SQL_INSTANCE" \
    --project "$PROJECT_ID" --format='value(connectionName)' 2>/dev/null || true)"
  [[ -n "$SQL_CONNECTION_NAME" ]] \
    || fail "Cloud SQL instance ${SQL_INSTANCE} not found. Run scripts/provision-dev.sh first."
}

service_url() {
  gcloud --quiet run services describe "$1" --region "$REGION" --project "$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null || true
}

# The worker's OIDC audience is its own URL, and a service has no URL until it
# has been created once. Cloud Run's default hostname is derived from the
# service name and the project number, so the first deploy can be told what its
# own URL will be; every later deploy reads the real one. `verify_worker_url`
# below checks the prediction against what Cloud Run actually issued rather
# than trusting the format.
predict_worker_url() {
  local project_number
  project_number="$(gcloud --quiet projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  printf 'https://%s-%s.%s.run.app' "$WORKER_SERVICE" "$project_number" "$REGION"
}

# --- schema, before anything can serve -------------------------------------

# Two jobs rather than one, because they are two operator actions with two
# different reasons to fail: a migration is schema and seeding is content.
# Both run as support-maintenance, whose only project role is cloudsql.client.
# It cannot invoke the worker, post to Slack, or enqueue a task.
run_operator_job() {
  local job="$1" command="$2"
  shift 2
  local args
  args="$(IFS=,; printf '%s' "$*")"
  ok "${job}: ${command} $*"
  # --args= with an equals sign, not a space. The value starts with "--", and
  # gcloud reads a space-separated value that begins with a dash as a flag of
  # its own.
  gcloud_q run jobs deploy "$job" \
    --region "$REGION" \
    --image "$IMAGE" \
    --service-account "$(sa_email "$MAINTENANCE_SA")" \
    --set-cloudsql-instances "$SQL_CONNECTION_NAME" \
    --set-secrets "DATABASE_URL=${SECRET_DATABASE_URL}:latest" \
    --command "$command" \
    --args="$args" \
    --max-retries 0 \
    --task-timeout 10m \
    --execute-now \
    --wait >/dev/null
  ok "${job}: done"
}

apply_schema() {
  step "Schema and policies, before any traffic"
  if [[ "$skip_migrations" == true ]]; then
    ok "--skip-migrations: nothing applied"
    ok "only use this when the schema and the policy set are already current"
    return
  fi
  run_operator_job "$MIGRATE_JOB" apply-migrations --migrations-dir "$IMAGE_MIGRATIONS_DIR"
  run_operator_job "$SEED_JOB" seed-policies \
    --migrations-dir "$IMAGE_MIGRATIONS_DIR" \
    --policies-dir "$IMAGE_POLICIES_DIR"
}

# --- the private worker -----------------------------------------------------

deploy_worker() {
  step "Private worker"
  local name value worker_env url
  url="$(service_url "$WORKER_SERVICE")"
  if [[ -n "$url" ]]; then
    ok "existing url ${url}"
  else
    url="$(predict_worker_url)"
    ok "first deploy, expecting ${url}"
  fi

  worker_env="WORKER_BASE_URL=${url};TASK_OIDC_SERVICE_ACCOUNT=$(sa_email "$WEBHOOK_SA");GOOGLE_CLOUD_PROJECT=${PROJECT_ID};GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}"
  for name in SUPPORT_AGENT_MODEL WORKER_DEADLINE_SECONDS; do
    value="${!name:-}"
    if [[ -n "$value" ]]; then
      worker_env="${worker_env};${name}=${value}"
    fi
  done

  # WORKER_BASE_URL is one value used twice: the audience Cloud Tasks puts in
  # the token, and the audience this worker accepts. One variable, so the two
  # cannot drift apart.
  #
  # "^;^" changes the separator gcloud splits the variable list on. The default
  # is a comma, which is also what the Slack allowlists use, and an "@" would
  # split a service-account email in half.
  gcloud_q run deploy "$WORKER_SERVICE" \
    --region "$REGION" \
    --image "$IMAGE" \
    --service-account "$(sa_email "$WORKER_SA")" \
    --no-allow-unauthenticated \
    --ingress all \
    --port 8080 \
    --command uvicorn \
    --args="support_agent_app.worker.main:create_app,--factory,--host,0.0.0.0,--port,8080" \
    --set-cloudsql-instances "$SQL_CONNECTION_NAME" \
    --set-secrets "DATABASE_URL=${SECRET_DATABASE_URL}:latest,SLACK_BOT_TOKEN=${SECRET_SLACK_BOT_TOKEN}:latest" \
    --set-env-vars "^;^${worker_env}" \
    --timeout "$WORKER_REQUEST_TIMEOUT" \
    --max-instances "$MAX_INSTANCES" \
    --min-instances 0 >/dev/null

  WORKER_URL="$(service_url "$WORKER_SERVICE")"
  [[ -n "$WORKER_URL" ]] || fail "${WORKER_SERVICE} deployed but reported no URL"
  verify_worker_url "$url"
  ok "worker  ${WORKER_URL}"
}

# The audience is exact. A worker configured with a URL that is not its own
# rejects every task with a 401, and it rejects them in a way that looks like a
# broken IAM binding, so the mismatch is caught here instead.
verify_worker_url() {
  local used="$1"
  if [[ "${WORKER_URL%/}" == "${used%/}" ]]; then
    return
  fi
  ok "Cloud Run issued ${WORKER_URL}, not the predicted ${used}"
  ok "correcting WORKER_BASE_URL and redeploying the worker"
  gcloud_q run services update "$WORKER_SERVICE" \
    --region "$REGION" \
    --update-env-vars "WORKER_BASE_URL=${WORKER_URL}" >/dev/null
}

# The worker is private in two independent ways. This is the first: Cloud Run
# refuses a caller with no run.invoker binding before the request reaches the
# process. The second is in worker/auth.py, which checks which identity signed
# the token. A widened binding does not by itself open the worker.
configure_invoker() {
  step "Who may invoke the worker"
  local role=roles/run.invoker member
  member="serviceAccount:$(sa_email "$WEBHOOK_SA")"
  if has_run_binding "$role" "$member"; then
    ok "${WEBHOOK_SA} can already invoke ${WORKER_SERVICE}"
  else
    gcloud_q run services add-iam-policy-binding "$WORKER_SERVICE" \
      --region "$REGION" --member "$member" --role "$role" --condition None >/dev/null
    ok "${WEBHOOK_SA} -> invoke ${WORKER_SERVICE}"
  fi

  local public
  for public in allUsers allAuthenticatedUsers; do
    if has_run_binding "$role" "$public"; then
      gcloud_q run services remove-iam-policy-binding "$WORKER_SERVICE" \
        --region "$REGION" --member "$public" --role "$role" >/dev/null
      ok "removed ${public}: the worker is private and that is not a setting"
    fi
  done
  ok "no unauthenticated invoker on ${WORKER_SERVICE}"
}

webhook_is_public() {
  gcloud --quiet run services get-iam-policy "$WEBHOOK_SERVICE" \
    --region "$REGION" --project "$PROJECT_ID" \
    --flatten='bindings[].members' \
    --filter='bindings.role=roles/run.invoker AND bindings.members=allUsers' \
    --format='value(bindings.members)' 2>/dev/null | grep -q .
}

has_run_binding() {
  local role="$1" member="$2"
  gcloud --quiet run services get-iam-policy "$WORKER_SERVICE" \
    --region "$REGION" --project "$PROJECT_ID" \
    --flatten='bindings[].members' \
    --filter="bindings.role=${role} AND bindings.members=${member}" \
    --format='value(bindings.members)' 2>/dev/null | grep -q .
}

# --- the public webhook, last ----------------------------------------------

deploy_webhook() {
  step "Public webhook"
  # It holds the signing secret and not the bot token, because it verifies a
  # Slack signature and never posts a reply. Only the worker does that.
  gcloud_q run deploy "$WEBHOOK_SERVICE" \
    --region "$REGION" \
    --image "$IMAGE" \
    --service-account "$(sa_email "$WEBHOOK_SA")" \
    --allow-unauthenticated \
    --port 8080 \
    --command uvicorn \
    --args="support_agent_app.api.main:create_app,--factory,--host,0.0.0.0,--port,8080" \
    --set-cloudsql-instances "$SQL_CONNECTION_NAME" \
    --set-secrets "DATABASE_URL=${SECRET_DATABASE_URL}:latest,SLACK_SIGNING_SECRET=${SECRET_SLACK_SIGNING_SECRET}:latest" \
    --set-env-vars "^;^TASK_QUEUE_BACKEND=cloud-tasks;TASK_QUEUE_NAME=${TASK_QUEUE};TASK_QUEUE_LOCATION=${REGION};GOOGLE_CLOUD_PROJECT=${PROJECT_ID};TASK_OIDC_SERVICE_ACCOUNT=$(sa_email "$WEBHOOK_SA");WORKER_BASE_URL=${WORKER_URL};SLACK_ALLOWED_TEAM_IDS=${SLACK_ALLOWED_TEAM_IDS};SLACK_ALLOWED_CHANNEL_IDS=${SLACK_ALLOWED_CHANNEL_IDS}" \
    --timeout 30s \
    --max-instances "$MAX_INSTANCES" \
    --min-instances 0 >/dev/null

  WEBHOOK_URL="$(service_url "$WEBHOOK_SERVICE")"
  [[ -n "$WEBHOOK_URL" ]] || fail "${WEBHOOK_SERVICE} deployed but reported no URL"

  # gcloud reports a refused public binding as a warning and still exits 0, and
  # a webhook Slack cannot reach is not a deployment. Check it rather than
  # reading the output.
  if ! webhook_is_public; then
    fail "${WEBHOOK_SERVICE} deployed but allUsers cannot invoke it, so Slack cannot deliver to it.
An organization policy on constraints/iam.allowedPolicyMemberDomains usually causes this.
docs/deploying-to-cloud-run.md has the exception this project uses."
  fi
  ok "webhook ${WEBHOOK_URL}"
}

summary() {
  step "Done"
  ok "image      ${IMAGE}"
  ok "webhook    ${WEBHOOK_URL}   public, runs as ${WEBHOOK_SA}"
  ok "worker     ${WORKER_URL}   private, runs as ${WORKER_SA}"
  ok "jobs       ${MIGRATE_JOB}, ${SEED_JOB}, run as ${MAINTENANCE_SA}"
  ok "queue      ${TASK_QUEUE} in ${REGION}"
  printf '\nSlack event URL: %s/slack/events\n' "$WEBHOOK_URL"
  printf 'Prove a task flows end to end: docs/deploying-to-cloud-run.md\n'
}

main() {
  require_tools
  resolve_allowlists
  printf 'Deploying to %s in %s\n' "$PROJECT_ID" "$REGION"
  resolve_image
  resolve_connection_name
  apply_schema
  deploy_worker
  configure_invoker
  deploy_webhook
  summary
}

main
