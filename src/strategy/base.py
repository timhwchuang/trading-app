"""Strategy interface (Protocol + optional ABC base).

This is the core contract for pluggable strategies.

Design goals (per open-source refinement):
- Code to interface, not implementation.
- The engine (runtime.TradingEngine + mixins) is purely the execution/risk/session host.
- The backtest system (backtest.BacktestEngine) is purely the replay host.
- Any strategy that satisfies this interface can be injected into either.
- Strategies feel like plugins: implement the contract (or subclass BaseStrategy) and pass the instance in.

The existing VWAP momentum logic already produces the right shape via its .evaluate() method
and supporting state machine. We formalize it here without changing its behavior.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from core.types import MarketSnapshot, OrderSignal, PositionSnapshot, RiskGate, StrategySideEffects


class Strategy(Protocol):
    """Pluggable strategy decision contract.

    The host (engine/backtester) is responsible for:
    - Computing MarketSnapshot (via indicators)
    - Building PositionSnapshot and RiskGate from its own state machine
    - Computing vol_threshold (using current ATR + opening volume ladder)
    - Passing session times and daily loss limit + callback
    - Handling OrderSignal (pending, place_order, fills, etc.)
    - All locks, timing, reconnection, tick archiving, etc.

    The strategy is responsible only for pure(ish) signal generation and any
    internal episode state it needs (e.g. momentum tracking).

    Implementations should be stateless with respect to execution/pending/positions;
    they receive fresh snapshots on every call.
    """

    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
        vol_threshold: tuple[float, float, float],
        *,
        session_force_flatten_time: datetime.time,
        session_flatten_time: datetime.time,
        max_daily_loss_points: float,
        on_daily_loss_block: Callable[[], None] | None = None,
    ) -> tuple[Optional[OrderSignal], StrategySideEffects]:
        """Core decision point.

        Returns (signal_or_None, side_effects).

        The host will:
        - If side_effects.block_new_entry: set its own block flag.
        - If signal: arm pending and enqueue the order.

        All the heavy context (daily loss check, pending guards, trading session,
        cooldown, force flatten, etc.) has already been applied by the host before
        calling this method (see RiskGate).
        """
        ...

    def reset(self) -> None:
        """Reset any internal episode / momentum state.

        Called by the host after a fill (entry or exit) and on position resync
        in some paths. Implementations that maintain intra-trade state must
        implement this.
        """
        ...

    # ------------------------------------------------------------------
    # Momentum-related hooks (present on the current VWAP implementation).
    # The host (engine) currently delegates to these for property exposure
    # and on_tick peak updates. They are optional for new strategies.
    # During the transition we keep the delegation on TradingEngine for
    # backward compatibility with tests and existing call sites.
    # New strategies can implement them as no-ops.
    # ------------------------------------------------------------------

    def activate_momentum(self, direction: str, price: float, ts: int) -> None:
        """Start a new momentum episode (used by the current VWAP logic)."""
        ...

    def update_momentum_peak(self, price: float) -> None:
        """Update the peak price during an active momentum episode."""
        ...


class BaseStrategy(ABC):
    """Convenience ABC that satisfies the Strategy Protocol.

    Subclass this if you want:
    - Editor support for the required methods
    - Default (no-op) implementations for the optional momentum hooks
    - A place to hang shared strategy utilities

    You are still free to implement Strategy as a pure Protocol (no inheritance)
    if you prefer composition or function-based wrappers.
    """

    @abstractmethod
    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
        vol_threshold: tuple[float, float, float],
        *,
        session_force_flatten_time: datetime.time,
        session_flatten_time: datetime.time,
        max_daily_loss_points: float,
        on_daily_loss_block: Callable[[], None] | None = None,
    ) -> tuple[Optional[OrderSignal], StrategySideEffects]:
        """See Strategy.evaluate."""
        ...

    def reset(self) -> None:
        """Default no-op. Override if your strategy has episode state."""
        pass

    def activate_momentum(self, direction: str, price: float, ts: int) -> None:
        """Default no-op."""
        pass

    def update_momentum_peak(self, price: float) -> None:
        """Default no-op."""
        pass


# Re-export for convenience so users can do:
#   from strategy.base import Strategy, StrategySideEffects, BaseStrategy
__all__ = ["Strategy", "StrategySideEffects", "BaseStrategy"]
