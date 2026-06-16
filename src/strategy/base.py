"""Strategy interface (Protocol + optional ABC base).

This is the core contract for pluggable strategies.

Design goals (per open-source refinement):
- Code to interface, not implementation.
- The engine (runtime.TradingEngine + mixins) is purely the execution/risk/session host.
- The backtest system (backtest.BacktestEngine) is purely the replay host.
- Any strategy that satisfies this interface can be injected into either.
- Strategies feel like plugins: implement the contract (or subclass BaseStrategy) and pass the instance in.

**Transition status (not yet fully pluggable):**
The Protocol formalizes the `evaluate()` call site, but the host still reaches into
VWAP-specific surfaces on `self.strategy` (e.g. `.momentum`, `reset_momentum()`,
`manage_exit()`, audit builders). Only `strategy.vwap_momentum.VWAPMomentumStrategy`
can run end-to-end today. New strategies injected via the constructor will fail on the
first tick until those host dependencies are widened or removed. See TODO Phase 7.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from core.types import MarketSnapshot, OrderSignal, PositionSnapshot, RiskGate, StrategySideEffects


class Strategy(Protocol):
    """Pluggable strategy decision contract (transition — see module docstring).

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

        Declared on the Protocol but not yet called by the host (host uses
        ``reset_momentum()`` on the VWAP implementation instead). Reserved for
        a future unified reset hook.
        """
        ...

    # ------------------------------------------------------------------
    # Momentum-related hooks (present on the current VWAP implementation).
    # The host currently delegates to these and reads ``.momentum`` directly.
    # They are NOT sufficient for a new strategy: see module docstring.
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
