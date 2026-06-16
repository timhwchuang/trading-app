"""Shared test utilities (P2-8: avoid real Shioaji client in unit tests)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from integrations.engine_wiring import default_strategy, trading_app_engine_ports
from trading_engine.core.strategy import Strategy
from trading_engine.engine import TradingEngine


def make_host(
    decision: Strategy | None = None,
    *,
    api: Any | None = None,
) -> TradingEngine:
    """Create a TradingEngine (execution host) with mock API.

    Pass ``decision`` to inject a custom strategy plugin.
    Pass ``api`` to bind a concrete broker (e.g. MockBroker) at construction time.
    """
    broker = api if api is not None else MagicMock()
    ports = trading_app_engine_ports(api=broker, use_mock_adapter=True)
    if decision is None:
        decision = default_strategy(ports["runtime_config"], ports["obs"])
    return TradingEngine(
        api=broker,
        strategy=decision,
        **{k: v for k, v in ports.items() if k != "obs"},
    )


make_strategy = make_host


def arm_pending_entry(
    host: TradingEngine,
    *,
    order_id: str = "ord-entry-1",
    signal_price: float = 18000.0,
    exchange_ts: int = 1000,
) -> None:
    host.is_pending = True
    host.pending_intent = "entry"
    host.pending_order_id = order_id
    host.pending_qty = 1
    host.pending_exchange_ts = exchange_ts
    host.pending_signal_price = signal_price
    host.pending_limit_price = signal_price + 3
    host.pending_ioc_slippage = 3


def arm_pending_exit(
    host: TradingEngine,
    *,
    order_id: str = "ord-exit-1",
    signal_price: float = 18020.0,
    exchange_ts: int = 2000,
    exit_reason: str = "take_profit",
) -> None:
    host.is_pending = True
    host.pending_intent = "exit"
    host.pending_order_id = order_id
    host.pending_qty = 1
    host.pending_exchange_ts = exchange_ts
    host.pending_signal_price = signal_price
    host.pending_limit_price = signal_price - 3
    host.pending_ioc_slippage = 3
    host.pending_exit_reason = exit_reason