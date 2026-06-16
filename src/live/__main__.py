"""Thin live entry: assemble Shioaji API + TradingEngine."""

from __future__ import annotations

import shioaji as sj

from config import SIMULATION
from integrations.engine_wiring import default_strategy, trading_app_engine_ports
from trading_engine.engine import TradingEngine


def main() -> None:
    api = sj.Shioaji(simulation=SIMULATION)
    ports = trading_app_engine_ports(
        api=api,
        use_mock_adapter=False,
        with_alerts=True,
        with_archive=True,
    )
    TradingEngine(
        api=api,
        strategy=default_strategy(ports["runtime_config"], ports["obs"]),
        **{k: v for k, v in ports.items() if k != "obs"},
    ).start()


if __name__ == "__main__":
    main()