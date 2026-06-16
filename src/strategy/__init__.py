"""Re-export strategy plugin surface for theman app code."""

from strategy.base import BaseStrategy, Strategy, StrategySideEffects
from strategy_vwap_momentum import (
    SWEEPABLE_PARAMS,
    StrategyParams,
    VWAPMomentumStrategy,
    apply_strategy_params,
    compute_trend,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    patch_strategy_params,
    restore_strategy_params,
    sweepable_value,
    trend_allows_entry,
)
from trading_engine.core.runtime_config import SWEEP_FIELD_TO_CONST
from trading_engine.indicators import IndicatorState

__all__ = [
    "BaseStrategy",
    "IndicatorState",
    "SWEEPABLE_PARAMS",
    "SWEEP_FIELD_TO_CONST",
    "Strategy",
    "StrategyParams",
    "StrategySideEffects",
    "VWAPMomentumStrategy",
    "apply_strategy_params",
    "compute_trend",
    "dynamic_trail_points",
    "dynamic_vwap_stop_distance",
    "patch_strategy_params",
    "restore_strategy_params",
    "sweepable_value",
    "trend_allows_entry",
]