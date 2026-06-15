"""P4-3: Alert dispatch (Telegram / generic webhook)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict[str, Any], *, timeout: float = 10.0) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("告警發送失敗 | url=%s err=%s", url, e)
        return False


def send_alert(message: str, *, level: str = "WARNING") -> bool:
    """Best-effort alert; never raises. Returns True if any channel succeeded."""
    text = f"[theman][{level}] {message}"
    logger.log(
        logging.CRITICAL if level == "CRITICAL" else logging.WARNING,
        "ALERT %s",
        message,
    )

    sent = False
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        if _post_json(url, {"chat_id": chat_id, "text": text}):
            sent = True

    webhook = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if webhook:
        if _post_json(webhook, {"text": text, "level": level}):
            sent = True

    return sent
