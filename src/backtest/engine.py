"""Trading-app backtest assembly (wires strategy + ports; replay loop in trading-backtest)."""

from __future__ import annotations

import datetime
from typing import List

from core.runtime_config import RuntimeConfig, default_runtime_config
from integrations.engine_wiring import default_strategy, trading_app_engine_ports
from trading_backtest import BacktestEngine as CoreBacktestEngine
from trading_backtest import VirtualClock
from storage.tick_loader import DEFAULT_CACHE_DIR
from trading_backtest.mock_broker import MockBroker
from trading_engine.core.strategy import Strategy


class BacktestEngine:
    """Thin wrapper: inject app ports + default strategy; delegate replay to trading-backtest."""

    def __init__(
        self,
        code: str,
        dates: List[datetime.date],
        cache_dir=DEFAULT_CACHE_DIR,
        strategy: Strategy | None = None,
        runtime_config: RuntimeConfig | None = None,
    ) -> None:
        cfg = runtime_config or default_runtime_config()
        self.clock = VirtualClock()
        self.broker = MockBroker(
            clock=self.clock,
            cache_dir=cache_dir,
            BLOWOUT_VOL=cfg.momentum_vol_1s,
            session_force_flatten_time=cfg.session_force_flatten_time,
        )
        ports = trading_app_engine_ports(
            api=self.broker,
            use_mock_adapter=True,
            runtime_config=cfg,
        )
        if strategy is None:
            strategy = default_strategy(cfg, ports["obs"])
        self._core = CoreBacktestEngine(
            code,
            dates,
            strategy,
            cache_dir=cache_dir,
            runtime_config=cfg,
            broker=self.broker,
            clock=self.clock,
            telemetry=ports["telemetry"],
            trend_refresh=ports["trend_refresh"],
            order_adapter=ports["order_adapter"],
        )
        self.host = self._core.host
        self.code = code
        self.dates = dates
        self.cache_dir = cache_dir

    def run(self) -> None:
        self._core.run()


__all__ = ["BacktestEngine", "VirtualClock"]