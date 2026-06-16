"""Phase 4: Determinism gate — SHA-256 over canonical audit JSON lines."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Iterable, List

from backtest.engine import BacktestEngine
from storage.tick_loader import DEFAULT_CACHE_DIR

_AUDIT_PREFIXES = ("SIGNAL_AUDIT ", "FILL_AUDIT ", "DAILY_SUMMARY ")
_NON_DETERMINISTIC_OPERATIONAL_KEYS = frozenset(
    {
        "lock_wait_max_ms",
        "lock_wait_over_50ms",
        "no_tick_resubscribe",
        "atr_min",
        "atr_max",
        "atr_samples",
        "tick_type",
    }
)
_AUDIT_LOGGERS = ("trading_engine", "strategy_vwap_momentum")


def normalize_audit_for_hash(label: str, json_part: str) -> str:
    """Canonical JSON for hashing; strips wall-clock / ops telemetry from DAILY_SUMMARY."""
    obj = json.loads(json_part)
    if label == "DAILY_SUMMARY":
        operational = obj.get("operational")
        if isinstance(operational, dict):
            obj = {
                **obj,
                "operational": {
                    k: v
                    for k, v in operational.items()
                    if k not in _NON_DETERMINISTIC_OPERATIONAL_KEYS
                },
            }
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_audit_json(json_part: str) -> str:
    """Parse and re-serialize with stable key order (6.8)."""
    obj = json.loads(json_part)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class _AuditCaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        for prefix in _AUDIT_PREFIXES:
            if msg.startswith(prefix):
                label = prefix.strip()
                self.records.append((label, msg[len(prefix) :]))
                return


def hash_audit_records(records: Iterable[tuple[str, str]]) -> str:
    hasher = hashlib.sha256()
    for label, json_part in records:
        hasher.update(normalize_audit_for_hash(label, json_part).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def hash_audit_lines(json_parts: Iterable[str]) -> str:
    """Hash raw JSON payloads (no DAILY_SUMMARY operational stripping)."""
    hasher = hashlib.sha256()
    for json_part in json_parts:
        hasher.update(canonical_audit_json(json_part).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _run_with_audit_capture(fn) -> list[tuple[str, str]]:
    handler = _AuditCaptureHandler()
    loggers: list[tuple[logging.Logger, int]] = []
    for name in _AUDIT_LOGGERS:
        logger = logging.getLogger(name)
        loggers.append((logger, logger.level))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        fn()
    finally:
        for logger, prev_level in loggers:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
    return handler.records


def run_hash(
    code: str,
    dates: list,
    cache_dir=DEFAULT_CACHE_DIR,
) -> str:
    """Run one backtest and hash SIGNAL_AUDIT + FILL_AUDIT + DAILY_SUMMARY JSON."""

    def _run() -> None:
        engine = BacktestEngine(code, dates, cache_dir=Path(cache_dir))
        engine.run()

    records = _run_with_audit_capture(_run)
    return hash_audit_records(records)


def capture_backtest_log_lines(
    code: str,
    dates: list,
    cache_dir=DEFAULT_CACHE_DIR,
) -> list[str]:
    """Return uat_report-compatible log lines from a backtest run."""

    def _run() -> None:
        engine = BacktestEngine(code, dates, cache_dir=Path(cache_dir))
        engine.run()

    records = _run_with_audit_capture(_run)
    return [f"10:00:00 [INFO] {label} {payload}" for label, payload in records]