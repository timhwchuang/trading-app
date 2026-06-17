"""P6-6: Survival metrics (expectancy, max drawdown, Sharpe) and friction costs."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FrictionSettings:
    enabled: bool = False
    mode: str = "flat_round_trip"
    round_trip_friction_points: float = 2.0
    commission_per_side_points: float = 0.5
    tax_per_exit_points: float = 1.0
    commission_per_side_ntd: float = 0.0
    tax_rate: float = 0.0
    point_value_ntd: float = 10.0


def friction_settings_from_mapping(data: Mapping[str, Any] | None) -> FrictionSettings:
    if not data:
        return FrictionSettings()
    return FrictionSettings(
        enabled=bool(data.get("enabled", False)),
        mode=str(data.get("mode", "flat_round_trip")),
        round_trip_friction_points=float(data.get("round_trip_friction_points", 2.0)),
        commission_per_side_points=float(
            data.get("commission_per_side_points", 0.5)
        ),
        tax_per_exit_points=float(data.get("tax_per_exit_points", 1.0)),
        commission_per_side_ntd=float(data.get("commission_per_side_ntd", 0.0)),
        tax_rate=float(data.get("tax_rate", 0.0)),
        point_value_ntd=float(data.get("point_value_ntd", 10.0)),
    )


def friction_per_round_trip(settings: FrictionSettings) -> float:
    if not settings.enabled:
        return 0.0
    mode = settings.mode
    if mode == "flat_round_trip":
        return settings.round_trip_friction_points
    if mode == "per_side":
        return 2.0 * settings.commission_per_side_points + settings.tax_per_exit_points
    if mode == "ntd":
        pv = settings.point_value_ntd
        if pv <= 0:
            return 0.0
        ntd = 2.0 * settings.commission_per_side_ntd
        if settings.tax_rate:
            ntd += settings.tax_rate
        return round(ntd / pv, 4)
    return settings.round_trip_friction_points


def extract_round_trip_gross_pnls(fills: Sequence[Mapping[str, Any]]) -> list[float]:
    """Pair entry/exit FILL rows into completed round-trip gross PnL (points)."""
    pnls: list[float] = []
    open_entry = False
    for fill in fills:
        intent = fill.get("intent")
        if intent == "entry":
            open_entry = True
        elif intent == "exit" and open_entry:
            pnls.append(float(fill.get("pnl_points", 0.0)))
            open_entry = False
    return pnls


def _safe_mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 4)


def _safe_stdev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    return round(statistics.stdev(values), 4)


def compute_expectancy_stats(
    gross_pnls: Sequence[float],
    *,
    friction_per_trade: float = 0.0,
) -> dict[str, Any]:
    if not gross_pnls:
        return {
            "trade_count": 0,
            "win_rate": None,
            "avg_win_gross": None,
            "avg_loss_gross": None,
            "payoff_ratio": None,
            "expectancy_per_trade_gross": None,
            "expectancy_per_trade_net": None,
            "friction_per_trade": friction_per_trade,
        }

    wins = [p for p in gross_pnls if p > 0]
    losses = [p for p in gross_pnls if p < 0]
    count = len(gross_pnls)
    win_rate = len(wins) / count if count else None
    avg_win = _safe_mean(wins)
    avg_loss = _safe_mean(losses)
    payoff = None
    if avg_win is not None and avg_loss is not None and avg_loss != 0:
        payoff = round(avg_win / abs(avg_loss), 4)

    exp_gross = _safe_mean(gross_pnls)
    exp_net = (
        round(exp_gross - friction_per_trade, 4) if exp_gross is not None else None
    )

    return {
        "trade_count": count,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "avg_win_gross": avg_win,
        "avg_loss_gross": avg_loss,
        "payoff_ratio": payoff,
        "expectancy_per_trade_gross": exp_gross,
        "expectancy_per_trade_net": exp_net,
        "friction_per_trade": friction_per_trade,
    }


def equity_curve_from_pnls(
    net_pnls: Sequence[float],
    *,
    initial_capital: float = 0.0,
) -> list[float]:
    """Cumulative equity starting at initial_capital (before first trade)."""
    equity: list[float] = [round(initial_capital, 4)]
    running = round(initial_capital, 4)
    for p in net_pnls:
        running = round(running + p, 4)
        equity.append(running)
    return equity


def compute_drawdown(equity_curve: Sequence[float]) -> dict[str, Any]:
    """Max drawdown on an equity curve that includes the starting balance."""
    if len(equity_curve) < 2:
        return {
            "max_drawdown_points": None,
            "max_drawdown_pct": None,
            "max_drawdown_duration_trades": None,
        }

    peak = equity_curve[0]
    max_dd = 0.0
    peak_at_max_dd = peak
    max_dd_duration = 0
    dd_start_idx: int | None = None

    for i, equity in enumerate(equity_curve):
        if equity > peak:
            peak = equity
            dd_start_idx = None
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown
            peak_at_max_dd = peak
            if dd_start_idx is None:
                dd_start_idx = i
            max_dd_duration = i - dd_start_idx
        if equity < peak and dd_start_idx is None:
            dd_start_idx = i

    max_dd_pct = (
        (max_dd / peak_at_max_dd * 100.0) if peak_at_max_dd > 0 else None
    )

    return {
        "max_drawdown_points": round(max_dd, 4),
        "max_drawdown_pct": round(max_dd_pct, 4) if max_dd_pct is not None else None,
        "max_drawdown_duration_trades": max_dd_duration if max_dd > 0 else 0,
    }


def compute_sharpe_sortino(
    returns: Sequence[float],
    *,
    period: str = "per_trade",
    risk_free: float = 0.0,
) -> dict[str, Any]:
    if len(returns) < 2:
        return {
            "sharpe": None,
            "sortino": None,
            "return_period": period,
            "return_count": len(returns),
        }

    mean_r = statistics.mean(returns) - risk_free
    stdev = statistics.stdev(returns)
    sharpe = round(mean_r / stdev, 4) if stdev > 0 else None

    downside = [min(0.0, r - risk_free) for r in returns]
    downside_sq = [d * d for d in downside]
    if not any(d > 0 for d in downside_sq):
        sortino = None
    else:
        downside_dev = math.sqrt(statistics.mean(downside_sq))
        sortino = round(mean_r / downside_dev, 4) if downside_dev > 0 else None

    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "return_period": period,
        "return_count": len(returns),
    }


def compute_performance_from_fills(
    fills: Sequence[Mapping[str, Any]],
    friction: FrictionSettings,
    *,
    sharpe_period: str = "per_trade",
    initial_capital: float = 0.0,
) -> dict[str, Any]:
    gross_pnls = extract_round_trip_gross_pnls(fills)
    fpt = friction_per_round_trip(friction)
    expectancy = compute_expectancy_stats(gross_pnls, friction_per_trade=fpt)

    net_pnls = [round(g - fpt, 4) for g in gross_pnls]
    cumulative_net = equity_curve_from_pnls(
        net_pnls, initial_capital=initial_capital
    )

    drawdown = compute_drawdown(cumulative_net)
    sharpe_src = net_pnls if sharpe_period == "per_trade" else gross_pnls
    risk_adj = compute_sharpe_sortino(sharpe_src, period=sharpe_period)

    return {
        "friction_enabled": friction.enabled,
        "friction_mode": friction.mode,
        "expectancy": expectancy,
        "drawdown": drawdown,
        "risk_adjusted": risk_adj,
        "total_pnl_gross": round(sum(gross_pnls), 2) if gross_pnls else 0.0,
        "total_pnl_net": round(sum(net_pnls), 2) if net_pnls else 0.0,
        "round_trip_net_pnls": net_pnls,
    }


def aggregate_daily_performance(
    summaries: Sequence[Mapping[str, Any]],
    *,
    initial_capital: float = 0.0,
) -> dict[str, Any]:
    """Aggregate multi-day DAILY_SUMMARY performance blocks (sum PnL, chained MDD)."""
    total_gross = 0.0
    total_net = 0.0
    trade_count = 0
    win_count = 0
    all_net_pnls: list[float] = []

    for summary in summaries:
        perf = summary.get("performance") or {}
        total_gross += float(perf.get("total_pnl_gross", 0.0))
        total_net += float(perf.get("total_pnl_net", 0.0))
        exp = perf.get("expectancy") or {}
        tc = int(exp.get("trade_count", 0) or 0)
        trade_count += tc
        wr = exp.get("win_rate")
        if wr is not None and tc:
            win_count += int(round(float(wr) * tc))
        day_pnls = perf.get("round_trip_net_pnls")
        if day_pnls:
            all_net_pnls.extend(float(p) for p in day_pnls)

    win_rate = round(win_count / trade_count, 4) if trade_count else None

    if all_net_pnls:
        dd = compute_drawdown(
            equity_curve_from_pnls(all_net_pnls, initial_capital=initial_capital)
        )
        max_dd_points = dd["max_drawdown_points"]
        max_dd_pct = dd["max_drawdown_pct"]
    else:
        max_dd_points = None
        max_dd_pct = None

    return {
        "day_count": len(summaries),
        "trade_count": trade_count,
        "total_pnl_gross": round(total_gross, 2),
        "total_pnl_net": round(total_net, 2),
        "win_rate": win_rate,
        "expectancy_per_trade_net": (
            round(total_net / trade_count, 4) if trade_count else None
        ),
        "max_drawdown_points": max_dd_points,
        "max_drawdown_pct": max_dd_pct,
    }


def _daily_net_pnl_from_summary(summary: Mapping[str, Any]) -> float:
    perf = summary.get("performance") or {}
    if perf.get("total_pnl_net") is not None:
        return float(perf["total_pnl_net"])
    return float(summary.get("pnl", {}).get("daily_pnl_points", 0.0))


def compute_cumulative_risk_progression(
    summaries: Sequence[Mapping[str, Any]],
    *,
    initial_capital: float = 0.0,
    max_acceptable_mdd: float | None = None,
) -> dict[str, Any]:
    """Day-by-day cumulative equity and running max drawdown (累進 MDD)."""
    if not summaries:
        return {
            "initial_capital_points": round(initial_capital, 4),
            "max_acceptable_mdd_points": max_acceptable_mdd,
            "cumulative_pnl_net": 0.0,
            "ending_equity": round(initial_capital, 4),
            "cumulative_max_drawdown_points": None,
            "current_drawdown_points": None,
            "budget_used_pct": None,
            "budget_headroom_points": None,
            "budget_breached": False,
            "daily_progression": [],
        }

    ordered = sorted(summaries, key=lambda s: str(s.get("date", "")))
    peak = round(initial_capital, 4)
    equity = round(initial_capital, 4)
    cumulative_pnl = 0.0
    cumulative_max_dd = 0.0
    daily_rows: list[dict[str, Any]] = []

    for summary in ordered:
        day_pnl = round(_daily_net_pnl_from_summary(summary), 4)
        cumulative_pnl = round(cumulative_pnl + day_pnl, 4)
        equity = round(initial_capital + cumulative_pnl, 4)
        if equity > peak:
            peak = equity
        current_dd = round(max(0.0, peak - equity), 4)
        cumulative_max_dd = round(max(cumulative_max_dd, current_dd), 4)
        row: dict[str, Any] = {
            "date": summary.get("date"),
            "daily_pnl_net": day_pnl,
            "cumulative_pnl_net": cumulative_pnl,
            "equity": equity,
            "peak_equity": peak,
            "current_drawdown_points": current_dd,
            "cumulative_max_drawdown_points": cumulative_max_dd,
        }
        if max_acceptable_mdd is not None and max_acceptable_mdd > 0:
            row["budget_used_pct"] = round(
                cumulative_max_dd / max_acceptable_mdd * 100.0, 2
            )
        daily_rows.append(row)

    budget_used = None
    headroom = None
    breached = False
    if max_acceptable_mdd is not None and max_acceptable_mdd > 0:
        budget_used = round(cumulative_max_dd / max_acceptable_mdd * 100.0, 2)
        headroom = round(max_acceptable_mdd - cumulative_max_dd, 4)
        breached = cumulative_max_dd > max_acceptable_mdd

    dd_pct = None
    if peak > 0:
        dd_pct = round(cumulative_max_dd / peak * 100.0, 4)

    return {
        "initial_capital_points": round(initial_capital, 4),
        "max_acceptable_mdd_points": max_acceptable_mdd,
        "cumulative_pnl_net": cumulative_pnl,
        "ending_equity": equity,
        "cumulative_max_drawdown_points": cumulative_max_dd,
        "cumulative_max_drawdown_pct": dd_pct,
        "current_drawdown_points": daily_rows[-1]["current_drawdown_points"]
        if daily_rows
        else None,
        "budget_used_pct": budget_used,
        "budget_headroom_points": headroom,
        "budget_breached": breached,
        "daily_progression": daily_rows,
    }


def sweep_score_from_kpi(
    kpi: Mapping[str, Any],
    *,
    metric: str = "expectancy_net",
    dd_penalty: float = 0.0,
    sl_penalty: float = 50.0,
) -> float:
    """Composite score for param_sweep (valid out-of-sample only)."""
    agg = kpi.get("performance_aggregate") or {}
    exp_net = agg.get("expectancy_per_trade_net")
    if exp_net is None:
        exp_net = 0.0
    mdd = agg.get("max_drawdown_points") or 0.0
    qsl = kpi.get("quick_stop_loss_rate") or 0.0
    pnl_net = agg.get("total_pnl_net") or kpi.get("daily_pnl_points", 0.0)

    if metric == "pnl_net":
        base = float(pnl_net)
    elif metric == "sharpe_net":
        sharpe_vals = [
            float((s.get("performance") or {}).get("risk_adjusted", {}).get("sharpe"))
            for s in kpi.get("_summaries", [])
            if (s.get("performance") or {}).get("risk_adjusted", {}).get("sharpe")
            is not None
        ]
        base = statistics.mean(sharpe_vals) if sharpe_vals else 0.0
    else:
        base = float(exp_net)

    return round(base - dd_penalty * float(mdd) - sl_penalty * float(qsl), 4)
