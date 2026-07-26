from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from support_agent_app.config import APP_ENV_PATH
from support_agent_app.integrations.slack import post_slack_message, verify_slack_signature
from support_agent_app.services.support_processor import process_support_email

load_dotenv(APP_ENV_PATH)


class SupportEmailRequest(BaseModel):
    sender: str
    subject: str
    body: str


class SupportEmailResponse(BaseModel):
    label: str
    reason: str
    document_id: str | None
    draft_reply: str | None


app = FastAPI(title="AI Architect Support Agent")
slack_app = FastAPI(title="AI Architect Slack Bot")
SLACK_MENTION = re.compile(r"<@[A-Z0-9]+>\s*")


@app.get("/health")
@slack_app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/support-email", response_model=SupportEmailResponse)
def support_email(request: SupportEmailRequest) -> SupportEmailResponse:
    result = process_support_email(request.body)
    return SupportEmailResponse(
        label=result.label,
        reason=result.reason,
        document_id=result.document_id,
        draft_reply=result.draft_reply,
    )


@app.post("/slack/events")
@slack_app.post("/slack/events")
async def slack_events(
    request: Request,
    slack_timestamp: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
    slack_signature: str | None = Header(default=None, alias="X-Slack-Signature"),
) -> dict[str, object]:
    """Accept signed Slack events and echo user messages in their thread."""
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not signing_secret:
        raise HTTPException(status_code=503, detail="SLACK_SIGNING_SECRET is not configured.")

    body = await request.body()
    if not slack_timestamp or not slack_signature or not verify_slack_signature(
        body=body,
        timestamp=slack_timestamp,
        signature=slack_signature,
        signing_secret=signing_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Slack payload was not valid JSON.") from error

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    event = payload.get("event")
    if payload.get("type") != "event_callback" or not isinstance(event, dict):
        return {"ok": True}

    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True}

    is_mention = event.get("type") == "app_mention"
    is_direct_message = event.get("type") == "message" and event.get("channel_type") == "im"
    if not is_mention and not is_direct_message:
        return {"ok": True}

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=503, detail="SLACK_BOT_TOKEN is not configured.")

    channel = event.get("channel")
    message_ts = event.get("ts")
    text = event.get("text")
    if not all(isinstance(value, str) and value for value in (channel, message_ts, text)):
        raise HTTPException(status_code=400, detail="Slack message event is missing required fields.")

    clean_text = SLACK_MENTION.sub("", text, count=1).strip()
    thread_ts = event.get("thread_ts") or message_ts
    await run_in_threadpool(
        post_slack_message,
        bot_token=bot_token,
        channel=channel,
        text=f"Echo: {clean_text}",
        thread_ts=thread_ts,
    )
    return {"ok": True}
