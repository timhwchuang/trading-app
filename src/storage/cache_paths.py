"""Canonical on-disk cache locations for trading-app (single source of truth).

All replay, sweep, B-class calibration, and archiver code must import
``DEFAULT_TICK_CACHE_DIR`` (alias ``DEFAULT_CACHE_DIR``) from here or from
``storage.tick_loader`` — never ``trading_backtest.loader.DEFAULT_CACHE_DIR``
(cwd-relative) inside the app layer.
"""

from __future__ import annotations

from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_TICK_CACHE_DIR = _APP_ROOT / "tick_cache"
DEFAULT_KBAR_CACHE_DIR = _APP_ROOT / "kbar_cache"

# Backward-compatible alias used across storage / sweep / reporting modules.
DEFAULT_CACHE_DIR = DEFAULT_TICK_CACHE_DIR

__all__ = [
    "DEFAULT_CACHE_DIR",
    "DEFAULT_KBAR_CACHE_DIR",
    "DEFAULT_TICK_CACHE_DIR",
]