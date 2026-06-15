"""P6-1～P6-3: Phase 6 strategy helpers (skeleton; params default off)."""

from __future__ import annotations

from typing import Callable, Sequence


def ema(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def resample_closes(closes: Sequence[float], timeframe_min: int) -> list[float]:
    """Downsample 1-minute closes to higher timeframe (last close per bucket)."""
    if timeframe_min <= 1:
        return list(closes)
    out: list[float] = []
    for i in range(timeframe_min - 1, len(closes), timeframe_min):
        out.append(closes[i])
    return out


def linear_regression_slope(values: Sequence[float]) -> float:
    """Least-squares slope over index 0..n-1."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def trend_from_ema(closes: Sequence[float], period: int) -> tuple[str, float]:
    """Return (trend_dir, strength) where strength = last_close - ema."""
    if len(closes) < period:
        return "Flat", 0.0
    ema_val = ema(closes[-period:], period)
    if ema_val is None:
        return "Flat", 0.0
    last = closes[-1]
    strength = round(last - ema_val, 2)
    if last > ema_val:
        return "Long", strength
    if last < ema_val:
        return "Short", abs(strength)
    return "Flat", 0.0


def trend_from_vwap_slope(
    closes: Sequence[float], min_slope: float
) -> tuple[str, float]:
    """Linear-regression slope of resampled closes."""
    if len(closes) < 2:
        return "Flat", 0.0
    slope = linear_regression_slope(closes)
    strength = abs(round(slope, 2))
    if slope > min_slope:
        return "Long", strength
    if slope < -min_slope:
        return "Short", strength
    return "Flat", 0.0


def compute_trend(
    closes: Sequence[float],
    *,
    mode: str = "ema",
    timeframe_min: int = 5,
    ema_period: int = 20,
    vwap_slope_min: float = 0.0,
) -> tuple[str, float]:
    """High-timeframe trend from 1-minute closes."""
    resampled = resample_closes(closes, timeframe_min)
    if mode == "vwap_slope":
        return trend_from_vwap_slope(resampled, vwap_slope_min)
    return trend_from_ema(resampled, ema_period)


def trend_allows_entry(
    *,
    enabled: bool,
    trend_dir: str,
    momentum_dir: str,
) -> bool:
    if not enabled or trend_dir == "Flat":
        return True
    return trend_dir == momentum_dir


def dynamic_atr_based(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    if atr <= 0:
        return floor
    return max(floor, round(atr * atr_k, 2))


def dynamic_trail_points(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    return dynamic_atr_based(atr, floor=floor, atr_k=atr_k)


def dynamic_vwap_stop_distance(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    return dynamic_atr_based(atr, floor=floor, atr_k=atr_k)


def dynamic_atr_points(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    """Alias kept for callers using the older name."""
    return dynamic_atr_based(atr, floor=floor, atr_k=atr_k)
