"""Strategy parameter bundle.

Concrete strategies (e.g. VWAPMomentumStrategy) own an instance of this.
It reads from the central config for convenience + supports the sweep / param-sweep
monkey-patching mechanism.

For better encapsulation in the future, strategies can define their own
parameter dataclasses and load only the subset they care about from a config section.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import config

SWEEPABLE_PARAMS = frozenset(
    {
        "ENTRY_BAND_POINTS",
        "VWAP_STOP_POINTS",
        "EXHAUSTION_VOL",
        "EXIT_GRACE_TICKS",
        "FIXED_TP_POINTS",
        "TRAIL_POINTS",
        "HARD_STOP_POINTS",
    }
)

SWEEP_FIELD_TO_CONST: dict[str, str] = {
    "entry_band_points": "ENTRY_BAND_POINTS",
    "vwap_stop_points": "VWAP_STOP_POINTS",
    "exhaustion_vol": "EXHAUSTION_VOL",
    "exit_grace_ticks": "EXIT_GRACE_TICKS",
    "fixed_tp_points": "FIXED_TP_POINTS",
    "trail_points": "TRAIL_POINTS",
    "hard_stop_points": "HARD_STOP_POINTS",
}


@dataclass
class StrategyParams:
    """Runtime strategy constants; properties read ``config`` each access for sweeps."""

    @property
    def entry_band_points(self) -> float:
        return float(config.ENTRY_BAND_POINTS)

    @property
    def vwap_stop_points(self) -> float:
        return float(config.VWAP_STOP_POINTS)

    @property
    def exhaustion_vol(self) -> int:
        return int(config.EXHAUSTION_VOL)

    @property
    def exit_grace_ticks(self) -> int:
        return int(config.EXIT_GRACE_TICKS)

    @property
    def exit_grace_sec(self) -> int:
        return int(config.EXIT_GRACE_SEC)

    @property
    def fixed_tp_points(self) -> float:
        return float(config.FIXED_TP_POINTS)

    @property
    def trail_points(self) -> float:
        return float(config.TRAIL_POINTS)

    @property
    def hard_stop_points(self) -> float:
        return float(config.HARD_STOP_POINTS)

    @property
    def momentum_buy_ratio(self) -> float:
        return float(config.MOMENTUM_BUY_RATIO)

    @property
    def momentum_sell_ratio(self) -> float:
        return float(config.MOMENTUM_SELL_RATIO)

    @property
    def min_atr_threshold(self) -> float:
        return float(config.MIN_ATR_THRESHOLD)

    @property
    def max_consecutive_loss(self) -> int:
        return int(config.MAX_CONSECUTIVE_LOSS)

    @property
    def atr_trailing_enabled(self) -> bool:
        return bool(config.ATR_TRAILING_ENABLED)

    @property
    def atr_vwap_stop_enabled(self) -> bool:
        return bool(config.ATR_VWAP_STOP_ENABLED)

    @property
    def trail_points_floor(self) -> float:
        return float(config.TRAIL_POINTS_FLOOR)

    @property
    def trail_atr_k(self) -> float:
        return float(config.TRAIL_ATR_K)

    @property
    def vwap_stop_points_floor(self) -> float:
        return float(config.VWAP_STOP_POINTS_FLOOR)

    @property
    def vwap_stop_atr_k(self) -> float:
        return float(config.VWAP_STOP_ATR_K)

    @property
    def trend_filter_enabled(self) -> bool:
        return bool(config.TREND_FILTER_ENABLED)

    @property
    def flatten_slippage_points(self) -> int:
        return int(config.FLATTEN_SLIPPAGE_POINTS)

    @classmethod
    def from_config(cls) -> StrategyParams:
        return cls()


def sweepable_value(name: str) -> Any:
    return getattr(config, name)


@contextmanager
def patch_strategy_params(params: dict[str, Any]) -> Iterator[None]:
    """Temporarily override module-level strategy constants for backtest sweep."""
    saved = apply_strategy_params(params)
    try:
        yield
    finally:
        restore_strategy_params(saved)


def apply_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    """Apply params and return saved snapshot for manual restore."""
    saved: dict[str, Any] = {}
    for key, value in params.items():
        saved[key] = getattr(config, key, None)
        setattr(config, key, value)
    return saved


def restore_strategy_params(saved: dict[str, Any]) -> None:
    for key, old in saved.items():
        setattr(config, key, old)
