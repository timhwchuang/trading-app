"""P6-1-CAL B-class: forward PnL from tick_cache replay.

Maps SIGNAL_AUDIT ``ts`` (exchange epoch seconds) to subsequent tick closes
under a documented policy. Used by ``trend_calibration`` harness and ``param_sweep``.
"""

from __future__ import annotations

import bisect
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from storage.tick_loader import DEFAULT_CACHE_DIR, iter_replay_ticks


@dataclass(frozen=True)
class ForwardPnlPolicy:
    """Hyperparameter for counterfactual entry PnL (must be documented per run)."""

    mode: str = "fixed_seconds"  # fixed_seconds | fixed_ticks | session_end
    window_seconds: int = 1800  # default ≈ 30×1m bars
    window_ticks: int = 100
    session_end: datetime.time = datetime.time(13, 45)


@dataclass
class TickSeries:
    timestamps: list[int]
    closes: list[float]

    def __len__(self) -> int:
        return len(self.timestamps)


def _direction_sign(direction: str) -> float:
    d = str(direction).strip().lower()
    if d in ("buy", "long"):
        return 1.0
    if d in ("sell", "short"):
        return -1.0
    return 1.0


def load_tick_series(
    code: str,
    dates: list[datetime.date],
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> TickSeries:
    """Load merged tick series from local cache (``.csv`` / ``.csv.gz``)."""
    timestamps: list[int] = []
    closes: list[float] = []
    for tick in iter_replay_ticks(code, dates, cache_dir=Path(cache_dir)):
        timestamps.append(int(tick.datetime.timestamp()))
        closes.append(float(tick.close))
    return TickSeries(timestamps=timestamps, closes=closes)


def _session_end_ts(tick_ts: int, session_end: datetime.time) -> int:
    dt = datetime.datetime.fromtimestamp(tick_ts)
    end = datetime.datetime.combine(dt.date(), session_end)
    return int(end.timestamp())


def _resolve_exit_index(
    series: TickSeries,
    start_idx: int,
    *,
    policy: ForwardPnlPolicy,
    entry_ts: int,
) -> int:
    n = len(series)
    if start_idx >= n:
        return n - 1 if n else 0

    if policy.mode == "fixed_ticks":
        return min(n - 1, start_idx + max(1, policy.window_ticks))

    if policy.mode == "session_end":
        end_ts = _session_end_ts(entry_ts, policy.session_end)
        idx = bisect.bisect_right(series.timestamps, end_ts) - 1
        return max(start_idx, min(n - 1, idx))

    # fixed_seconds (default)
    target_ts = entry_ts + max(1, policy.window_seconds)
    idx = bisect.bisect_right(series.timestamps, target_ts) - 1
    return max(start_idx, min(n - 1, idx))


def make_replay_forward_pnl(
    series: TickSeries,
    policy: ForwardPnlPolicy | None = None,
) -> Callable[[float, int, str], float]:
    """Return ``get_forward_pnl(price, ts, direction)`` for harness / sweep."""
    pol = policy or ForwardPnlPolicy()

    def _forward(price: float, ts: int, direction: str = "Buy") -> float:
        if not series.timestamps:
            return 0.0
        idx = bisect.bisect_left(series.timestamps, int(ts))
        if idx >= len(series.timestamps):
            idx = len(series.timestamps) - 1
        exit_idx = _resolve_exit_index(series, idx, policy=pol, entry_ts=int(ts))
        exit_close = series.closes[exit_idx]
        sign = _direction_sign(direction)
        return sign * (exit_close - float(price))

    return _forward


def policy_summary(policy: ForwardPnlPolicy) -> str:
    if policy.mode == "fixed_ticks":
        return f"fixed_ticks={policy.window_ticks}"
    if policy.mode == "session_end":
        return f"session_end={policy.session_end.isoformat()}"
    return f"fixed_seconds={policy.window_seconds}"