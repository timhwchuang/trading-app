"""Re-export trend helpers from plugin package."""

from strategy_vwap_momentum.trend import *  # noqa: F403

__all__ = [
    "compute_trend",
    "dynamic_atr_based",
    "dynamic_atr_points",
    "dynamic_trail_points",
    "dynamic_vwap_stop_distance",
    "ema",
    "linear_regression_slope",
    "resample_closes",
    "trend_allows_entry",
    "trend_from_ema",
    "trend_from_slope",
]