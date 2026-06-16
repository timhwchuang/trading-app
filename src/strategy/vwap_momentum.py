"""VWAP momentum entry/exit decision logic."""

from __future__ import annotations

import datetime
import logging
from typing import Callable, Optional, TYPE_CHECKING

from core.audit.signal_audit import SignalAudit, format_signal_audit
from core.types import (
    MarketSnapshot,
    MomentumState,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    StrategySideEffects,
)
from exchange_time import is_at_or_after
from strategy.base import BaseStrategy
from strategy.params import StrategyParams
from strategy.trend import (
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    trend_allows_entry,
)

if TYPE_CHECKING:
    from observability import DailyObservability

logger = logging.getLogger(__name__)

MOMENTUM_TIMEOUT_SEC = 180


class VWAPMomentumStrategy(BaseStrategy):
    """VWAP Momentum 策略決策實作（實現 Strategy interface）。

    策略相關參數已封裝在此類別內，透過 `self.params` (StrategyParams) 存取。
    所有決策邏輯（進場、出場、停損、Phase 6 濾網等）都只依賴傳入的 snapshots 與 self.params，
    不直接依賴全域 config（sweep patch 機制除外，屬於測試基礎設施）。
    """

    def __init__(
        self,
        params: StrategyParams | None = None,
        obs: Optional[DailyObservability] = None,
    ) -> None:
        super().__init__()
        self.params = params or StrategyParams.from_config()
        self.obs = obs

    def reset(self) -> None:
        super().reset()

    def reset_momentum(self) -> None:
        self.reset()

    def activate_momentum(self, direction: str, price: float, ts: int) -> None:
        self.momentum = MomentumState(
            active=True,
            direction=direction,
            peak=price,
            trigger_time=ts,
        )
        if self.obs is not None:
            self.obs.record_momentum_trigger()
        logger.info("MOMENTUM %s 突破 | 價格 %.1f", direction, price)

    def update_momentum_peak(self, price: float) -> None:
        if self.momentum.direction == "Long":
            self.momentum.peak = max(self.momentum.peak, price)
        elif self.momentum.direction == "Short":
            self.momentum.peak = min(self.momentum.peak, price)

    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
        vol_threshold: tuple[float, float, float],
        *,
        session_force_flatten_time: datetime.time,
        max_daily_loss_points: float,
        on_daily_loss_block: Callable[[], None] | None = None,
    ) -> tuple[Optional[OrderSignal], StrategySideEffects]:
        effects = StrategySideEffects()

        if not risk.api_connected:
            if position.has_position:
                if risk.force_flatten:
                    return self.session_force_flatten_signal(
                        market, position, session_force_flatten_time
                    )
                return self.manage_exit(market, position)
            return None, effects

        if risk.is_pending or risk.exit_pending:
            return None, effects
        if risk.cooldown_active:
            return None, effects
        if not risk.in_trading_session:
            return None, effects

        if (
            risk.daily_pnl <= -max_daily_loss_points
            and not risk.block_new_entry
        ):
            effects.block_new_entry = True
            if on_daily_loss_block is not None:
                on_daily_loss_block()

        if position.has_position:
            if risk.force_flatten:
                return self.session_force_flatten_signal(
                    market, position, session_force_flatten_time
                )
            return self.manage_exit(market, position)

        if risk.after_flatten_time:
            return None, effects
        if risk.block_new_entry:
            return None, effects
        if risk.consecutive_loss >= self.params.max_consecutive_loss:
            return None, effects
        if market.current_atr < self.params.min_atr_threshold:
            return None, effects

        if not self.momentum.active:
            signal = self._try_activate_momentum(market, vol_threshold)
            return signal, effects

        if market.ts - self.momentum.trigger_time > MOMENTUM_TIMEOUT_SEC:
            if self.obs is not None:
                self.obs.record_momentum_timeout()
            self.reset_momentum()
            return None, effects

        return self._try_pullback_entry(market, vol_threshold), effects

    def _try_activate_momentum(
        self,
        market: MarketSnapshot,
        vol_threshold: tuple[float, float, float],
    ) -> None:
        base_vol, multiplier, threshold = vol_threshold
        buy_ratio = (
            market.buy_vol_1s / market.vol_1s if market.vol_1s > 0 else 0
        )
        sell_ratio = (
            market.sell_vol_1s / market.vol_1s if market.vol_1s > 0 else 0
        )

        if market.vol_1s >= threshold and buy_ratio >= self.params.momentum_buy_ratio:
            logger.info(
                "MOMENTUM 量能通過 | dir=Long vol_1s=%d base=%.0f mult=%.2f "
                "threshold=%.0f buy_ratio=%.2f",
                market.vol_1s,
                base_vol,
                multiplier,
                threshold,
                buy_ratio,
            )
            self.activate_momentum("Long", market.price, market.ts)
        elif (
            market.vol_1s >= threshold
            and sell_ratio >= self.params.momentum_sell_ratio
        ):
            logger.info(
                "MOMENTUM 量能通過 | dir=Short vol_1s=%d base=%.0f mult=%.2f "
                "threshold=%.0f sell_ratio=%.2f",
                market.vol_1s,
                base_vol,
                multiplier,
                threshold,
                sell_ratio,
            )
            self.activate_momentum("Short", market.price, market.ts)
        return None

    def _try_pullback_entry(
        self,
        market: MarketSnapshot,
        vol_threshold: tuple[float, float, float],
    ) -> Optional[OrderSignal]:
        near_vwap = abs(market.price - market.vwap) <= self.params.entry_band_points
        exhausted = market.vol_1s <= self.params.exhaustion_vol
        if self.obs is not None:
            self.obs.record_pullback_tick(
                market.price,
                market.vwap,
                near_vwap=near_vwap,
                vol_dried_up=exhausted,
            )

        if not (near_vwap and exhausted):
            return None

        if not trend_allows_entry(
            enabled=self.params.trend_filter_enabled,
            trend_dir=market.trend_dir,
            momentum_dir=self.momentum.direction,
        ):
            # Vetoed by HTF trend filter. Record for calibration.
            # Critical: we emit a SIGNAL_AUDIT with reason="trend_veto" so that
            # uat_report / performance analysis can see the blocked candidates
            # and (by looking at subsequent price action) judge if the filter
            # actually improved expectancy. Without this, min_strength cannot
            # be honestly tuned.
            if self.obs is not None:
                self.obs.record_trend_veto()

            direction = self.momentum.direction
            audit_dir = "Buy" if direction == "Long" else "Sell"
            buy_ratio = (
                market.buy_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
            )
            sell_ratio = (
                market.sell_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
            )
            veto_audit = SignalAudit(
                intent="entry",
                direction=audit_dir,
                price=market.price,
                ts=market.ts,
                vol_1s=market.vol_1s,
                buy_ratio=round(buy_ratio, 4),
                sell_ratio=round(sell_ratio, 4),
                atr=round(market.current_atr, 2),
                vwap=round(market.vwap, 1),
                reason="trend_veto",
                trend_dir=market.trend_dir,
                trend_strength=market.trend_strength,
            )
            logging.getLogger(__name__).info(
                "SIGNAL_AUDIT %s", format_signal_audit(veto_audit)
            )
            return None

        if self.obs is not None:
            self.obs.record_momentum_entry()

        direction = self.momentum.direction
        action = "Buy" if direction == "Long" else "Sell"
        audit_dir = "Buy" if direction == "Long" else "Sell"
        base_vol, multiplier, threshold = vol_threshold
        return OrderSignal(
            action,
            1,
            market.price,
            "entry",
            exchange_ts=market.ts,
            audit=self.build_entry_audit(
                market, audit_dir, multiplier, threshold
            ),
        )

    def build_entry_audit(
        self,
        market: MarketSnapshot,
        direction: str,
        multiplier: float,
        vol_threshold: float,
    ) -> SignalAudit:
        buy_ratio = (
            market.buy_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
        )
        sell_ratio = (
            market.sell_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
        )
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=market.price,
            ts=market.ts,
            vol_1s=market.vol_1s,
            buy_ratio=round(buy_ratio, 4),
            sell_ratio=round(sell_ratio, 4),
            atr=round(market.current_atr, 2),
            multiplier=multiplier,
            vol_threshold=round(vol_threshold, 1),
            vwap=round(market.vwap, 1),
            reason="pullback",
            trend_dir=market.trend_dir,
            trend_strength=market.trend_strength,
        )

    def build_exit_audit(
        self,
        market: MarketSnapshot,
        direction: str,
        reason: str,
        *,
        trail_points_used: float = 0.0,
    ) -> SignalAudit:
        return SignalAudit(
            intent="exit",
            direction=direction,
            price=market.price,
            ts=market.ts,
            atr=round(market.current_atr, 2),
            vwap=round(market.vwap, 1),
            reason=reason,
            trail_points_used=round(trail_points_used, 2),
        )

    def _effective_trail_points(self, atr: float) -> float:
        if not self.params.atr_trailing_enabled:
            return self.params.trail_points
        return dynamic_trail_points(
            atr,
            floor=self.params.trail_points_floor,
            atr_k=self.params.trail_atr_k,
        )

    def _effective_vwap_stop_distance(self, atr: float) -> float:
        if not self.params.atr_vwap_stop_enabled:
            return self.params.vwap_stop_points
        return dynamic_vwap_stop_distance(
            atr,
            floor=self.params.vwap_stop_points_floor,
            atr_k=self.params.vwap_stop_atr_k,
        )

    def _in_exit_grace_period(self, ts: int, position: PositionSnapshot) -> bool:
        if position.ticks_since_entry < self.params.exit_grace_ticks:
            return True
        if position.entry_exchange_ts <= 0:
            return False
        return (ts - position.entry_exchange_ts) < self.params.exit_grace_sec

    def _stop_loss_hit(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        *,
        is_long: bool,
    ) -> tuple[bool, str]:
        vwap_stop = self._effective_vwap_stop_distance(market.current_atr)
        if is_long:
            hard_hit = market.price <= position.entry_price - self.params.hard_stop_points
            vwap_hit = market.price <= market.vwap - vwap_stop
        else:
            hard_hit = market.price >= position.entry_price + self.params.hard_stop_points
            vwap_hit = market.price >= market.vwap + vwap_stop

        if self._in_exit_grace_period(market.ts, position):
            return (hard_hit, "stop_loss") if hard_hit else (False, "")

        if hard_hit:
            return True, "stop_loss"
        if vwap_hit:
            return True, "stop_loss_vwap"
        return False, ""

    def manage_exit(
        self, market: MarketSnapshot, position: PositionSnapshot
    ) -> tuple[Optional[OrderSignal], StrategySideEffects]:
        trail_pts = self._effective_trail_points(market.current_atr)
        if position.position_dir == "Long":
            sl_hit, sl_reason = self._stop_loss_hit(
                market, position, is_long=True
            )
            tp_hit = market.price >= position.entry_price + self.params.fixed_tp_points
            trail_hit = market.price <= position.trailing_peak - trail_pts
            if sl_hit or tp_hit or trail_hit:
                reason = (
                    sl_reason
                    if sl_hit
                    else "take_profit"
                    if tp_hit
                    else "trailing_stop"
                )
                return (
                    OrderSignal(
                        "Sell",
                        1,
                        market.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market, "Sell", reason, trail_points_used=trail_pts
                        ),
                    ),
                    StrategySideEffects(),
                )
        elif position.position_dir == "Short":
            sl_hit, sl_reason = self._stop_loss_hit(
                market, position, is_long=False
            )
            tp_hit = market.price <= position.entry_price - self.params.fixed_tp_points
            trail_hit = market.price >= position.trailing_peak + trail_pts
            if sl_hit or tp_hit or trail_hit:
                reason = (
                    sl_reason
                    if sl_hit
                    else "take_profit"
                    if tp_hit
                    else "trailing_stop"
                )
                return (
                    OrderSignal(
                        "Buy",
                        1,
                        market.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market, "Buy", reason, trail_points_used=trail_pts
                        ),
                    ),
                    StrategySideEffects(),
                )
        return None, StrategySideEffects()

    def session_force_flatten_signal(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        session_force_flatten_time: datetime.time,
    ) -> tuple[Optional[OrderSignal], StrategySideEffects]:
        action = "Sell" if position.position_dir == "Long" else "Buy"
        logger.warning(
            "收盤強制平倉 | %s @ %.1f | force_flatten_time=%s",
            position.position_dir,
            market.price,
            session_force_flatten_time.strftime("%H:%M"),
        )
        return (
            OrderSignal(
                action,
                1,
                market.price,
                "exit",
                exchange_ts=market.ts,
                slippage_points=self.params.flatten_slippage_points,
                audit=self.build_exit_audit(
                    market, action, "session_force_flatten"
                ),
            ),
            StrategySideEffects(),
        )
