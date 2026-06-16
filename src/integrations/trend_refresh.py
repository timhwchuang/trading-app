"""TrendRefreshPort adapter wrapping strategy_vwap_momentum.trend."""

from __future__ import annotations

import datetime
from typing import Optional

from core.runtime_config import RuntimeConfig
from strategy_vwap_momentum.trend import compute_trend
from trading_engine.calendar.port import TaifexMarketCalendar


class TradingAppTrendRefresh:
    def __init__(self) -> None:
        self._calendar = TaifexMarketCalendar()

    def refresh_trend(
        self,
        kbars,
        *,
        exchange_dt: Optional[datetime.datetime],
        used_long_lookback: bool,
        atr: float,
        cfg: RuntimeConfig,
    ) -> tuple[str, float]:
        closes = list(getattr(kbars, "Close", []) or [])
        trend_closes = closes
        if used_long_lookback:
            trend_closes = (
                self._calendar.select_recent_trading_days_closes(
                    kbars, exchange_dt or datetime.datetime.now()
                )
                or closes
            )
        return compute_trend(
            trend_closes,
            mode=cfg.live_get("TREND_MODE", cfg.trend_mode),
            timeframe_min=cfg.live_get(
                "TREND_TIMEFRAME_MIN", cfg.trend_timeframe_min
            ),
            ema_period=cfg.live_get("TREND_EMA_PERIOD", cfg.trend_ema_period),
            slope_min=cfg.live_get("TREND_SLOPE_MIN", cfg.trend_slope_min),
            min_strength=cfg.live_get(
                "TREND_MIN_STRENGTH", cfg.trend_min_strength
            ),
            atr=atr,
        )


__all__ = ["TradingAppTrendRefresh"]