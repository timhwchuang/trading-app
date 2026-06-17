"""Parse strategy logs: SIGNAL_AUDIT, FILL_AUDIT, DAILY_SUMMARY → UAT metrics."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from observability import FillAudit
from reporting.performance_metrics import (
    FrictionSettings,
    aggregate_daily_performance,
    compute_cumulative_risk_progression,
    compute_performance_from_fills,
)
from trading_engine.core.audit.signal_audit import SignalAudit

MOMENTUM_TRIGGER_RE = re.compile(r"MOMENTUM (Long|Short) 突破")
SIGNAL_AUDIT_RE = re.compile(r"SIGNAL_AUDIT (.+)$")
FILL_AUDIT_RE = re.compile(r"FILL_AUDIT (.+)$")
DAILY_SUMMARY_RE = re.compile(r"DAILY_SUMMARY (.+)$")
INTENT_CANCELLED_RE = re.compile(
    r"委託未成交/已取消，重置 pending \| tag=(intent_cancelled(?:_open_session)?)"
)
TICK_TYPE_RE = re.compile(
    r"tick_type 分布 \| type0=(\d+) type1=(\d+) type2=(\d+) total=(\d+)"
)


@dataclass
class TradeRound:
    entry_ts: int
    entry_direction: str
    exit_ts: int | None = None
    exit_reason: str = ""
    hold_sec: int | None = None


def parse_signal_audit_line(line: str) -> SignalAudit | None:
    match = SIGNAL_AUDIT_RE.search(line)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return SignalAudit(**payload)


def parse_fill_audit_line(line: str) -> FillAudit | None:
    match = FILL_AUDIT_RE.search(line)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return FillAudit(**payload)


def parse_daily_summary_line(line: str) -> dict | None:
    match = DAILY_SUMMARY_RE.search(line)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def count_momentum_triggers(lines: list[str]) -> int:
    return sum(1 for line in lines if MOMENTUM_TRIGGER_RE.search(line))


def build_trade_rounds_from_events(
    events: list[dict[str, object]],
) -> list[TradeRound]:
    """Unified trade-round builder from normalized event dicts."""
    rounds: list[TradeRound] = []
    open_round: TradeRound | None = None

    for event in events:
        intent = str(event["intent"])
        if intent == "entry":
            if open_round is not None:
                rounds.append(open_round)
            open_round = TradeRound(
                entry_ts=int(event["ts"]),
                entry_direction=str(event["direction"]),
            )
        elif intent == "exit":
            if open_round is None:
                continue
            open_round.exit_ts = int(event["ts"])
            open_round.exit_reason = str(
                event.get("reason") or event.get("exit_reason") or ""
            )
            hold = event.get("hold_sec")
            if hold is not None:
                open_round.hold_sec = int(hold)  # type: ignore[arg-type]
            elif open_round.exit_ts is not None:
                open_round.hold_sec = open_round.exit_ts - open_round.entry_ts
            rounds.append(open_round)
            open_round = None

    if open_round is not None:
        rounds.append(open_round)

    return rounds


def build_trade_rounds(audits: list[SignalAudit]) -> list[TradeRound]:
    events = [
        {
            "intent": audit.intent,
            "ts": audit.ts,
            "direction": audit.direction,
            "reason": audit.reason if audit.intent == "exit" else "",
        }
        for audit in audits
    ]
    return build_trade_rounds_from_events(events)


def build_trade_rounds_from_fills(fills: list[FillAudit]) -> list[TradeRound]:
    events = [
        {
            "intent": fill.intent,
            "ts": fill.ts,
            "direction": fill.direction,
            "exit_reason": fill.exit_reason,
            "hold_sec": fill.hold_sec,
        }
        for fill in fills
    ]
    return build_trade_rounds_from_events(events)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (pct / 100) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 2)


def slippage_stats(fills: list[FillAudit]) -> dict:
    entry = [f.slippage_pts for f in fills if f.intent == "entry"]
    exit_ = [f.slippage_pts for f in fills if f.intent == "exit"]
    return {
        "entry_median": _percentile(entry, 50) if entry else None,
        "entry_p90": _percentile(entry, 90),
        "exit_median": _percentile(exit_, 50) if exit_ else None,
        "exit_p90": _percentile(exit_, 90),
        "entry_count": len(entry),
        "exit_count": len(exit_),
    }


def expectancy_by_reason(fills: list[FillAudit]) -> dict[str, dict]:
    buckets: dict[str, list[float]] = {}
    for fill in fills:
        if fill.intent != "exit" or not fill.exit_reason:
            continue
        buckets.setdefault(fill.exit_reason, []).append(fill.pnl_points)

    result: dict[str, dict] = {}
    for reason, pnls in buckets.items():
        count = len(pnls)
        total = round(sum(pnls), 2)
        result[reason] = {
            "count": count,
            "total_pnl": total,
            "avg_pnl": round(total / count, 2) if count else 0.0,
        }
    return result


def count_intent_cancelled(lines: list[str]) -> dict[str, int]:
    counts = {"intent_cancelled": 0, "intent_cancelled_open_session": 0}
    for line in lines:
        match = INTENT_CANCELLED_RE.search(line)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts


def latest_tick_type_line(lines: list[str]) -> dict | None:
    for line in reversed(lines):
        match = TICK_TYPE_RE.search(line)
        if not match:
            continue
        t0, t1, t2, total = (int(match.group(i)) for i in range(1, 5))
        return {
            "type0": t0,
            "type1": t1,
            "type2": t2,
            "total": total,
            "type0_pct": round(100.0 * t0 / total, 2) if total else None,
        }
    return None


def parse_daily_summaries(lines: list[str]) -> list[dict]:
    summaries: list[dict] = []
    for line in lines:
        summary = parse_daily_summary_line(line)
        if summary is not None:
            summaries.append(summary)
    return summaries


def parse_log_audits_and_fills(
    lines: list[str],
) -> tuple[list[SignalAudit], list[FillAudit]]:
    audits = [
        audit
        for line in lines
        if (audit := parse_signal_audit_line(line)) is not None
    ]
    fills = [
        fill for line in lines if (fill := parse_fill_audit_line(line)) is not None
    ]
    return audits, fills


def compute_trade_rounds(
    audits: list[SignalAudit], fills: list[FillAudit]
) -> list[TradeRound]:
    if fills:
        return build_trade_rounds_from_fills(fills)
    return build_trade_rounds(audits)


def compute_quick_sl_metrics(
    *,
    rounds: list[TradeRound],
    fills: list[FillAudit],
    quick_sl_sec: int,
) -> tuple[int, float | None, list[dict]]:
    stop_loss_reasons = {"stop_loss", "stop_loss_vwap"}
    completed = [r for r in rounds if r.exit_ts is not None]
    quick_stop_loss_rounds = [
        r
        for r in completed
        if r.exit_reason in stop_loss_reasons
        and r.exit_ts is not None
        and (r.exit_ts - r.entry_ts) < quick_sl_sec
    ]
    quick_stop_loss_fills = [
        f
        for f in fills
        if f.intent == "exit"
        and f.exit_reason in stop_loss_reasons
        and f.hold_sec < quick_sl_sec
    ]
    quick_sl_count = (
        len(quick_stop_loss_fills) if fills else len(quick_stop_loss_rounds)
    )
    quick_sl_rate = quick_sl_count / len(completed) if completed else None
    examples = (
        [
            {
                "direction": f.direction,
                "exit_ts": f.ts,
                "hold_sec": f.hold_sec,
                "exit_reason": f.exit_reason,
                "slippage_pts": f.slippage_pts,
            }
            for f in quick_stop_loss_fills[:10]
        ]
        if fills
        else [
            {
                "direction": r.entry_direction,
                "entry_ts": r.entry_ts,
                "exit_ts": r.exit_ts,
                "hold_sec": r.hold_sec,
                "exit_reason": r.exit_reason,
            }
            for r in quick_stop_loss_rounds[:10]
        ]
    )
    return quick_sl_count, quick_sl_rate, examples


@dataclass(frozen=True)
class RiskBudgetSettings:
    initial_capital_points: float = 0.0
    max_acceptable_mdd_points: float | None = None


def resolve_risk_budget_settings(
    risk: RiskBudgetSettings | None,
) -> RiskBudgetSettings:
    if risk is not None:
        return risk
    try:
        from config import INITIAL_CAPITAL_POINTS, MAX_ACCEPTABLE_MDD_POINTS

        return RiskBudgetSettings(
            initial_capital_points=INITIAL_CAPITAL_POINTS,
            max_acceptable_mdd_points=MAX_ACCEPTABLE_MDD_POINTS,
        )
    except Exception:
        return RiskBudgetSettings()


def resolve_friction_settings(
    friction: FrictionSettings | None,
) -> tuple[FrictionSettings, str]:
    if friction is None:
        try:
            from config import (
                COMMISSION_PER_SIDE_NTD,
                COMMISSION_PER_SIDE_POINTS,
                FRICTION_ENABLED,
                FRICTION_MODE,
                FRICTION_TAX_RATE,
                POINT_VALUE_NTD,
                ROUND_TRIP_FRICTION_POINTS,
                SHARPE_PERIOD,
                TAX_PER_EXIT_POINTS,
            )

            friction = FrictionSettings(
                enabled=FRICTION_ENABLED,
                mode=FRICTION_MODE,
                round_trip_friction_points=ROUND_TRIP_FRICTION_POINTS,
                commission_per_side_points=COMMISSION_PER_SIDE_POINTS,
                tax_per_exit_points=TAX_PER_EXIT_POINTS,
                commission_per_side_ntd=COMMISSION_PER_SIDE_NTD,
                tax_rate=FRICTION_TAX_RATE,
                point_value_ntd=POINT_VALUE_NTD,
            )
            return friction, SHARPE_PERIOD
        except Exception:
            return FrictionSettings(), "per_trade"
    try:
        from config import SHARPE_PERIOD as sharpe_period
    except Exception:
        sharpe_period = "per_trade"
    return friction, sharpe_period


def compute_performance_block(
    fills: list[FillAudit],
    daily_summaries: list[dict],
    friction: FrictionSettings,
    sharpe_period: str,
    *,
    initial_capital_points: float = 0.0,
) -> tuple[dict, dict]:
    fill_dicts = [asdict(f) for f in fills]
    performance = compute_performance_from_fills(
        fill_dicts,
        friction,
        sharpe_period=sharpe_period,
        initial_capital=initial_capital_points,
    )
    performance_aggregate = aggregate_daily_performance(
        daily_summaries, initial_capital=initial_capital_points
    )
    if not performance_aggregate.get("trade_count") and performance.get(
        "expectancy", {}
    ).get("trade_count"):
        performance_aggregate = {
            "trade_count": performance["expectancy"]["trade_count"],
            "total_pnl_gross": performance.get("total_pnl_gross", 0.0),
            "total_pnl_net": performance.get("total_pnl_net", 0.0),
            "win_rate": performance["expectancy"].get("win_rate"),
            "expectancy_per_trade_net": performance["expectancy"].get(
                "expectancy_per_trade_net"
            ),
            "max_drawdown_points": performance["drawdown"].get(
                "max_drawdown_points"
            ),
        }
    return performance, performance_aggregate


def compute_metrics(
    lines: list[str],
    *,
    quick_sl_sec: int = 5,
    friction: FrictionSettings | None = None,
    risk_budget: RiskBudgetSettings | None = None,
) -> dict:
    momentum_triggers = count_momentum_triggers(lines)
    audits, fills = parse_log_audits_and_fills(lines)
    entries = [a for a in audits if a.intent == "entry"]
    exits = [a for a in audits if a.intent == "exit"]
    rounds = compute_trade_rounds(audits, fills)
    completed = [r for r in rounds if r.exit_ts is not None]
    quick_sl_count, quick_sl_rate, quick_sl_examples = compute_quick_sl_metrics(
        rounds=rounds,
        fills=fills,
        quick_sl_sec=quick_sl_sec,
    )

    exit_reasons: dict[str, int] = {}
    for audit in exits:
        exit_reasons[audit.reason] = exit_reasons.get(audit.reason, 0) + 1

    cancel_counts = count_intent_cancelled(lines)
    daily_summaries = parse_daily_summaries(lines)
    tick_type = latest_tick_type_line(lines)

    conversion_rate = (
        len(entries) / momentum_triggers if momentum_triggers else None
    )
    cancel_rate = (
        cancel_counts["intent_cancelled"] / len(entries) if entries else None
    )
    open_cancel_rate = (
        cancel_counts["intent_cancelled_open_session"] / len(entries)
        if entries
        else None
    )

    near_miss = None
    if daily_summaries:
        near_miss = daily_summaries[-1].get("near_miss")

    friction, sharpe_period = resolve_friction_settings(friction)
    risk = resolve_risk_budget_settings(risk_budget)
    performance, performance_aggregate = compute_performance_block(
        fills,
        daily_summaries,
        friction,
        sharpe_period,
        initial_capital_points=risk.initial_capital_points,
    )
    cumulative_risk = compute_cumulative_risk_progression(
        daily_summaries,
        initial_capital=risk.initial_capital_points,
        max_acceptable_mdd=risk.max_acceptable_mdd_points,
    )
    slip = slippage_stats(fills)
    exp_by_reason = expectancy_by_reason(fills)

    return {
        "momentum_triggers": momentum_triggers,
        "entry_signals": len(entries),
        "exit_signals": len(exits),
        "momentum_to_entry_conversion": conversion_rate,
        "completed_rounds": len(completed),
        "open_rounds": len(rounds) - len(completed),
        f"quick_stop_loss_lt_{quick_sl_sec}s": quick_sl_count,
        f"quick_stop_loss_rate_lt_{quick_sl_sec}s": quick_sl_rate,
        "exit_reasons": exit_reasons,
        "slippage": slip,
        "expectancy_by_reason": exp_by_reason,
        "intent_cancelled": cancel_counts,
        "intent_cancel_rate": cancel_rate,
        "open_session_cancel_rate": open_cancel_rate,
        "tick_type": tick_type,
        "near_miss": near_miss,
        "daily_summaries": daily_summaries,
        "performance": performance,
        "performance_aggregate": performance_aggregate,
        "cumulative_risk": cumulative_risk,
        "fill_count": len(fills),
        "quick_stop_loss_examples": quick_sl_examples,
        "tuning_hints": build_tuning_hints(
            conversion_rate=conversion_rate,
            quick_sl_rate=quick_sl_rate,
            slippage=slip,
            expectancy=exp_by_reason,
            near_miss=near_miss,
            cancel_rate=open_cancel_rate,
            tick_type=tick_type,
            daily_summaries=daily_summaries,
            cumulative_risk=cumulative_risk,
        ),
    }


def build_tuning_hints(
    *,
    conversion_rate: float | None,
    quick_sl_rate: float | None,
    slippage: dict,
    expectancy: dict[str, dict],
    near_miss: dict | None,
    cancel_rate: float | None,
    tick_type: dict | None,
    daily_summaries: list[dict],
    cumulative_risk: dict | None = None,
) -> list[str]:
    """Rule-based hints for humans / AI — maps KPIs to candidate params."""
    hints: list[str] = []

    if quick_sl_rate is not None and quick_sl_rate > 0.30:
        hints.append(
            "quick_sl_rate>30% → 考慮放長 exit_grace_ticks / exit_grace_sec，"
            "或放寬 vwap_stop_points"
        )
    if conversion_rate is not None and conversion_rate < 0.10:
        hints.append(
            "動量→進場轉換率<10% → 檢查 near_miss.closest_vwap_distance 是否多數"
            "> entry_band_points；考慮放寬 entry_band_points 或 exhaustion_vol"
        )
    if near_miss:
        closest = near_miss.get("closest_vwap_distance")
        if closest is not None and closest > 2.0:
            hints.append(
                f"closest_vwap_distance={closest} > entry_band_points → pullback 常差一點進場"
            )
        if near_miss.get("blocked_vwap_only", 0) > near_miss.get("blocked_vol_only", 0):
            hints.append(
                "blocked_vwap_only 偏高 → 量能已枯竭(vol_dried_up)但價格未進 band；"
                "考慮 entry_band_points"
            )
        if near_miss.get("blocked_vol_only", 0) > near_miss.get("blocked_vwap_only", 0):
            hints.append(
                "blocked_vol_only 偏高 → 價格已進 band 但 vol_1s 仍 > exhaustion_vol；"
                "考慮 exhaustion_vol"
            )
        if near_miss.get("momentum_timeout", 0) > 0:
            hints.append(
                "momentum_timeout>0 → 180s 內未等到 pullback；策略設計偏嚴或波動太快"
            )

    entry_med = slippage.get("entry_median")
    if entry_med is not None and entry_med > 2.0:
        hints.append(
            f"進場滑價中位數 {entry_med} 點 > 2 → 檢查流動性；勿輕易放大 ioc_slippage_points"
        )
    if cancel_rate is not None and cancel_rate > 0.20:
        hints.append(
            "開盤 IOC 取消率>20% → 預期內保護；維持 ioc_slippage_points，勿為成交率放大讓價"
        )
    if tick_type and tick_type.get("type0_pct", 0) > 40:
        hints.append(
            f"tick_type0 占比 {tick_type['type0_pct']}% 偏高 → buy/sell ratio 推斷品質可能失真"
        )

    for reason, stats in expectancy.items():
        if stats["count"] >= 2 and stats["avg_pnl"] < 0:
            hints.append(
                f"exit_reason={reason} 平均 PnL {stats['avg_pnl']} 為負 → 檢查對應出場參數"
            )

    if daily_summaries:
        last = daily_summaries[-1]
        op = last.get("operational", {})
        if op.get("lock_wait_over_50ms", 0) > 0:
            hints.append(
                f"lock_wait_over_50ms={op['lock_wait_over_50ms']} → 檢查 callback 熱路徑負載"
            )
        atr_min = op.get("atr_min")
        params = last.get("params", {})
        min_atr = params.get("min_atr_threshold")
        if atr_min is not None and min_atr is not None and atr_min < min_atr:
            hints.append(
                f"當日 atr_min={atr_min} < min_atr_threshold={min_atr} → 可能整天無交易"
            )

    if cumulative_risk:
        budget = cumulative_risk.get("max_acceptable_mdd_points")
        cum_mdd = cumulative_risk.get("cumulative_max_drawdown_points")
        used = cumulative_risk.get("budget_used_pct")
        if (
            budget is not None
            and budget > 0
            and cum_mdd is not None
            and cumulative_risk.get("budget_breached")
        ):
            hints.append(
                f"累積 MDD {cum_mdd} 點 > 可承受預算 {budget} 點 → 暫停調參/評估是否縮倉或停玩"
            )
        elif used is not None and used >= 80.0:
            hints.append(
                f"累積 MDD 已用預算 {used:.1f}%（{cum_mdd}/{budget} 點）→ 接近風險上限"
            )

    if not hints:
        hints.append("無明顯調參警示；繼續累積樣本")
    return hints


def format_report(metrics: dict, *, quick_sl_sec: int = 5) -> str:
    conv = metrics["momentum_to_entry_conversion"]
    qsl_rate = metrics[f"quick_stop_loss_rate_lt_{quick_sl_sec}s"]
    conv_text = f"{conv:.1%}" if conv is not None else "N/A"
    qsl_text = f"{qsl_rate:.1%}" if qsl_rate is not None else "N/A"

    lines = [
        "=== UAT Report ===",
        f"動量觸發數:           {metrics['momentum_triggers']}",
        f"進場 signal 數:       {metrics['entry_signals']}",
        f"出場 signal 數:       {metrics['exit_signals']}",
        f"成交回報 FILL 數:     {metrics['fill_count']}",
        f"動量→進場轉換率:      {conv_text}",
        f"完整 round-trip:      {metrics['completed_rounds']}",
        f"未平倉 round:         {metrics['open_rounds']}",
        (
            f"秒停損 (<{quick_sl_sec}s): "
            f"{metrics[f'quick_stop_loss_lt_{quick_sl_sec}s']} ({qsl_text})"
        ),
    ]

    slip = metrics.get("slippage", {})
    if slip.get("entry_count") or slip.get("exit_count"):
        lines.append("滑價 (adverse pts vs signal):")
        lines.append(
            f"  進場 median={slip.get('entry_median')} p90={slip.get('entry_p90')} "
            f"n={slip.get('entry_count')}"
        )
        lines.append(
            f"  出場 median={slip.get('exit_median')} p90={slip.get('exit_p90')} "
            f"n={slip.get('exit_count')}"
        )

    exp = metrics.get("expectancy_by_reason", {})
    if exp:
        lines.append("期望值 by exit_reason (點數, gross):")
        for reason, stats in sorted(exp.items()):
            lines.append(
                f"  {reason}: n={stats['count']} avg={stats['avg_pnl']} "
                f"total={stats['total_pnl']}"
            )

    perf = metrics.get("performance", {})
    exp_all = perf.get("expectancy", {})
    if exp_all.get("trade_count"):
        lines.append("生存指標 (round-trip):")
        wr = exp_all.get("win_rate")
        wr_text = f"{wr:.1%}" if wr is not None else "N/A"
        lines.append(
            f"  筆數={exp_all['trade_count']} 勝率={wr_text} "
            f"盈虧比={exp_all.get('payoff_ratio')}"
        )
        lines.append(
            f"  期望值 gross={exp_all.get('expectancy_per_trade_gross')} "
            f"net={exp_all.get('expectancy_per_trade_net')} "
            f"(摩擦/筆={exp_all.get('friction_per_trade')})"
        )
        dd = perf.get("drawdown", {})
        lines.append(
            f"  最大回撤 net={dd.get('max_drawdown_points')} 點 "
            f"({dd.get('max_drawdown_pct')}%)"
        )
        risk = perf.get("risk_adjusted", {})
        lines.append(
            f"  Sharpe={risk.get('sharpe')} Sortino={risk.get('sortino')} "
            f"({risk.get('return_period')})"
        )
        lines.append(
            f"  累計 PnL gross={perf.get('total_pnl_gross')} "
            f"net={perf.get('total_pnl_net')}"
        )

    agg = metrics.get("performance_aggregate", {})
    cum_risk = metrics.get("cumulative_risk", {})
    if cum_risk.get("daily_progression") or agg.get("day_count", 0) > 0:
        lines.append("風險預算（累進 MDD，跨日）:")
        cap = cum_risk.get("initial_capital_points")
        budget = cum_risk.get("max_acceptable_mdd_points")
        lines.append(
            f"  本金={cap} 點 | 可承受累積 MDD≤{budget} 點"
        )
        cum_mdd = cum_risk.get("cumulative_max_drawdown_points")
        used = cum_risk.get("budget_used_pct")
        headroom = cum_risk.get("budget_headroom_points")
        status = "超標" if cum_risk.get("budget_breached") else "OK"
        used_text = f"{used:.1f}%" if used is not None else "N/A"
        lines.append(
            f"  累積淨利={cum_risk.get('cumulative_pnl_net')} 點 | "
            f"累積 MDD={cum_mdd} 點 | 預算使用率={used_text} | "
            f"剩餘={headroom} 點 | {status}"
        )
        for row in cum_risk.get("daily_progression", []):
            lines.append(
                f"  {row.get('date')} | 日淨利={row.get('daily_pnl_net')} | "
                f"權益={row.get('equity')} | 累積MDD={row.get('cumulative_max_drawdown_points')}"
            )
    elif cum_risk.get("max_acceptable_mdd_points") is not None:
        dd = perf.get("drawdown", {}) if perf else {}
        cum_mdd = dd.get("max_drawdown_points")
        budget = cum_risk.get("max_acceptable_mdd_points")
        breached = (
            cum_mdd is not None
            and budget is not None
            and budget > 0
            and cum_mdd > budget
        )
        lines.append("風險預算（單段 round-trip 累進 MDD）:")
        lines.append(
            f"  MDD={cum_mdd} 點 | 預算≤{budget} 點 | "
            f"{'超標' if breached else 'OK'}"
        )

    cancel = metrics.get("intent_cancelled", {})
    if cancel.get("intent_cancelled"):
        lines.append(
            f"IOC 取消: total={cancel.get('intent_cancelled', 0)} "
            f"開盤窗={cancel.get('intent_cancelled_open_session', 0)}"
        )
        ocr = metrics.get("open_session_cancel_rate")
        if ocr is not None:
            lines.append(f"  開盤取消率: {ocr:.1%}")

    tick_type = metrics.get("tick_type")
    if tick_type:
        lines.append(
            f"tick_type0 占比: {tick_type.get('type0_pct')}% "
            f"(n={tick_type.get('total')})"
        )

    near_miss = metrics.get("near_miss")
    if near_miss:
        lines.append("Near-miss (pullback 未進場):")
        lines.append(
            f"  episodes={near_miss.get('momentum_episodes')} "
            f"timeout={near_miss.get('momentum_timeout')} "
            f"closest_vwap_dist={near_miss.get('closest_vwap_distance')}"
        )
        lines.append(
            f"  blocked_vwap_only={near_miss.get('blocked_vwap_only')} "
            f"blocked_vol_only={near_miss.get('blocked_vol_only')} "
            f"blocked_both={near_miss.get('blocked_both')}"
        )

    if metrics["exit_reasons"]:
        lines.append("出場 reason 分布:")
        for reason, count in sorted(metrics["exit_reasons"].items()):
            lines.append(f"  {reason or '(empty)'}: {count}")

    hints = metrics.get("tuning_hints", [])
    if hints:
        lines.append("調參提示 (rule-based):")
        for hint in hints:
            lines.append(f"  - {hint}")

    return "\n".join(lines)


def format_trend_report(summaries: list[dict]) -> str:
    if not summaries:
        return "無 DAILY_SUMMARY 行可分析"

    lines = ["=== Multi-day Trend (DAILY_SUMMARY) ==="]
    for s in summaries:
        date = s.get("date", "?")
        sig = s.get("signals", {})
        fills = s.get("fills", {})
        qsl = s.get("quick_stop_loss", {})
        pnl = s.get("pnl", {})
        conv = sig.get("momentum_to_entry_conversion")
        conv_text = f"{conv:.1%}" if conv is not None else "N/A"
        qsl_rate = qsl.get("rate")
        qsl_text = f"{qsl_rate:.1%}" if qsl_rate is not None else "N/A"
        lines.append(
            f"{date} | conv={conv_text} | entries={sig.get('entry_signals')} | "
            f"quick_sl={qsl_text} | pnl={pnl.get('daily_pnl_points')} | "
            f"entry_slip_med={fills.get('entry_slippage_median')}"
        )
    return "\n".join(lines)


def read_log_lines(paths: list[Path]) -> list[str]:
    lines: list[str] = []
    for path in paths:
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze trading-app log for UAT metrics."
    )
    parser.add_argument(
        "log_files",
        nargs="+",
        type=Path,
        help="Strategy log file(s); multiple files merge for multi-day trend",
    )
    parser.add_argument(
        "--quick-sl-sec",
        type=int,
        default=5,
        help="Seconds threshold for quick stop-loss (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metrics as JSON",
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help="Show multi-day trend from DAILY_SUMMARY lines only",
    )
    parser.add_argument(
        "--summaries-only",
        action="store_true",
        help="Alias for --trend",
    )
    args = parser.parse_args(argv)

    for path in args.log_files:
        if not path.is_file():
            print(f"找不到 log 檔: {path}", file=sys.stderr)
            return 1

    lines = read_log_lines(args.log_files)
    summaries = parse_daily_summaries(lines)

    if args.trend or args.summaries_only:
        print(format_trend_report(summaries))
        return 0

    metrics = compute_metrics(lines, quick_sl_sec=args.quick_sl_sec)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(format_report(metrics, quick_sl_sec=args.quick_sl_sec))
        if len(summaries) > 1:
            print()
            print(format_trend_report(summaries))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
