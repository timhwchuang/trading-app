"""P0-11 follow-up: archive kbars from refresh_atr for backtest ATR warmup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from storage.kbar_loader import (
    DEFAULT_CACHE_DIR,
    KBarRecord,
    _kbars_raw_to_records,
    kbars_cache_path,
    save_kbars_csv,
)

logger = logging.getLogger(__name__)


def archive_kbars_snapshot(
    raw_kbars: Any,
    *,
    product_code: str,
    trade_date,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> int:
    """Write today's kbars API response to ``{code}_kbars_{date}.csv``."""
    bars = _kbars_raw_to_records(raw_kbars)
    if trade_date is not None:
        bars = [b for b in bars if b.ts.date() == trade_date]
    if not bars:
        return 0
    path = kbars_cache_path(cache_dir, product_code, trade_date or bars[-1].ts.date())
    count = save_kbars_csv(bars, path)
    logger.info(
        "Kbars 落盤 | code=%s date=%s bars=%d path=%s",
        product_code,
        path.stem.split("_")[-1],
        count,
        path.name,
    )
    return count
