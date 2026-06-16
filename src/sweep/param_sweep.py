"""Phase 5: Walk-forward parameter sweep over backtest DAILY_SUMMARY KPIs."""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Any

from backtest.engine import BacktestEngine
from config import SWEEP_DD_PENALTY, SWEEP_SCORE_METRIC, SWEEP_SL_PENALTY
from storage.tick_loader import DEFAULT_CACHE_DIR
from sweep.determinism_check import _AuditCaptureHandler
from reporting.performance_metrics import aggregate_daily_performance, sweep_score_from_kpi
from strategy.params import (
    apply_strategy_params,
    restore_strategy_params,
)

DEFAULT_PENALTY = 50.0

# Backward-compatible aliases for tests
_apply_params = apply_strategy_params
_restore_params = restore_strategy_params


def _run_backtest_summaries(
    code: str,
    dates: list,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    handler = _AuditCaptureHandler()
    strategy_logger = logging.getLogger("theman")
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
            "performance_aggregate": aggregate_daily_performance([]),
            "_summaries": [],
        }
    total_pnl = sum(
        float(s.get("pnl", {}).get("daily_pnl_points", 0.0)) for s in summaries
    )
    total_quick_sl = sum(
        int(s.get("quick_stop_loss", {}).get("count", 0) or 0) for s in summaries
    )
    total_exits = sum(
        int(s.get("fills", {}).get("exit_count", 0) or 0) for s in summaries
    )
    weighted_rate = (
        total_quick_sl / total_exits if total_exits > 0 else None
    )
    perf_agg = aggregate_daily_performance(summaries)
    kpi = {
        "daily_pnl_points": round(total_pnl, 2),
        "quick_stop_loss_rate": weighted_rate,
        "day_count": len(summaries),
        "performance_aggregate": perf_agg,
        "_summaries": summaries,
    }
    kpi["valid_score"] = sweep_score_from_kpi(
        kpi,
        metric=SWEEP_SCORE_METRIC,
        dd_penalty=SWEEP_DD_PENALTY,
        sl_penalty=SWEEP_SL_PENALTY,
    )
    return kpi


def valid_score(valid_kpi: dict[str, Any], *, penalty: float = DEFAULT_PENALTY) -> float:
    if "valid_score" in valid_kpi:
        return float(valid_kpi["valid_score"])
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
        saved = apply_strategy_params(params)
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
            restore_strategy_params(saved)

    results.sort(key=lambda row: row["valid_score"], reverse=True)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results
