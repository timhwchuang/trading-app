"""Sweepable strategy params with safe patch/restore (avoids ad-hoc setattr)."""

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

# settings field → config module constant (sweep patches the constant)
SWEEP_FIELD_TO_CONST: dict[str, str] = {
    "entry_band_points": "ENTRY_BAND_POINTS",
    "vwap_stop_points": "VWAP_STOP_POINTS",
    "exhaustion_vol": "EXHAUSTION_VOL",
    "exit_grace_ticks": "EXIT_GRACE_TICKS",
    "fixed_tp_points": "FIXED_TP_POINTS",
    "trail_points": "TRAIL_POINTS",
    "hard_stop_points": "HARD_STOP_POINTS",
}


def _patch_modules() -> tuple[Any, ...]:
    import man

    return (config, man)


@dataclass(frozen=True)
class StrategyParamPatch:
    """Saved values for one param across config / man / observability."""

    values: tuple[Any, ...]


@contextmanager
def patch_strategy_params(params: dict[str, Any]) -> Iterator[None]:
    """Temporarily override module-level strategy constants for backtest sweep."""
    modules = _patch_modules()
    saved: dict[str, tuple[Any, ...]] = {}
    for key, value in params.items():
        saved[key] = tuple(getattr(module, key, None) for module in modules)
        for module in modules:
            setattr(module, key, value)
    try:
        yield
    finally:
        for key, values in saved.items():
            for module, old in zip(modules, values):
                setattr(module, key, old)


def apply_strategy_params(params: dict[str, Any]) -> dict[str, tuple[Any, ...]]:
    """Apply params and return saved snapshot for manual restore."""
    modules = _patch_modules()
    saved: dict[str, tuple[Any, ...]] = {}
    for key, value in params.items():
        saved[key] = tuple(getattr(module, key, None) for module in modules)
        for module in modules:
            setattr(module, key, value)
    return saved


def restore_strategy_params(saved: dict[str, tuple[Any, ...]]) -> None:
    modules = _patch_modules()
    for key, values in saved.items():
        for module, old in zip(modules, values):
            setattr(module, key, old)
