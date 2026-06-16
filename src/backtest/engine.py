"""Phase 2: Single-threaded tick replay engine for backtesting."""

from __future__ import annotations

import datetime
from typing import List

from config import ATR_REFRESH_SEC, SESSION_END, SESSION_START
from exchange_time import is_trading_session
from integrations.engine_wiring import default_strategy, theman_engine_ports
from runtime.engine import TradingEngine
from core.runtime_config import RuntimeConfig
from strategy.base import Strategy
from backtest.mock_broker import MockBroker
from storage.tick_loader import DEFAULT_CACHE_DIR


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


def _pre_tick_refresh_atr(host: TradingEngine, ts: int) -> None:
    """Run ATR refresh synchronously before on_tick (avoids lock re-entry deadlock)."""
    if ts - host.last_atr_refresh >= ATR_REFRESH_SEC:
        host.last_atr_refresh = ts
        host.refresh_atr()


class BacktestEngine:
    def __init__(
        self,
        code: str,
        dates: List[datetime.date],
        cache_dir=DEFAULT_CACHE_DIR,
        strategy: Strategy | None = None,
        runtime_config: RuntimeConfig | None = None,
    ) -> None:
        """strategy: pluggable decision logic (see strategy.base.Strategy).
        If None, the default VWAP momentum strategy is used.
        """
        self.clock = VirtualClock()
        self.broker = MockBroker(clock=self.clock, cache_dir=cache_dir)
        ports = theman_engine_ports(
            api=self.broker,
            use_mock_adapter=True,
            runtime_config=runtime_config,
        )
        cfg = ports["runtime_config"]
        if strategy is None:
            strategy = default_strategy(cfg, ports["obs"])
        self.host = TradingEngine(
            api=self.broker,
            clock=self.clock,
            strategy=strategy,
            **{k: v for k, v in ports.items() if k != "obs"},
        )
        self.host.contract = self.broker.resolve_contract(code)
        self.host._maybe_refresh_atr = _noop_maybe_refresh_atr
        self.host._order_sync_mode = True
        self.code = code
        self.dates = dates
        self.cache_dir = cache_dir

    def run(self) -> None:
        from backtest.replay import iter_replay_ticks

        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())
            self.broker.current_dt = tick.datetime
            # Match before timeout so cold-gap ticks can fill/cancel in-flight IOC.
            self.broker.process_matching_queue(tick, self.host)
            self.host._check_pending_timeout()
            if is_trading_session(tick.datetime, SESSION_START, SESSION_END):
                _pre_tick_refresh_atr(
                    self.host, int(tick.datetime.timestamp())
                )
                self.host.on_tick(tick)
        if self.host._last_tick_exchange_dt is not None:
            self.host._emit_daily_summary(
                self.host._last_tick_exchange_dt.date()
            )
