#!/usr/bin/env bash
#
# Delete the billable parts of the development environment.
#
#   scripts/teardown-dev.sh            # asks before deleting anything
#   scripts/teardown-dev.sh --yes      # no prompt
#   scripts/teardown-dev.sh --dry-run  # show what would go, delete nothing
#
# Cloud SQL goes first, because it is the only resource that bills while
# nothing is running and it is the slowest to delete.
#
# What this deliberately leaves behind:
#
#   The Cloud Tasks queue is paused, not deleted. Cloud Tasks reserves a
#   deleted queue name for about seven days, so deleting it would stop
#   provision-dev.sh from rebuilding the environment. A paused, empty queue
#   costs nothing.
#
#   The three service accounts and the enabled APIs stay. Neither costs money,
#   and a deleted service account leaves stale IAM bindings behind it.
#
# Cloud SQL reserves a deleted instance name for about a week too. Set
# SQL_INSTANCE if you need to rebuild sooner than that.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-build-ai-systems-dev}"
REGION="${REGION:-europe-west1}"
AR_REPOSITORY="${AR_REPOSITORY:-support-agent}"
SQL_INSTANCE="${SQL_INSTANCE:-support-agent-dev}"
TASK_QUEUE="${TASK_QUEUE:-support-requests}"
SECRETS=(slack-bot-token slack-signing-secret database-url)

assume_yes=false
dry_run=false
for arg in "$@"; do
  case "$arg" in
    --yes|-y) assume_yes=true ;;
    --dry-run) dry_run=true ;;
    *) printf 'error: unknown option %s\n' "$arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n== %s\n' "$1"; }
ok() { printf '   %s\n' "$1"; }
fail() { printf 'error: %s\n' "$1" >&2; exit 1; }

gcloud_q() {
  $dry_run && return 0
  gcloud --project "$PROJECT_ID" --quiet "$@"
}

# Says what happened, or what would have happened under --dry-run.
did() {
  if $dry_run; then
    ok "would ${1}"
  else
    ok "$2"
  fi
}

command -v gcloud >/dev/null 2>&1 || fail "gcloud is not installed"
gcloud --quiet projects describe "$PROJECT_ID" >/dev/null 2>&1 || fail "cannot reach project ${PROJECT_ID}"

printf 'Tearing down %s in %s\n' "$PROJECT_ID" "$REGION"
if ! $assume_yes && ! $dry_run; then
  printf 'This deletes the Cloud SQL instance %s and its data. Type the project id to confirm: ' "$SQL_INSTANCE"
  read -r reply
  [[ "$reply" == "$PROJECT_ID" ]] || fail "not confirmed, nothing deleted"
fi

step "Cloud SQL"
if gcloud --quiet sql instances describe "$SQL_INSTANCE" --project "$PROJECT_ID" >/dev/null 2>&1; then
  $dry_run || ok "deleting ${SQL_INSTANCE}, this takes a few minutes"
  gcloud_q sql instances delete "$SQL_INSTANCE" >/dev/null
  did "delete ${SQL_INSTANCE} and its data" "${SQL_INSTANCE} deleted"
else
  ok "${SQL_INSTANCE} is already gone"
fi

step "Artifact Registry"
if gcloud --quiet artifacts repositories describe "$AR_REPOSITORY" \
    --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud_q artifacts repositories delete "$AR_REPOSITORY" --location "$REGION" >/dev/null
  did "delete ${AR_REPOSITORY}" "${AR_REPOSITORY} deleted"
else
  ok "${AR_REPOSITORY} is already gone"
fi

step "Secret Manager"
for secret in "${SECRETS[@]}"; do
  if gcloud --quiet secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud_q secrets delete "$secret" >/dev/null
    did "delete ${secret}" "${secret} deleted"
  else
    ok "${secret} is already gone"
  fi
done

step "Cloud Tasks"
state="$(gcloud --quiet tasks queues describe "$TASK_QUEUE" --location "$REGION" \
  --project "$PROJECT_ID" --format='value(state)' 2>/dev/null || true)"
if [[ -z "$state" ]]; then
  ok "${TASK_QUEUE} does not exist"
elif [[ "$state" == "PAUSED" ]]; then
  ok "${TASK_QUEUE} is already paused"
else
  gcloud_q tasks queues purge "$TASK_QUEUE" --location "$REGION" >/dev/null
  gcloud_q tasks queues pause "$TASK_QUEUE" --location "$REGION" >/dev/null
  did "purge and pause ${TASK_QUEUE}" "${TASK_QUEUE} purged and paused"
fi

step "Done"
ok "service accounts and enabled APIs were left in place, they cost nothing"
ok "run scripts/provision-dev.sh to build the environment again"
