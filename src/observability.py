"""Structured observability: FILL_AUDIT, near-miss counters, DAILY_SUMMARY."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from config import settings
from reporting.performance_metrics import (
    aggregate_daily_performance,
    compute_performance_from_fills,
    friction_settings_from_mapping,
)


@dataclass
class FillAudit:
    intent: str
    direction: str
    signal_price: float
    fill_price: float
    slippage_pts: float
    limit_price: float
    slippage_vs_limit_pts: float
    order_id: str
    ts: int
    hold_sec: int = 0
    pnl_points: float = 0.0
    exit_reason: str = ""
    ioc_slippage_allowed: int = 0


def format_fill_audit(audit: FillAudit) -> str:
    return json.dumps(asdict(audit), ensure_ascii=False, separators=(",", ":"))


def compute_adverse_slippage(
    signal_price: float, fill_price: float, *, is_buy: bool
) -> float:
    """Positive = worse for trader (paid more on buy / received less on sell)."""
    if is_buy:
        return round(fill_price - signal_price, 2)
    return round(signal_price - fill_price, 2)


def compute_limit_price(
    signal_price: float, *, is_buy: bool, ioc_slippage: int
) -> float:
    if is_buy:
        return signal_price + ioc_slippage
    return signal_price - ioc_slippage


@dataclass
class NearMissStats:
    momentum_episodes: int = 0
    momentum_timeout: int = 0
    blocked_vwap_only: int = 0
    blocked_vol_only: int = 0
    blocked_both: int = 0
    closest_vwap_distance: float | None = None


class NearMissTracker:
    """Accumulate pullback near-miss stats during momentum episodes (no per-tick log)."""

    def __init__(self) -> None:
        self.stats = NearMissStats()
        self._episode_active = False

    def on_momentum_start(self) -> None:
        self.stats.momentum_episodes += 1
        self._episode_active = True

    def on_momentum_end(self, *, timeout: bool) -> None:
        if timeout:
            self.stats.momentum_timeout += 1
        self._episode_active = False

    def on_pullback_tick(
        self,
        price: float,
        vwap: float,
        *,
        near_vwap: bool,
        vol_dried_up: bool,
    ) -> None:
        """Classify pullback ticks that did NOT fire entry.

        Aligns with original (flat man.py) semantics: entry requires ``near_vwap and vol_dried_up`` where
        ``vol_dried_up`` means ``vol_1s <= EXHAUSTION_VOL`` (volume exhausted /
        dried up — a pass, not a rejection).

        Truth table (near_vwap, vol_dried_up):
          T, T → entry fires; not a near-miss (return)
          T, F → blocked_vol_only  (in band, volume still too high)
          F, T → blocked_vwap_only (volume ok, price not in band)
          F, F → blocked_both
        """
        if not self._episode_active:
            return
        dist = abs(price - vwap)
        closest = self.stats.closest_vwap_distance
        if closest is None or dist < closest:
            self.stats.closest_vwap_distance = round(dist, 2)
        if near_vwap and vol_dried_up:
            return
        if near_vwap and not vol_dried_up:
            self.stats.blocked_vol_only += 1
        elif not near_vwap and vol_dried_up:
            self.stats.blocked_vwap_only += 1
        else:
            self.stats.blocked_both += 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.stats)


@dataclass
class DailyObservability:
    """In-memory daily counters; flushed as one DAILY_SUMMARY line."""

    near_miss: NearMissTracker = field(default_factory=NearMissTracker)
    momentum_triggers: int = 0
    entry_signals: int = 0
    exit_signals: int = 0
    fills: list[dict[str, Any]] = field(default_factory=list)
    pnl_by_reason: dict[str, dict[str, float]] = field(default_factory=dict)
    intent_cancelled: int = 0
    intent_cancelled_open_session: int = 0
    lock_wait_max_ms: float = 0.0
    lock_wait_over_50ms: int = 0
    no_tick_resubscribe: int = 0
    tick_type_counts: dict[str, int] = field(
        default_factory=lambda: {"0": 0, "1": 0, "2": 0}
    )
    tick_type_inferred_counts: dict[str, int] = field(
        default_factory=lambda: {"1": 0, "2": 0}
    )
    atr_min: float | None = None
    atr_max: float | None = None
    daily_pnl: float = 0.0
    consecutive_loss: int = 0
    trend_vetoes: int = 0
    _entry_fill_ts: int = 0
    _entry_signal_price: float = 0.0

    def record_momentum_trigger(self) -> None:
        self.momentum_triggers += 1
        self.near_miss.on_momentum_start()

    def record_momentum_timeout(self) -> None:
        self.near_miss.on_momentum_end(timeout=True)

    def record_momentum_entry(self) -> None:
        self.near_miss.on_momentum_end(timeout=False)

    def record_trend_veto(self) -> None:
        """Count a pullback entry that was blocked by the HTF trend filter.

        This is critical for calibrating min_strength / trend_filter_enabled.
        The actual SIGNAL_AUDIT with reason="trend_veto" is emitted by the
        strategy at veto time so that uat_report can see forward returns etc.
        """
        self.trend_vetoes += 1

    def record_pullback_tick(
        self,
        price: float,
        vwap: float,
        *,
        near_vwap: bool,
        vol_dried_up: bool,
    ) -> None:
        self.near_miss.on_pullback_tick(
            price, vwap, near_vwap=near_vwap, vol_dried_up=vol_dried_up
        )

    def record_entry_signal(self) -> None:
        self.entry_signals += 1

    def record_exit_signal(self) -> None:
        self.exit_signals += 1

    def record_atr(self, atr: float) -> None:
        if atr <= 0:
            return
        if self.atr_min is None or atr < self.atr_min:
            self.atr_min = round(atr, 2)
        if self.atr_max is None or atr > self.atr_max:
            self.atr_max = round(atr, 2)

    def record_lock_wait(self, wait_ms: float) -> None:
        if wait_ms > self.lock_wait_max_ms:
            self.lock_wait_max_ms = round(wait_ms, 3)
        if wait_ms > 50:
            self.lock_wait_over_50ms += 1

    def record_intent_cancelled(self, tag: str) -> None:
        self.intent_cancelled += 1
        if tag == "intent_cancelled_open_session":
            self.intent_cancelled_open_session += 1

    def record_no_tick_resubscribe(self) -> None:
        self.no_tick_resubscribe += 1

    def snapshot_tick_types(self, counts: Mapping[int, int]) -> None:
        for key in (0, 1, 2):
            self.tick_type_counts[str(key)] = int(counts.get(key, 0))

    def record_tick_type(self, original: int, effective: int) -> None:
        """Track original vs price-inferred tick_type for UAT debug."""
        if original == 0 and effective in (1, 2):
            self.tick_type_inferred_counts[str(effective)] = (
                self.tick_type_inferred_counts.get(str(effective), 0) + 1
            )

    def record_fill(
        self,
        *,
        intent: str,
        direction: str,
        signal_price: float,
        fill_price: float,
        is_buy: bool,
        limit_price: float,
        order_id: str,
        ts: int,
        ioc_slippage_allowed: int,
        exit_reason: str = "",
        pnl_points: float = 0.0,
        hold_sec: int = 0,
    ) -> FillAudit:
        slippage_pts = compute_adverse_slippage(
            signal_price, fill_price, is_buy=is_buy
        )
        slippage_vs_limit = compute_adverse_slippage(
            limit_price, fill_price, is_buy=is_buy
        )
        audit = FillAudit(
            intent=intent,
            direction=direction,
            signal_price=round(signal_price, 1),
            fill_price=round(fill_price, 1),
            slippage_pts=slippage_pts,
            limit_price=round(limit_price, 1),
            slippage_vs_limit_pts=slippage_vs_limit,
            order_id=order_id,
            ts=ts,
            hold_sec=hold_sec,
            pnl_points=round(pnl_points, 2),
            exit_reason=exit_reason,
            ioc_slippage_allowed=ioc_slippage_allowed,
        )
        self.fills.append(asdict(audit))
        if intent == "entry":
            self._entry_fill_ts = ts
            self._entry_signal_price = signal_price
        elif intent == "exit":
            if exit_reason:
                bucket = self.pnl_by_reason.setdefault(
                    exit_reason, {"count": 0, "total_pnl": 0.0}
                )
                bucket["count"] += 1
                bucket["total_pnl"] = round(bucket["total_pnl"] + pnl_points, 2)
            self._entry_fill_ts = 0
            self._entry_signal_price = 0.0
        return audit

    def update_risk_state(self, daily_pnl: float, consecutive_loss: int) -> None:
        self.daily_pnl = round(daily_pnl, 2)
        self.consecutive_loss = consecutive_loss

    def build_summary(
        self,
        trade_date: str,
        *,
        quick_sl_sec: int = 5,
        runtime_config: Any = None,
    ) -> dict[str, Any]:
        entry_fills = [f for f in self.fills if f["intent"] == "entry"]
        exit_fills = [f for f in self.fills if f["intent"] == "exit"]
        quick_sl = [
            f
            for f in exit_fills
            if f["exit_reason"] in ("stop_loss", "stop_loss_vwap")
            and f["hold_sec"] < quick_sl_sec
        ]
        completed_exits = len(exit_fills)
        conversion = (
            self.entry_signals / self.momentum_triggers
            if self.momentum_triggers
            else None
        )
        tick_total = sum(self.tick_type_counts.values())
        type0_pct = (
            100.0 * self.tick_type_counts.get("0", 0) / tick_total
            if tick_total
            else None
        )
        inferred_total = sum(self.tick_type_inferred_counts.values())
        entry_slips = [f["slippage_pts"] for f in entry_fills]
        exit_slips = [f["slippage_pts"] for f in exit_fills]
        pnl_by_reason = {
            reason: {
                "count": int(v["count"]),
                "total_pnl": v["total_pnl"],
                "avg_pnl": round(v["total_pnl"] / v["count"], 2)
                if v["count"]
                else 0.0,
            }
            for reason, v in self.pnl_by_reason.items()
        }
        friction = friction_settings_from_mapping(
            {
                "enabled": settings.friction_enabled,
                "mode": settings.friction_mode,
                "round_trip_friction_points": settings.round_trip_friction_points,
                "commission_per_side_points": settings.commission_per_side_points,
                "tax_per_exit_points": settings.tax_per_exit_points,
                "commission_per_side_ntd": settings.commission_per_side_ntd,
                "tax_rate": settings.friction_tax_rate,
                "point_value_ntd": settings.point_value_ntd,
            }
        )
        performance = compute_performance_from_fills(
            self.fills, friction, sharpe_period=settings.sharpe_period
        )
        return {
            "date": trade_date,
            "params": build_config_snapshot(runtime_config),
            "signals": {
                "momentum_triggers": self.momentum_triggers,
                "entry_signals": self.entry_signals,
                "exit_signals": self.exit_signals,
                "momentum_to_entry_conversion": conversion,
            },
            "fills": {
                "entry_count": len(entry_fills),
                "exit_count": len(exit_fills),
                "entry_slippage_median": _median(entry_slips),
                "entry_slippage_p90": _percentile(entry_slips, 90),
                "exit_slippage_median": _median(exit_slips),
                "exit_slippage_p90": _percentile(exit_slips, 90),
            },
            "pnl": {
                "daily_pnl_points": self.daily_pnl,
                "by_reason": pnl_by_reason,
            },
            "performance": performance,
            "quick_stop_loss": {
                "threshold_sec": quick_sl_sec,
                "count": len(quick_sl),
                "rate": len(quick_sl) / completed_exits if completed_exits else None,
            },
            "near_miss": self.near_miss.to_dict(),
            "operational": {
                "intent_cancelled": self.intent_cancelled,
                "intent_cancelled_open_session": self.intent_cancelled_open_session,
                "intent_cancel_rate": (
                    self.intent_cancelled / self.entry_signals
                    if self.entry_signals
                    else None
                ),
                "open_session_cancel_rate": (
                    self.intent_cancelled_open_session / self.entry_signals
                    if self.entry_signals
                    else None
                ),
                "tick_type0_pct": round(type0_pct, 2) if type0_pct is not None else None,
                "tick_type_inferred": dict(self.tick_type_inferred_counts),
                "tick_type_inferred_total": inferred_total,
                "lock_wait_max_ms": self.lock_wait_max_ms,
                "lock_wait_over_50ms": self.lock_wait_over_50ms,
                "no_tick_resubscribe": self.no_tick_resubscribe,
                "atr_min": self.atr_min,
                "atr_max": self.atr_max,
            },
        }

    def reset(self) -> None:
        self.near_miss = NearMissTracker()
        self.momentum_triggers = 0
        self.entry_signals = 0
        self.exit_signals = 0
        self.fills.clear()
        self.pnl_by_reason.clear()
        self.intent_cancelled = 0
        self.intent_cancelled_open_session = 0
        self.lock_wait_max_ms = 0.0
        self.lock_wait_over_50ms = 0
        self.no_tick_resubscribe = 0
        self.tick_type_counts = {"0": 0, "1": 0, "2": 0}
        self.tick_type_inferred_counts = {"1": 0, "2": 0}
        self.atr_min = None
        self.atr_max = None
        self.daily_pnl = 0.0
        self.consecutive_loss = 0
        self._entry_fill_ts = 0
        self._entry_signal_price = 0.0


def build_config_snapshot(runtime_config: Any = None) -> dict[str, Any]:
    """Strategy params at summary time — Settings + instance overlay."""
    import config as cfg
    from core.runtime_config import default_runtime_config

    cfg_rt = runtime_config or default_runtime_config()
    snap = asdict(cfg.settings)
    snap.pop("config_path", None)
    snap.update(cfg_rt.config_snapshot_fields())
    for key in (
        "session_start",
        "session_end",
        "session_flatten_time",
        "session_force_flatten_time",
    ):
        value = snap.get(key)
        if hasattr(value, "strftime"):
            snap[key] = value.strftime("%H:%M")
    return snap


def format_daily_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    rank = (pct / 100) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    value = ordered[low] * (1 - weight) + ordered[high] * weight
    return round(value, 2)
