# Slack App Setup

This guide configures the single-workspace Slack app for the HR policy assistant.
It was checked against the signed-in Slack app-management UI in the Gradientwork workspace on 14 August 2026.

## Current workspace state

Slack app management currently lists one unrelated app in Gradientwork.
The workspace's safe team ID is `T0B2CKH25KK`.
The unrelated app's manifest has direct-message events, message-history and assistant scopes, interactivity, and Socket Mode.
It is not the course app and must not be renamed, reduced, deleted, or otherwise repurposed.

The installed course app is `HR Policy Assistant`, with safe app ID `A0BQF2X29MF`.
Its installed bot scopes are exactly `app_mentions:read` and `chat:write`, with no user scopes.
App Home messages, interactivity, slash commands, Events API delivery, Socket Mode, and public distribution are off.
Inspect the list again before creating anything because the workspace may have changed since this observation.

## Repository manifests

Use [the bootstrap manifest](../slack/manifest.bootstrap.json) to create the app before a public webhook exists.
It creates the display information and bot user, requests only `app_mentions:read` and `chat:write`, and explicitly disables direct messages, incoming webhooks, interactivity, Socket Mode, organization deployment, and Slack-hosted or MCP features.
It has no event delivery configuration.

[The deployment-stage manifest](../slack/manifest.json) adds the single `app_mention` bot event.
Its `.invalid` request URL is deliberately non-routable and stays that way in Git.
It is replaced with the deployed HTTPS webhook in a rendered copy at the point the manifest is applied, which [Enable event delivery after deployment](#enable-event-delivery-after-deployment) shows.

Slack's current validator requires either a request URL or Socket Mode when a manifest contains bot events.
The two files keep the initial app reproducible without enabling Socket Mode or pretending that a webhook already exists.

## Safe values and secret locations

These identifiers are safe to record as configuration:

- `SLACK_ALLOWED_TEAM_IDS`: the workspace team ID.
- `SLACK_APP_ID`: the app ID shown under **Basic Information**.
- `SLACK_BOT_USER_ID`: the bot member ID available after installation.
- `SLACK_ALLOWED_CHANNEL_IDS`: the dedicated public HR channel ID, when that channel is selected.

Version 1 does not tag a Slack user or user group in human-review replies, so no support-group configuration is required.

These values are credentials and must never be copied into Codex, GitHub, screenshots, shell output, documentation, or `MEMORY.md`:

- `SLACK_SIGNING_SECRET` appears under **Settings → Basic Information → App Credentials**.
- `SLACK_BOT_TOKEN` appears under **Features → OAuth & Permissions → OAuth Tokens** after installation.

For local work, the operator enters those two values directly into the repository root `.env`.
The repository ignores that file through its `.env` rule.
For deployment, create Secret Manager entries such as `slack-signing-secret` and `slack-bot-token`, then enter the values through a secure operator-controlled path.
Do not pass a credential value through an agent command or task message.

## Inspect before creating

1. Open <https://api.slack.com/apps> in the signed-in browser.
2. Filter by `HR Policy Assistant` and `Gradientwork`.
3. If a matching app exists, open **App Manifest** and compare its non-secret configuration with the repository manifests.
4. Reconcile the matching app instead of creating another one.
5. If only unrelated apps exist, leave them unchanged and continue.

The current UI path for a new app is **Your Apps → Create New App → From a manifest → Continue**.
The next screen contains the manifest editor first and the **Workspace** selector beneath it.
Choose **Gradientwork**, select the JSON tab, paste `slack/manifest.bootstrap.json`, and select **Next**.
Review the summary before selecting **Create and Install**.

Creating the app changes workspace state.
A browser agent must stop immediately before **Create and Install** unless the user has just confirmed that exact action.

After creation, record only the app ID and team ID.
Do not open, show, copy, or transcribe credential fields.

## Install the bot

Open the course app, then use **Settings → Install App** or **Features → OAuth & Permissions**.
Select **Install to Workspace** or **Reinstall to Workspace** only after confirming that the requested bot scopes are exactly:

- `app_mentions:read`
- `chat:write`

Slack may then show an OAuth consent or workspace installation approval screen.
The browser agent must stop there and ask the user for explicit confirmation.
It must not approve the installation itself.

After the user completes the approval, the operator stores the displayed bot credential directly in the repository root `.env` without exposing it to the agent.
The operator stores the signing credential from **Basic Information → App Credentials** in the same file.

The current Slack web profile for this installed app does not expose **Copy member ID**.
Do not mistake the direct-message channel ID for the bot user ID.
After the operator stores the bot credential in the repository root `.env`, use Slack's `auth.test` method from a local process that reads the file and prints only the returned `user_id`.
Record that safe identifier as `SLACK_BOT_USER_ID` without printing the credential or the complete API response.

Invite the installed bot to the dedicated test channel with Slack's normal channel invite flow.
This invitation is a separate manual checkpoint because it changes channel membership.

## Enable event delivery after deployment

This is the real route. The tunnel in the README is a local development
convenience and is no longer how this app is connected.

Do not perform this section until the public webhook is deployed at an HTTPS URL
ending in `/slack/events` and can answer Slack's URL-verification challenge.

### Render the manifest without committing the URL

`slack/manifest.json` keeps its non-routable `.invalid` request URL in Git. Only
the rendered copy carries the deployed host, and that copy is never committed.
Derive it from the live service rather than typing it, so the recipe stays
correct across redeploys:

```bash
WEBHOOK_URL="$(gcloud run services describe support-webhook \
  --region europe-west1 --format='value(status.url)')"

sed "s|https://replace-after-deployment.invalid|${WEBHOOK_URL}|" \
  slack/manifest.json > "${TMPDIR:-/tmp}/manifest.rendered.json"
```

The rendered file lands outside the working tree, so there is nothing to
accidentally stage.

### Point Slack at it

1. Open **Features → App Manifest**, paste the rendered manifest, and select **Save Changes**.
2. Alternatively, open **Features → Event Subscriptions**, switch **Enable Events** on, enter the deployed request URL, and wait for Slack to show **Verified**.
3. Under **Subscribe to bot events**, confirm that `app_mention` is the only event.
4. Save the changes.
5. If scopes changed, return to **Install App** and reinstall only after the user approves the OAuth screen.

Slack verifies the URL by posting a signed `url_verification` payload and
expecting the `challenge` value echoed back. The webhook answers that before it
looks at anything else, so a green **Verified** also proves the signing secret in
Secret Manager matches the one in **Basic Information**.

### What must not be committed

Never commit a credential, a complete Slack callback payload, or a temporary
tunnel URL.

The deployed Cloud Run URL is not a credential: the endpoint is public by
necessity and is protected by signature verification, not by being unguessable.
It is deliberately recorded in [the deployment
record](deploying-to-cloud-run.md), which documents one specific deployment.
Keeping it out of `slack/manifest.json` is a different rule with a different
reason: the manifest is a reproducible artifact, and binding it to one
deployment's hostname makes it wrong for every other one.

## Acceptance test: a real mention, nothing running locally

Recorded on 20 August 2026 against the deployed services in
`build-ai-systems-dev`.

Checked against the deployed system, not a local one. The signed probes were
built the way `demos/send_slack_event.py` builds them, reading the signing
secret from Secret Manager on stdin so it never reached a command line.

| Check | Expected | Observed |
|---|---|---|
| Signed `url_verification` | 200, body is the `challenge` verbatim | 200, echoed the 35-character challenge exactly |
| Forged signature | 401, nothing stored | 401 `invalid slack signature` |
| No signature headers at all | 401 | 401 |
| Mention from a non-allowlisted channel | 200, no work created | 200, and the worker logged no request at all |
| The same `event_id` delivered twice | at most one reply | two webhook 200s, exactly one `POST /tasks/process-support-request` |

The duplicate pair is the interesting one. Both deliveries were accepted, and
the second returned in 0.22 seconds against the first's 5.99: it re-derived the
same Cloud Tasks name, the queue refused the second copy, and the webhook
converged instead of creating a second unit of work. The queue drained to zero
and the worker ran once.

The non-allowlisted channel case is deliberately a 200. A retry cannot change
the answer, so telling Slack to stop is the correct response, and the absence of
any worker request is what proves nothing was created.

The reply text itself is confirmed by a human reading the channel. The bot token
holds `app_mentions:read` and `chat:write` and no history scope, so the app
cannot read its own message back, and granting a read scope to verify a
deployment would be a worse trade than looking.

### The real mention: not yet recorded

Every request above was posted directly to the deployed webhook, signed the way
Slack signs one. None of them came from Slack. At the time of writing the
webhook's request log held only these synthetic probes and no Slackbot user
agent, so the last link in the chain, Slack actually delivering an
`app_mention` to the deployed URL, is unproved.

That link is a console setting rather than anything in this repository, and it
is the one thing the deployment cannot make true for itself. When a real mention
produces a cited reply in its own thread with nothing running on a laptop,
record it here: the webhook's request log is where the delivery shows up, and
the Slack thread is where the reply is read.

## Final checks

- **App Home** has its Messages tab disabled, so direct messages are not a supported entry point.
- **Interactivity & Shortcuts** is disabled.
- **Slash Commands** has no commands.
- **OAuth & Permissions** lists only the two bot scopes above and no user scopes.
- **Event Subscriptions** remains off until the verified webhook is connected, then lists only `app_mention`.
- **Socket Mode** is disabled.
- **Manage Distribution** remains off because version 1 supports one workspace.
- Human-review replies require no Slack user-group setup.
- The app can be invited to the dedicated test channel after installation.
- `git check-ignore .env` prints that ignored path.
- The Git diff contains no credential value, complete Slack message, or customer payload.
- `slack/manifest.json` still carries its `.invalid` request URL.

## Reusable browser prompt

The supervised browser procedure is stored in [configure-slack-app-with-codex-prompt.md](resources/configure-slack-app-with-codex-prompt.md).
Use it from a browser-connected Codex task so the agent can inspect the current Slack UI while the operator keeps control of approvals and credential entry.
