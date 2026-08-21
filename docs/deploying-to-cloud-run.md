# Deploying to Cloud Run

Two services and two jobs, all from one image. This is what
`scripts/deploy-dev.sh` does, why it does it in that order, and the recorded
proof that a task really flows from Slack to a reply with nothing running on a
laptop.

The ground it deploys onto comes from `scripts/provision-dev.sh`, and the image
comes from `scripts/build-and-push.sh`. Neither is repeated here.

## One command

```bash
scripts/build-and-push.sh
SLACK_ALLOWED_TEAM_IDS=T0B2CKH25KK \
SLACK_ALLOWED_CHANNEL_IDS=C0BQJ8U1Z5X \
  scripts/deploy-dev.sh
```

The two allowlists are the only values the script needs and cannot infer. They
are identifiers, not secrets, so they come from the environment or `.env`.
Every credential stays in Secret Manager and is mounted by name; the script
never reads one.

## What it deploys, in this order

| Order | What | Identity | Why here |
|---|---|---|---|
| 1 | `support-migrate` job | `support-maintenance` | Schema before anything can serve (ARCHITECTURE rule 7) |
| 2 | `support-seed-policies` job | `support-maintenance` | The agent has nothing to cite until this runs |
| 3 | `support-worker` service | `support-worker` | Private. Nothing can reach it yet |
| 4 | `run.invoker` binding | — | Exactly one identity may call the worker |
| 5 | `support-webhook` service | `support-webhook` | Public. This is what starts the traffic |

The order is the deployment's only real safety property. Both jobs finish
before either service exists, so there is no window in which a request can
arrive at a schema that is not there. `--skip-migrations` exists for a redeploy
that changes no schema, and skipping is a decision the operator makes out loud.

Two jobs rather than one, because a migration failing and a seed failing are
different problems. Both run as `support-maintenance`, whose only project role
is `cloudsql.client`: it cannot invoke the worker, enqueue a task, or post to
Slack.

Migrations and policies live in the image at `/srv/migrations` and
`/srv/policies`, and the jobs name those paths. Neither runtime reads them.
`apply-migrations` and `seed-policies` take the directory as an argument rather
than resolving it relative to the installed package, because inside the image
that resolution lands somewhere inside the virtual environment.

## The identities

No key is downloaded anywhere in this system. Each runtime is a Cloud Run
service account and the platform hands it credentials.

| Service | Runs as | Reads | Can do |
|---|---|---|---|
| `support-webhook` | `support-webhook` | `slack-signing-secret`, `database-url` | Store a request, create a task, act as itself to mint the task's token |
| `support-worker` | `support-worker` | `slack-bot-token`, `database-url` | Read policies, call Gemini, post one reply |
| jobs | `support-maintenance` | `database-url` | Change the schema and the policy set |

The webhook cannot post to Slack and the worker cannot enqueue a task. That is
the same split the code makes, enforced by IAM rather than by intention.

The worker calls Gemini through its own runtime identity: `roles/aiplatform.user`
and nothing more. There is no model API key in Secret Manager, in the image, or
in either service's environment. `GOOGLE_CLOUD_PROJECT` and
`GOOGLE_CLOUD_LOCATION` say where; Application Default Credentials say who.

## The audience problem

`WORKER_BASE_URL` is one value used twice: the audience Cloud Tasks writes into
the token, and the audience the worker will accept. They must be the same
string, so the script sets one variable on both services.

A service has no URL until it exists, so the first deploy has to be told what
its own URL will be. The script predicts the default Cloud Run hostname from
the service name and project number, deploys, then reads the URL Cloud Run
actually issued and corrects the variable if the two differ. That correction is
not decoration; on the first deploy here they *did* differ:

```
   first deploy, expecting https://support-worker-87550339822.europe-west1.run.app
   Cloud Run issued https://support-worker-rus5pevnnq-ew.a.run.app, not the predicted ...
   correcting WORKER_BASE_URL and redeploying the worker
```

Cloud Run serves this service on both hostnames. Only one of them can be the
audience, and a worker holding the other rejects every task with a 401 that
looks exactly like a broken IAM binding. Reading the URL back is what stops
that from being a debugging session.

## Proof: one task, end to end

Recorded on 20 August 2026, against
`support-agent@sha256:5b76b165…` in `build-ai-systems-dev`, the digest the two
services are running now.

Nothing ran locally except the thing standing in for Slack. Until this run
nothing had exercised Cloud Tasks in the deployed system at all: #51 ran the
webhook against the local queue and #52 tested the adapter in unit tests.

### The queue delivers and the worker checks who called

First with no application work attached, so a failure could only be identity.
One task, created by hand, carrying a request ID that does not exist:

```bash
gcloud tasks create-http-task --queue=support-requests --location=europe-west1 \
  --url="https://support-worker-rus5pevnnq-ew.a.run.app/tasks/process-support-request" \
  --method=POST --header="Content-Type: application/json" \
  --body-content='{"request_id": "2934d48e-2197-4175-ac0a-61412f7a9065"}' \
  --oidc-service-account-email=support-webhook@build-ai-systems-dev.iam.gserviceaccount.com \
  --oidc-token-audience="https://support-worker-rus5pevnnq-ew.a.run.app"
```

```
POST /tasks/process-support-request   404   1.503s
```

A 404 is the good answer. It is raised by the route, which means the request
got past Cloud Run's `run.invoker` check and past the worker's own token check:
Google signed it, the audience matched, and the verified email was the one
service account allowed to enqueue work. The only thing missing was the request
row, because there was not one.

The same worker, called without a credential:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://support-worker-rus5pevnnq-ew.a.run.app/tasks/process-support-request \
  -H 'Content-Type: application/json' -d '{"request_id":"00000000-0000-0000-0000-000000000000"}'
```

```
403
```

Cloud Run refused it before the container saw it. The 401 the application would
have raised is a second lock, unit-tested in `tests/unit/worker/test_worker_auth.py`
and demonstrated in `docs/worker-authentication.md`.

### The whole path

Then one signed `app_mention` posted to the public webhook, standing in for
Slack itself, asking a question the policy set can answer. Team `T0B2CKH25KK`,
channel `C0BQJ8U1Z5X`. A message posted first with the bot token gives the
worker a real thread to reply into, since Slack rejects a reply to a
`thread_ts` that was never a message.

`app/support_agent_app/demos/send_slack_event.py` builds exactly this request,
and `--print-curl` prints it instead of sending it. It wants `DATABASE_URL`
because it then watches Postgres for the outcome, which a laptop cannot reach
here: the deployed database is on a Cloud SQL socket. Give it any URL to see the
curl, and read the outcome from the logs below instead.

```
thread root ts 1787226362.810969
event_id Ev-deploy-1826f924-6a4f-4fd9-9198-59630a2b2882
webhook responded 200
```

The logs, both services:

```
support-webhook  POST /slack/events                     200   0.555s
support-worker   POST /tasks/process-support-request    200  10.584s
```

And in the Slack thread, a reply citing the annual leave policy.

Six things are proved by those two lines and that reply, and none of them had
been proved before:

1. The public webhook accepts a Slack-signed request and answers in 0.555
   seconds, comfortably inside Slack's three second window.
2. It called no model and read no policy to do it (INV-2): the ten seconds are
   all on the other service.
3. Cloud Tasks accepted the task and delivered it, minting a token for
   `support-webhook`.
4. The `run.invoker` binding let that identity through to a private service.
5. The worker verified the token, and the audience it verified against is the
   URL the queue used.
6. The worker read policies from Cloud SQL, called Gemini as
   `support-worker@…` with no API key, and posted a real reply with the bot
   token only it can read.

An unsigned request to the same public URL is a 401, raised before the body is
parsed:

```
support-webhook  POST /slack/events   401   2.749s
```

Nearly all of that is a cold start: the service had scaled to zero and this
request paid for the instance. A warm rejection is single-digit milliseconds.

### What the proof does not cover

The current deployment contract requires `app_mentions:read`, `chat:write`, and
`reactions:write` and still grants no message-history or reaction-read scope.
This recorded proof predates the acknowledgement reaction, so its bot token held
only the first two scopes. The reply was confirmed by a human looking at the
channel rather than by reading it back over the API. Granting a history scope
to verify a deployment would be a worse trade than looking.

The mention was synthetic. A real Slack delivery additionally depends on the
Slack app's event URL pointing at
`https://support-webhook-rus5pevnnq-ew.a.run.app/slack/events`, which is a
console setting and not something this script can make true.

Application `logger.info` lines do not reach Cloud Logging, because uvicorn
does not configure the root logger and nothing else does either. The evidence
above is Cloud Run's own request logs. Nothing is lost that matters for
correctness, since complete message text is deliberately never logged (INV-9)
and Postgres is the durable record, but "accepted request `<id>`" would be
worth having.

## One thing the script cannot do for you

`--allow-unauthenticated` failed the first time:

```
FAILED_PRECONDITION: One or more users named in the policy do not belong to a
permitted customer, perhaps due to an organization policy.
```

The organization enforces `constraints/iam.allowedPolicyMemberDomains`, which
forbids `allUsers` in any IAM policy. A Slack webhook has to be reachable by
Slack, which presents no Google identity, so this project holds an explicit
exception:

```bash
gcloud services enable orgpolicy.googleapis.com --project build-ai-systems-dev

cat > /tmp/allow-public-invoker.yaml <<'YAML'
name: projects/87550339822/policies/iam.allowedPolicyMemberDomains
spec:
  inheritFromParent: false
  rules:
  - allowAll: true
YAML
gcloud org-policies set-policy /tmp/allow-public-invoker.yaml --project build-ai-systems-dev
```

The binding is refused for a minute or so after that, while the policy
propagates. `scripts/deploy-dev.sh` then makes the webhook public itself.

This is an operator decision, made once and knowingly, which is why it is here
and not inside the deploy script. It applies to the whole project, not to one
service: the constraint has no per-resource form. The worker stays private
regardless, and the script removes `allUsers` and `allAuthenticatedUsers` from
the worker on every run, because a public worker is not a configuration this
system offers.

## Redeploying

Run the same command again. Every step is a create-or-update, the deployment
names an image digest rather than a tag, and both services get the same digest,
so "the webhook and the worker are the same build" is a fact rather than a
hope.

Cloud SQL bills whether or not anything is running. `scripts/teardown-dev.sh`
removes the billable parts.
