"""Phase 5: Walk-forward parameter sweep over backtest DAILY_SUMMARY KPIs."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from backtest.engine import BacktestEngine
from config import SWEEP_DD_PENALTY, SWEEP_SCORE_METRIC, SWEEP_SL_PENALTY
from core.runtime_config import default_runtime_config
from reporting.performance_metrics import aggregate_daily_performance, sweep_score_from_kpi
from reporting.forward_pnl import ForwardPnlPolicy, load_tick_series, make_replay_forward_pnl
from reporting.trend_calibration import compute_trend_veto_calibration
from storage.tick_loader import DEFAULT_CACHE_DIR
from strategy_vwap_momentum import apply_strategy_params, restore_strategy_params
from sweep.determinism_check import _run_with_audit_capture

DEFAULT_PENALTY = 50.0

# Backward-compatible aliases for tests
_apply_params = apply_strategy_params
_restore_params = restore_strategy_params


def _run_backtest_summaries(
    code: str,
    dates: list,
    cache_dir: Path,
    runtime_config=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run backtest under capture handler.
    Returns (daily_summaries, signal_audits) so CAL-3 can feed real SIGNAL_AUDIT
    (incl. reason=trend_veto) into compute_trend_veto_calibration instead of always-empty.
    _AuditCaptureHandler already matches "SIGNAL_AUDIT " prefix (P1-6 fix).
    """
    def _run() -> None:
        engine = BacktestEngine(
            code, dates, cache_dir=cache_dir, runtime_config=runtime_config
        )
        engine.run()

    records = _run_with_audit_capture(_run)
    summaries: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for label, payload in records:
        if label == "DAILY_SUMMARY":
            try:
                summaries.append(json.loads(payload))
            except Exception:
                pass
        elif label == "SIGNAL_AUDIT":
            try:
                signals.append(json.loads(payload))
            except Exception:
                pass
    return summaries, signals


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


def _resolve_forward_pnl(
    code: str,
    dates_valid: list,
    cache_path: Path,
    forward_policy: ForwardPnlPolicy | None,
):
    if forward_policy is None:
        return None
    series = load_tick_series(code, dates_valid, cache_dir=cache_path)
    if not series.timestamps:
        return None
    return make_replay_forward_pnl(series, forward_policy)


def sweep(
    grid: dict[str, list],
    dates_train: list,
    dates_valid: list,
    code: str,
    cache_dir=DEFAULT_CACHE_DIR,
    *,
    penalty: float = DEFAULT_PENALTY,
    output_path: Path | None = None,
    forward_policy: ForwardPnlPolicy | None = None,
) -> list[dict[str, Any]]:
    """Cartesian grid sweep; ranking uses valid (out-of-sample) KPI only."""
    cache_path = Path(cache_dir)
    replay_fwd = _resolve_forward_pnl(code, dates_valid, cache_path, forward_policy)
    keys = list(grid.keys())
    combos = itertools.product(*(grid[k] for k in keys))
    results: list[dict[str, Any]] = []
    for combo in combos:
        params = dict(zip(keys, combo))
        cfg = default_runtime_config()
        saved = apply_strategy_params(params, cfg)
        try:
            train_summaries, _train_signals = _run_backtest_summaries(
                code, dates_train, cache_path, runtime_config=cfg
            )
            valid_summaries, valid_signals = _run_backtest_summaries(
                code, dates_valid, cache_path, runtime_config=cfg
            )
            train_kpi = _aggregate_kpi(train_summaries)
            valid_kpi = _aggregate_kpi(valid_summaries)
            # P6-1-CAL-3/4/6: if trend params present, feed captured SIGNAL_AUDITs (reason=trend_veto)
            # from the valid run into the harness instead of hardcoded [].
            # This makes veto_metrics a real (if still synthetic-toy fwd for A-class) conditional
            # expectation instead of an empty-shell always-0 structure.
            # B-class will supply better get_forward_pnl from replay + real UAT logs.
            veto_metrics = None
            if any(
                str(k).startswith("trend_")
                or str(k).upper().startswith("TREND_")
                or "TREND" in str(k).upper()
                for k in params.keys()
            ):
                try:
                    veto_audits = [
                        s
                        for s in valid_signals
                        if str(s.get("reason", "")).lower() in ("trend_veto", "trend veto")
                        or "trend_veto" in str(s)
                    ]
                    allowed_audits = [
                        s
                        for s in valid_signals
                        if s.get("intent") == "entry"
                        and str(s.get("reason", "")).lower() not in ("trend_veto", "trend veto")
                    ]
                    veto_metrics = compute_trend_veto_calibration(
                        veto_audits,
                        allowed_audits=allowed_audits or None,
                        get_forward_pnl=replay_fwd,
                        forward_policy=forward_policy,
                        b_class=replay_fwd is not None,
                    )
                except Exception:
                    veto_metrics = {"note": "harness call failed (synthetic path)"}
            row = {
                "params": params,
                "train_kpi": train_kpi,
                "valid_kpi": valid_kpi,
                "valid_score": valid_score(valid_kpi, penalty=penalty),
            }
            if veto_metrics is not None:
                row["veto_metrics"] = veto_metrics
            results.append(row)
        finally:
            restore_strategy_params(saved, cfg)

    results.sort(key=lambda row: row["valid_score"], reverse=True)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results
