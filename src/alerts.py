"""P4-3: Alert dispatch (Telegram / generic webhook).

Callback-safe: ``send_alert`` only enqueues; a background worker performs I/O.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_ALERT_QUEUE_MAXSIZE = 500


@dataclass(frozen=True)
class _AlertRecord:
    message: str
    level: str


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


def _send_alert_sync(message: str, *, level: str = "WARNING") -> bool:
    """Blocking network I/O; only call from the alert worker thread."""
    text = f"[trading-app][{level}] {message}"
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


class _AlertDispatcher:
    """Background sender: callers only ``put_nowait``; never block callback threads."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_AlertRecord] = queue.Queue(
            maxsize=_ALERT_QUEUE_MAXSIZE
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._worker,
                name="alert-dispatcher",
                daemon=True,
            )
            self._thread.start()
            atexit.register(self.shutdown)

    def enqueue(self, message: str, level: str) -> None:
        self._ensure_started()
        try:
            self._queue.put_nowait(_AlertRecord(message, level))
        except queue.Full:
            logger.warning("告警佇列已滿，丟棄 | %s", message[:120])

    def _worker(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                _send_alert_sync(record.message, level=record.level)
            except Exception as e:
                logger.warning("告警 worker 異常: %s", e)

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def flush_for_test(self, timeout: float = 5.0) -> None:
        """Wait until the queue is drained (tests only)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.empty():
                time.sleep(0.05)
                if self._queue.empty():
                    return
            time.sleep(0.01)


_dispatcher = _AlertDispatcher()


def send_alert(message: str, *, level: str = "WARNING") -> bool:
    """Best-effort alert; never raises. Enqueues for async delivery."""
    logger.log(
        logging.CRITICAL if level == "CRITICAL" else logging.WARNING,
        "ALERT %s",
        message,
    )
    _dispatcher.enqueue(message, level)
    return True


def flush_alerts_for_test(timeout: float = 5.0) -> None:
    """Drain the alert queue (unit tests)."""
    _dispatcher.flush_for_test(timeout)
