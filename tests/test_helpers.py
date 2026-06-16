"""Shared test utilities (P2-8: avoid real Shioaji client in unit tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

from runtime.engine import TradingEngine
from strategy.base import Strategy


def make_host(decision: Strategy | None = None) -> TradingEngine:
    """Create a TradingEngine (execution host) with mock API.

    Pass ``decision`` to inject a custom strategy plugin (see strategy.base.Strategy).
    """
    return TradingEngine(api=MagicMock(), strategy=decision)


# Backward-compatible alias; prefer make_host (returns host, not decision logic).
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
