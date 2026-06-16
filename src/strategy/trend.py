"""Trend & dynamic risk helpers for P6 (P6-1 trend filter + P6-2/3 ATR dynamic exits).

This module was previously named phase6.py during skeleton phase.
It now hosts the higher-timeframe trend regime detection used as entry filter.

Trend filter (P6-1 Level 2):
- compute_trend(..., min_strength=...) returns meaningful "Long"/"Short" only when
  the detected move on the resampled HTF has sufficient magnitude.
- "Flat" now also covers "detected direction but strength below threshold".
- trend_allows_entry uses the (now stronger) trend_dir to block clear counter-trend
  pullback entries.
- This gives real practical value: small noisy HTF drifts no longer create false
  "with-trend" or "counter-trend" signals, while real legs on the day can protect
  against fading micro-momentum in the wrong direction.

P6-1-CAL-4 命名誠實化：
- `trend_ema_period` / `trend_timeframe_min` 定義的「有效尺度」≈ timeframe_min × ema_period（分鐘）。
  這是 short-window displacement / slope proxy（intraday HTF bias veto），**不是**真正日內或跨日 macro bias。
  實際 regime power 仍來自 resample + min_strength (ATR units) + Level 2 gating。
- 建議文件 alias 概念：trend_ema_period 可視為 trend_window_bars（HTF bars 數），但 yaml key 維持不變以相容。
- 校準 SOP 見 docs/BackTestingSpec.md「P6-1 Trend Filter Calibration Workflow」與 TODO P6-1-CAL-4/5。
  所有真實 delta / veto_rate 必須來自 UAT tick 後的 harness + sweep；本處僅語意說明。
"""

from __future__ import annotations

from typing import Callable, Sequence


def ema(values: Sequence[float], period: int) -> float | None:
    """Compute EMA over the series.

    Initialization uses SMA of the first 'period' values as seed (standard
    warmup) instead of seeding from values[0] only. This reduces first-bar
    overweight bias.

    When called with exactly 'period' values (current usage pattern in
    trend_from_ema), this reduces to SMA of the window.
    The result is then compared as 'last vs SMA/EMA of recent HTF window'.
    """
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    # Proper warmup: SMA of first period bars as initial EMA value
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def resample_closes(closes: Sequence[float], timeframe_min: int) -> list[float]:
    """Naive stride downsample of 1m closes to higher timeframe.

    Aligned from the *end* so that the most recent close is always represented
    in the last output bar (important for "current regime" at decision time).
    Still a crude stride (not true datetime-bucketed resampling). It can cross
    session gaps when the input closes span multiple days.

    For production: strongly prefer fetching actual higher-TF kbars (e.g. 5m/15m)
    directly from the API for the relevant session, or implement proper
    time-bucket resampling using bar timestamps.
    """
    if timeframe_min <= 1:
        return list(closes)
    n = len(closes)
    if n == 0:
        return []
    out: list[float] = []
    # Walk backward from the very last bar so closes[-1] is guaranteed to be
    # included (or be the representative of the last, possibly partial, bucket).
    i = n - 1
    while i >= 0:
        out.append(closes[i])
        i -= timeframe_min
    out.reverse()
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
    """Return (trend_dir, strength) on resampled HTF closes.

    Uses ema() (now SMA-seeded for the window) on the last 'period' resampled bars.
    strength = last - ema_val (signed for Long, positive abs for Short).
    This is effectively 'current price vs SMA/EMA of the recent HTF window'.

    Caller (compute_trend) may further downgrade to Flat based on min_strength.
    Note: not a full multi-period recursive EMA with long history; it is a
    short-window displacement / average comparison (common practical proxy
    for intraday HTF bias).
    """
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


def trend_from_slope(
    closes: Sequence[float], min_slope: float
) -> tuple[str, float]:
    """Linear regression slope on resampled higher-timeframe closes.

    This is *price* slope (no volume, not VWAP). Positive slope = Long bias.
    strength = |slope| (always non-negative when Long/Short).
    Caller (compute_trend) may further downgrade to Flat based on min_strength.
    """
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
    slope_min: float = 0.0,
    min_strength: float = 0.0,
    atr: float = 0.0,
) -> tuple[str, float]:
    """High-timeframe trend / regime from (typically 1-minute) closes.

    mode="ema":   last vs EMA on resampled HTF closes.
    mode="slope": linreg price slope on resampled HTF closes.

    atr (recommended):
        When > 0, strength is normalized as strength / atr before comparing to
        min_strength. This makes the threshold comparable across "ema" vs "slope"
        modes and across different volatility regimes. The *raw* strength is still
        returned (for audit / logging / future logic).

    min_strength (Level 2):
        If a direction is detected but (normalized) strength < min_strength,
        force "Flat", 0.0.
        This makes "Long"/"Short" labels meaningful (only when the HTF move has legs).

        ⚠️ SEMANTICS WARNING (critical for traders):
          min_strength=0.0 (the default) is the *most aggressive* setting for the
          filter, not the most permissive.
          - At 0.0: any detectable HTF drift (even 0.1 point) produces a "Long" or
            "Short" label → trend_allows_entry will veto the largest number of
            counter-trend pullbacks.
          - Raising min_strength makes the filter *looser* (more cases become
            "Flat" → more entries allowed).
          When you do `trend_filter_enabled: true` with defaults, you get the
          strictest veto behavior. Always calibrate and document your intended
          min_strength.

        When atr is supplied (normal case from engine), min_strength is interpreted
        in "ATR units" (e.g. 0.5 means "at least 0.5 ATR of HTF strength").
        Typical calibrated values after UAT: 0.3 ~ 1.5+ ATR depending on product/TF/mode.
    """
    resampled = resample_closes(closes, timeframe_min)
    if mode == "slope":
        direction, strength = trend_from_slope(resampled, slope_min)
    else:
        direction, strength = trend_from_ema(resampled, ema_period)

    # Level 2: only commit to a trend label when the move is strong enough.
    # This is what gives the filter real practical filtering power.
    if direction != "Flat":
        eff_strength = strength
        if atr > 1e-6:
            eff_strength = strength / atr
        if eff_strength < min_strength:
            return "Flat", 0.0
    return direction, strength


def trend_allows_entry(
    *,
    enabled: bool,
    trend_dir: str,
    momentum_dir: str,
) -> bool:
    """Higher-timeframe (P6-1) regime filter for pullback entries.

    With Level 2 min_strength support in compute_trend:
      - "Long"/"Short" are only emitted when the HTF move exceeded min_strength.
      - "Flat" now also includes "direction visible but too weak" and pure noise.

    Logic (unchanged for call-site compatibility):
    - disabled or trend_dir == "Flat" → allow (permissive on unclear regimes)
    - else only allow if trend_dir matches the micro momentum direction.

    Real trading value:
      Strong declared counter-trend days will now reliably block fading the
      micro pullback in the wrong direction. Weak/choppy days remain permissive
      (consistent with the original micro + VWAP-pullback philosophy) but at
      least we no longer pretend a 1-point drift on the 5m is a "trend".
    """
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
