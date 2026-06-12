"""Phase 2: Single-threaded tick replay engine for backtesting."""

from __future__ import annotations

import datetime
from typing import List

from config import ATR_REFRESH_SEC, SESSION_END, SESSION_START
from data_loader import DEFAULT_CACHE_DIR, iter_replay_ticks
from exchange_time import is_trading_session
from man import VWAPMomentumStrategy
from mock_broker import MockBroker


class VirtualClock:
    def __init__(self) -> None:
        self._now = 0.0

    def set(self, epoch_sec: float) -> None:
        self._now = epoch_sec

    def __call__(self) -> float:
        return self._now


def _noop_maybe_refresh_atr(_ts: int) -> None:
    """Suppress background-thread spawn inside on_tick (backtest handles ATR earlier)."""
    return


def _pre_tick_refresh_atr(strategy: VWAPMomentumStrategy, ts: int) -> None:
    """Run ATR refresh synchronously before on_tick (avoids lock re-entry deadlock)."""
    if ts - strategy.last_atr_refresh >= ATR_REFRESH_SEC:
        strategy.last_atr_refresh = ts
        strategy.refresh_atr()


class BacktestEngine:
    def __init__(
        self,
        code: str,
        dates: List[datetime.date],
        cache_dir=DEFAULT_CACHE_DIR,
    ) -> None:
        self.clock = VirtualClock()
        self.broker = MockBroker(clock=self.clock, cache_dir=cache_dir)
        self.strategy = VWAPMomentumStrategy(api=self.broker, clock=self.clock)
        self.strategy.contract = self.broker.resolve_contract(code)
        self.strategy._maybe_refresh_atr = _noop_maybe_refresh_atr
        self.code = code
        self.dates = dates
        self.cache_dir = cache_dir

    def run(self) -> None:
        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())
            self.broker.current_dt = tick.datetime
            # Match before timeout so cold-gap ticks can fill/cancel in-flight IOC.
            self.broker.process_matching_queue(tick, self.strategy)
            self.strategy._check_pending_timeout()
            if is_trading_session(tick.datetime, SESSION_START, SESSION_END):
                _pre_tick_refresh_atr(
                    self.strategy, int(tick.datetime.timestamp())
                )
                self.strategy.on_tick(tick)
        if self.strategy._last_tick_exchange_dt is not None:
            self.strategy._emit_daily_summary(
                self.strategy._last_tick_exchange_dt.date()
            )
