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
Its `.invalid` request URL is deliberately non-routable and must be replaced with the deployed HTTPS webhook before the manifest is applied.

Slack's current validator requires either a request URL or Socket Mode when a manifest contains bot events.
The two files keep the initial app reproducible without enabling Socket Mode or pretending that a webhook already exists.

## Safe values and secret locations

These identifiers are safe to record as configuration:

- `SLACK_ALLOWED_TEAM_IDS`: the workspace team ID.
- `SLACK_APP_ID`: the app ID shown under **Basic Information**.
- `SLACK_BOT_USER_ID`: the bot member ID available after installation.
- `SLACK_HR_USER_GROUP_ID`: the configured HR support user-group ID.
- `SLACK_ALLOWED_CHANNEL_IDS`: the dedicated public HR channel ID, when that channel is selected.

These values are credentials and must never be copied into Codex, GitHub, screenshots, shell output, documentation, or `MEMORY.md`:

- `SLACK_SIGNING_SECRET` appears under **Settings → Basic Information → App Credentials**.
- `SLACK_BOT_TOKEN` appears under **Features → OAuth & Permissions → OAuth Tokens** after installation.

For local work, the operator enters those two values directly into `support_agent_app/.env`.
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

After the user completes the approval, the operator stores the displayed bot credential directly in `support_agent_app/.env` without exposing it to the agent.
The operator stores the signing credential from **Basic Information → App Credentials** in the same file.

The current Slack web profile for this installed app does not expose **Copy member ID**.
Do not mistake the direct-message channel ID for the bot user ID.
After the operator stores the bot credential in `support_agent_app/.env`, use Slack's `auth.test` method from a local process that reads the file and prints only the returned `user_id`.
Record that safe identifier as `SLACK_BOT_USER_ID` without printing the credential or the complete API response.

To find the support user-group ID, open the workspace administration page, choose **People → User groups**, open the intended HR support group, and copy the ID from its details or URL.
Do not record the group's membership.
Record only the safe identifier as `SLACK_HR_USER_GROUP_ID`.

On 14 August 2026, Gradientwork's **People → User groups** page showed **See paid subscriptions** and no user-group records.
The course workspace therefore has no support user-group ID to record yet.
Do not invent an ID or substitute a person.
Create or select the HR support group only after the workspace supports user groups, then record its safe ID through the path above.

Invite the installed bot to the dedicated test channel with Slack's normal channel invite flow.
This invitation is a separate manual checkpoint because it changes channel membership.

## Enable event delivery after deployment

Do not perform this section until the public webhook is deployed at an HTTPS URL ending in `/slack/events` and can answer Slack's URL-verification challenge.

1. Replace the `.invalid` request URL in `slack/manifest.json` with the deployed HTTPS endpoint in a local, uncommitted copy.
2. Open **Features → App Manifest**, paste that rendered manifest, and select **Save Changes**.
3. Alternatively, open **Features → Event Subscriptions**, switch **Enable Events** on, enter the deployed request URL, and wait for Slack to show **Verified**.
4. Under **Subscribe to bot events**, confirm that `app_mention` is the only event.
5. Save the changes.
6. If scopes changed, return to **Install App** and reinstall only after the user approves the OAuth screen.

Never commit the deployed service URL, temporary tunnel URL, or a complete Slack callback payload.

## Final checks

- **App Home** has its Messages tab disabled, so direct messages are not a supported entry point.
- **Interactivity & Shortcuts** is disabled.
- **Slash Commands** has no commands.
- **OAuth & Permissions** lists only the two bot scopes above and no user scopes.
- **Event Subscriptions** remains off until the verified webhook is connected, then lists only `app_mention`.
- **Socket Mode** is disabled.
- **Manage Distribution** remains off because version 1 supports one workspace.
- **People → User groups** exposes a real HR support group and its ID before human-review replies are enabled.
- The app can be invited to the dedicated test channel after installation.
- `git check-ignore support_agent_app/.env` prints that ignored path.
- The Git diff contains no credential value, complete Slack message, or customer payload.

## Reusable browser prompt

The supervised browser procedure is stored in [configure-slack-app-with-codex-prompt.md](resources/configure-slack-app-with-codex-prompt.md).
Use it from a browser-connected Codex task so the agent can inspect the current Slack UI while the operator keeps control of approvals and credential entry.
