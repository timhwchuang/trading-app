"""Phase 5: Walk-forward parameter sweep over backtest DAILY_SUMMARY KPIs."""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Any

import config
import man
from backtester import BacktestEngine
from data_loader import DEFAULT_CACHE_DIR
from determinism_check import _AuditCaptureHandler

DEFAULT_PENALTY = 50.0

_PATCH_TARGETS = (
    "ENTRY_BAND_POINTS",
    "VWAP_STOP_POINTS",
    "EXHAUSTION_VOL",
    "EXIT_GRACE_TICKS",
    "FIXED_TP_POINTS",
    "TRAIL_POINTS",
    "HARD_STOP_POINTS",
)


def _apply_params(params: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    saved: dict[str, tuple[Any, Any]] = {}
    for k, v in params.items():
        saved[k] = (getattr(man, k, None), getattr(config, k, None))
        setattr(man, k, v)
        setattr(config, k, v)
    return saved


def _restore_params(saved: dict[str, tuple[Any, Any]]) -> None:
    for k, (mv, cv) in saved.items():
        setattr(man, k, mv)
        setattr(config, k, cv)


def _run_backtest_summaries(
    code: str,
    dates: list,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    handler = _AuditCaptureHandler()
    strategy_logger = logging.getLogger("man")
    prev_level = strategy_logger.level
    strategy_logger.addHandler(handler)
    strategy_logger.setLevel(logging.INFO)
    try:
        engine = BacktestEngine(code, dates, cache_dir=cache_dir)
        engine.run()
    finally:
        strategy_logger.removeHandler(handler)
        strategy_logger.setLevel(prev_level)
    summaries: list[dict[str, Any]] = []
    for label, payload in handler.records:
        if label == "DAILY_SUMMARY":
            summaries.append(json.loads(payload))
    return summaries


def _aggregate_kpi(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        return {
            "daily_pnl_points": 0.0,
            "quick_stop_loss_rate": None,
            "day_count": 0,
        }
    total_pnl = sum(
        float(s.get("pnl", {}).get("daily_pnl_points", 0.0)) for s in summaries
    )
    rates = [
        s.get("quick_stop_loss", {}).get("rate")
        for s in summaries
        if s.get("quick_stop_loss", {}).get("rate") is not None
    ]
    avg_rate = sum(rates) / len(rates) if rates else None
    return {
        "daily_pnl_points": round(total_pnl, 2),
        "quick_stop_loss_rate": avg_rate,
        "day_count": len(summaries),
    }


def valid_score(valid_kpi: dict[str, Any], *, penalty: float = DEFAULT_PENALTY) -> float:
    rate = valid_kpi.get("quick_stop_loss_rate") or 0.0
    return float(valid_kpi.get("daily_pnl_points", 0.0)) - penalty * rate


def sweep(
    grid: dict[str, list],
    dates_train: list,
    dates_valid: list,
    code: str,
    cache_dir=DEFAULT_CACHE_DIR,
    *,
    penalty: float = DEFAULT_PENALTY,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Cartesian grid sweep; ranking uses valid (out-of-sample) KPI only."""
    cache_path = Path(cache_dir)
    keys = list(grid.keys())
    combos = itertools.product(*(grid[k] for k in keys))
    results: list[dict[str, Any]] = []
    for combo in combos:
        params = dict(zip(keys, combo))
        saved = _apply_params(params)
        try:
            train_kpi = _aggregate_kpi(
                _run_backtest_summaries(code, dates_train, cache_path)
            )
            valid_kpi = _aggregate_kpi(
                _run_backtest_summaries(code, dates_valid, cache_path)
            )
            results.append(
                {
                    "params": params,
                    "train_kpi": train_kpi,
                    "valid_kpi": valid_kpi,
                    "valid_score": valid_score(valid_kpi, penalty=penalty),
                }
            )
        finally:
            _restore_params(saved)

    results.sort(key=lambda row: row["valid_score"], reverse=True)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results
