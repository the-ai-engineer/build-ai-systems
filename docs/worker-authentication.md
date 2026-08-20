# Proving the worker is private

The worker accepts a Google-signed OIDC token from exactly one service account.
This is how to see that for yourself, and what the checks were when this was
written.

The token is the second lock. The first is Cloud Run's own `run.invoker`
binding, which `scripts/provision-dev.sh` grants to `support-webhook` on the
worker service and to nobody else. The token check is the one that says *which*
identity, and it keeps holding if a binding is ever widened by mistake.

## Run the worker the way it is deployed

Locally, with the deployed identity check rather than the local one. The
audience is the worker's own base URL, because that is what `api/task_queue.py`
puts in the token Cloud Tasks mints:

```bash
DATABASE_URL="postgresql:///support_agent" \
WORKER_MODEL_SOURCE=fixture WORKER_SLACK_SINK=record \
WORKER_TASK_AUTH=google-oidc \
WORKER_BASE_URL=http://127.0.0.1:8099 \
TASK_OIDC_SERVICE_ACCOUNT=support-webhook@build-ai-systems-dev.iam.gserviceaccount.com \
  uv run uvicorn support_agent_app.worker.main:create_app --factory --port 8099

# in another terminal, store a request to process
REQUEST_ID=$(DATABASE_URL="postgresql:///support_agent" \
  uv run demo-seed-request --question "Can unused annual leave be carried into next year?" \
  --request-id-only)
```

## The unauthorized calls

Three ways to arrive without a valid identity. All three are a 401, raised
before the worker reads the request row or claims anything:

```bash
# no token at all
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST \
  http://127.0.0.1:8099/tasks/process-support-request \
  -H 'Content-Type: application/json' -d "{\"request_id\":\"$REQUEST_ID\"}"

# the local shared string, which a deployed worker does not read
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST \
  http://127.0.0.1:8099/tasks/process-support-request \
  -H 'X-Worker-Task-Identity: local-development-task' \
  -H 'Content-Type: application/json' -d "{\"request_id\":\"$REQUEST_ID\"}"

# a forged bearer token: correctly shaped, not signed by Google
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST \
  http://127.0.0.1:8099/tasks/process-support-request \
  -H 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImZvcmdlZCJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20ifQ.not-a-signature' \
  -H 'Content-Type: application/json' -d "{\"request_id\":\"$REQUEST_ID\"}"
```

Recorded output:

```
HTTP 401
HTTP 401
HTTP 401
```

## The authorized call

Google mints the token, for the same service account Cloud Tasks uses and the
same audience it would set. Impersonating that account needs
`roles/iam.serviceAccountTokenCreator` on it, which is an operator's grant and
not something the application holds:

```bash
TOKEN=$(gcloud auth print-identity-token \
  --impersonate-service-account=support-webhook@build-ai-systems-dev.iam.gserviceaccount.com \
  --audiences=http://127.0.0.1:8099 \
  --include-email)

curl -s -w '\nHTTP %{http_code}\n' -X POST \
  http://127.0.0.1:8099/tasks/process-support-request \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"request_id\":\"$REQUEST_ID\"}"
```

The token's claims are the ones the worker checks:

```json
{
  "iss": "https://accounts.google.com",
  "aud": "http://127.0.0.1:8099",
  "email": "support-webhook@build-ai-systems-dev.iam.gserviceaccount.com",
  "email_verified": true
}
```

Recorded output:

```
{"request_id":"a6b1dec8-4ca2-4cce-9243-e4b8032308f7","outcome":"completed","send_attempted":true}
HTTP 200
```

## The same token, for somewhere else

Ask Google for a token that is just as genuine and carries a different
audience, and the worker refuses it. This is the check that stops a token
minted for one service being replayed against another:

```bash
OTHER=$(gcloud auth print-identity-token \
  --impersonate-service-account=support-webhook@build-ai-systems-dev.iam.gserviceaccount.com \
  --audiences=https://another-service.example \
  --include-email)

curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST \
  http://127.0.0.1:8099/tasks/process-support-request \
  -H "Authorization: Bearer $OTHER" \
  -H 'Content-Type: application/json' -d "{\"request_id\":\"$REQUEST_ID\"}"
```

Recorded output:

```
HTTP 401
```

A token minted for a different service account is refused the same way, by the
email check rather than the audience one. Proving that live needs
`serviceAccountTokenCreator` on a second account, so it is covered in
`tests/unit/worker/test_worker_auth.py` instead.

## What a test can and cannot show

`tests/unit/worker/test_worker_auth.py` covers every rejection through an
injected verifier, so the suite needs no Google Cloud project, credentials, or
network. What it deliberately cannot show is that a real Google token verifies,
because the only honest way to prove that is to ask Google for one. That is the
run above.
