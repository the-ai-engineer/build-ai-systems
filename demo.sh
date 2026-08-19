#!/usr/bin/env bash
#
# Run the whole system locally and show every HTTP call it makes.
#
#   ./demo.sh                 deterministic adapters, no credentials needed
#   ./demo.sh --live-model    real Gemini, needs GOOGLE_CLOUD_PROJECT and ADC
#
# This starts the two services and then drives them with plain curl. Every
# command it runs is printed before it runs, so nothing here is a trick you
# could not type yourself.

set -euo pipefail

WORKER_PORT=${WORKER_PORT:-8081}
WEBHOOK_PORT=${WEBHOOK_PORT:-8080}
SIGNING_SECRET=${SLACK_SIGNING_SECRET:-demo-secret}
QUESTION=${QUESTION:-"Can unused annual leave be carried into next year?"}
LIVE_MODEL=""
[[ "${1:-}" == "--live-model" ]] && LIVE_MODEL="1"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { printf '\033[2m$ %s\033[0m\n' "$*"; eval "$*"; }

cleanup() {
  [[ -n "${WORKER_PID:-}" ]] && kill "$WORKER_PID" 2>/dev/null || true
  [[ -n "${WEBHOOK_PID:-}" ]] && kill "$WEBHOOK_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait_for() {
  local url=$1 name=$2
  for _ in $(seq 1 60); do
    curl -s -o /dev/null "$url" && return 0
    sleep 0.5
  done
  echo "$name did not start. See /tmp/$name.log" >&2
  tail -20 "/tmp/$name.log" >&2
  exit 1
}

# Four external systems, chosen independently:
#   Postgres   always real, locally
#   model      real Gemini with --live-model, otherwise a canned one
#   queue      LocalTaskQueue, a thread inside the webhook process
#   Slack      recorded to Postgres, never sent, unless you set SLACK_BOT_TOKEN
export WORKER_SLACK_SINK=${WORKER_SLACK_SINK:-record}
if [[ -n "$LIVE_MODEL" ]]; then
  : "${GOOGLE_CLOUD_PROJECT:?--live-model needs GOOGLE_CLOUD_PROJECT}"
  export WORKER_MODEL_SOURCE=configured
else
  export WORKER_MODEL_SOURCE=fixture
fi

say "1. Schema and policies"
run "uv run apply-migrations"
run "uv run seed-policies"

say "2. Start the two services"
echo "the worker is private, the webhook is public. They share a database and nothing else."
uv run uvicorn support_agent_app.worker.main:create_app --factory --port "$WORKER_PORT" \
  >/tmp/worker.log 2>&1 &
WORKER_PID=$!
SLACK_SIGNING_SECRET="$SIGNING_SECRET" \
SLACK_ALLOWED_TEAM_IDS=T-demo SLACK_ALLOWED_CHANNEL_IDS=C-demo \
WORKER_BASE_URL="http://127.0.0.1:$WORKER_PORT" \
  uv run uvicorn support_agent_app.api.main:create_app --factory --port "$WEBHOOK_PORT" \
  >/tmp/webhook.log 2>&1 &
WEBHOOK_PID=$!
wait_for "http://127.0.0.1:$WORKER_PORT/docs" worker
wait_for "http://127.0.0.1:$WEBHOOK_PORT/docs" webhook
echo "worker  http://127.0.0.1:$WORKER_PORT"
echo "webhook http://127.0.0.1:$WEBHOOK_PORT"

say "3. Call the worker directly"
echo "no Slack, no queue. Store a request, then POST its ID."
REQUEST_ID=$(uv run demo-seed-request --question "$QUESTION" --request-id-only)
echo "stored request $REQUEST_ID"
run "curl -s -i -X POST http://127.0.0.1:$WORKER_PORT/tasks/process-support-request \\
  -H 'X-Worker-Task-Identity: local-development-task' \\
  -H 'Content-Type: application/json' \\
  -d '{\"request_id\":\"$REQUEST_ID\"}' | head -1"
echo "the payload carried a request ID and nothing else. The question stayed in Postgres."

say "4. Reject an unauthenticated task"
run "curl -s -o /dev/null -w 'HTTP %{http_code}\\n' -X POST http://127.0.0.1:$WORKER_PORT/tasks/process-support-request \\
  -H 'Content-Type: application/json' \\
  -d '{\"request_id\":\"$REQUEST_ID\"}'"
echo "401. The worker is private and checks every caller."

say "5. Go through the public webhook, as Slack would"
echo "the only hard part is the signature: an HMAC over the raw body."
CURL_CMD=$(uv run demo-slack-event --print-curl \
  --webhook-url "http://127.0.0.1:$WEBHOOK_PORT" \
  --signing-secret "$SIGNING_SECRET" \
  --question "$QUESTION")
printf '\033[2m$ %s\033[0m\n' "$CURL_CMD"
eval "$CURL_CMD" 2>/dev/null | head -1
echo "the webhook answered without calling a model, then queued the work."

say "6. Reject a forged signature"
FORGED=$(uv run demo-slack-event --print-curl \
  --webhook-url "http://127.0.0.1:$WEBHOOK_PORT" \
  --signing-secret "wrong-secret" \
  --question "$QUESTION")
eval "${FORGED/curl -i/curl -s -o /dev/null -w 'HTTP %{http_code}\\n'}" 2>/dev/null
echo "401, before the body was parsed."

say "7. What the employee would see"
sleep 3
run "psql \"\${DATABASE_URL#postgresql://}\" -tAc \"select a.status, a.outbound_text from support_requests r join outbound_actions a using (request_id) order by a.created_at desc limit 1\" 2>/dev/null || uv run python -c \"
from support_agent_app.settings import WorkerSettings
from psycopg import connect
from psycopg.rows import dict_row
with connect(WorkerSettings.load().database_url, row_factory=dict_row) as c:
    row = c.execute('select a.status, a.outbound_text from support_requests r join outbound_actions a using (request_id) order by a.created_at desc limit 1').fetchone()
print(row['status']); print(row['outbound_text'])\""

say "Done"
echo "logs: /tmp/worker.log /tmp/webhook.log"
