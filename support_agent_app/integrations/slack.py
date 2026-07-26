from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.request import Request, urlopen

SLACK_API_URL = "https://slack.com/api/chat.postMessage"
MAX_REQUEST_AGE_SECONDS = 60 * 5


def verify_slack_signature(
    *,
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    now: float | None = None,
) -> bool:
    """Verify that an HTTP request was signed by Slack and is recent."""
    if not timestamp.isdigit():
        return False

    current_time = time.time() if now is None else now
    if abs(current_time - int(timestamp)) > MAX_REQUEST_AGE_SECONDS:
        return False

    base_string = b"v0:" + timestamp.encode("utf-8") + b":" + body
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        base_string,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def post_slack_message(
    *,
    bot_token: str,
    channel: str,
    text: str,
    thread_ts: str,
) -> None:
    """Post one threaded message through Slack's Web API."""
    request = Request(
        SLACK_API_URL,
        data=json.dumps(
            {
                "channel": channel,
                "text": text,
                "thread_ts": thread_ts,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    with urlopen(request, timeout=2) as response:
        payload = json.loads(response.read())

    if not payload.get("ok"):
        raise RuntimeError(f"Slack rejected chat.postMessage: {payload.get('error', 'unknown error')}")
