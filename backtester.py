"""Phase 2: Single-threaded tick replay engine for backtesting."""

from __future__ import annotations

import datetime
from typing import List

from config import SESSION_END, SESSION_START
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
        self.code = code
        self.dates = dates
        self.cache_dir = cache_dir

    def run(self) -> None:
        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())
            self.broker.current_dt = tick.datetime
            if not is_trading_session(tick.datetime, SESSION_START, SESSION_END):
                continue
            self.strategy._check_pending_timeout()
            self.strategy.on_tick(tick)
            self.broker.process_matching_queue(tick, self.strategy)
        if self.strategy._last_tick_exchange_dt is not None:
            self.strategy._emit_daily_summary(
                self.strategy._last_tick_exchange_dt.date()
            )
