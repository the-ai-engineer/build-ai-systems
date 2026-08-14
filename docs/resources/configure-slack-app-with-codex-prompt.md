# Configure the Slack App With Codex

```text
Configure the Build AI Systems HR Policy Assistant in the signed-in Gradientwork Slack workspace.

Read AGENTS.md, issue #17, slack/manifest.bootstrap.json, slack/manifest.json, and docs/slack-setup.md before acting.
Use the connected browser and inspect https://api.slack.com/apps before creating anything.
Filter by app name and workspace, open possible matches, and compare their non-secret manifests.
Reuse and reconcile an existing matching HR Policy Assistant app.
Do not create a duplicate blindly, and do not alter unrelated apps.

Before a public HTTPS webhook exists, use slack/manifest.bootstrap.json.
The app must have only the app_mentions:read and chat:write bot scopes.
Keep direct messages, the App Home Messages tab, interactive components, shortcuts, slash commands, incoming webhooks, Socket Mode, organization deployment, MCP, and multi-workspace distribution disabled.

Do not enable Events API delivery before a deployed HTTPS /slack/events endpoint can complete Slack's verification challenge.
At that later checkpoint, replace the non-routable placeholder in a local copy of slack/manifest.json, apply it, and confirm app_mention is the only subscribed event.
Never commit a deployed or temporary request URL.

Never reveal, show, copy, transcribe, log, document, screenshot, or commit a signing secret, bot token, OAuth code, configuration token, customer message, member list, or complete event payload.
Do not ask me to paste any credential into chat.
Record only safe team, app, bot-user, support-user-group, and channel identifiers, plus the locations where credentials belong.
Local credentials belong only in the gitignored support_agent_app/.env file.
Deployed credentials belong in Google Secret Manager.

Stop immediately if Slack shows an OAuth consent or workspace installation approval screen.
Describe the requested scopes and ask for my explicit confirmation.
Do not click the approval button yourself.
Also stop immediately before the final Create and Install action unless I have just confirmed that exact workspace change.

After each safe step, re-read the visible UI state instead of relying on memory.
Append only sanitized setup steps, surprising UI details, manual checkpoints, safe identifiers, and verification evidence to MEMORY.md.
If the signed-in Slack state is unavailable, complete all safe repository work and report the exact page and action where an authenticated operator must resume.
```
