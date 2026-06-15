"""P6-1～P6-3: Phase 6 strategy helpers (skeleton; params default off)."""

from __future__ import annotations

from typing import Sequence


def ema(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


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


def trend_allows_entry(
    *,
    enabled: bool,
    trend_dir: str,
    momentum_dir: str,
) -> bool:
    if not enabled or trend_dir == "Flat":
        return True
    return trend_dir == momentum_dir


def dynamic_trail_points(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    if atr <= 0:
        return floor
    return max(floor, round(atr * atr_k, 2))


def dynamic_vwap_stop_distance(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    if atr <= 0:
        return floor
    return max(floor, round(atr * atr_k, 2))
