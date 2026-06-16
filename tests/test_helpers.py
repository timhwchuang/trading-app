"""Shared test utilities (P2-8: avoid real Shioaji client in unit tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

from runtime.engine import VWAPMomentumStrategy


def make_strategy() -> VWAPMomentumStrategy:
    return VWAPMomentumStrategy(api=MagicMock())


def arm_pending_entry(
    strategy: VWAPMomentumStrategy,
    *,
    order_id: str = "ord-entry-1",
    signal_price: float = 18000.0,
    exchange_ts: int = 1000,
) -> None:
    strategy.is_pending = True
    strategy.pending_intent = "entry"
    strategy.pending_order_id = order_id
    strategy.pending_qty = 1
    strategy.pending_exchange_ts = exchange_ts
    strategy.pending_signal_price = signal_price
    strategy.pending_limit_price = signal_price + 3
    strategy.pending_ioc_slippage = 3


def arm_pending_exit(
    strategy: VWAPMomentumStrategy,
    *,
    order_id: str = "ord-exit-1",
    signal_price: float = 18020.0,
    exchange_ts: int = 2000,
    exit_reason: str = "take_profit",
) -> None:
    strategy.is_pending = True
    strategy.pending_intent = "exit"
    strategy.pending_order_id = order_id
    strategy.pending_qty = 1
    strategy.pending_exchange_ts = exchange_ts
    strategy.pending_signal_price = signal_price
    strategy.pending_limit_price = signal_price - 3
    strategy.pending_ioc_slippage = 3
    strategy.pending_exit_reason = exit_reason
