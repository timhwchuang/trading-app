"""Test tick fixtures compatible with trading-backtest MockBroker (numeric close)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace


def make_replay_tick(
    dt: datetime.datetime,
    *,
    close: float = 18000.0,
    volume: int = 1,
    tick_type: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        datetime=dt,
        close=float(close),
        volume=volume,
        tick_type=tick_type,
        bid_price=0.0,
        ask_price=0.0,
    )


def session_ticks(
    day: datetime.date | None = None,
) -> list[SimpleNamespace]:
    base_day = day or datetime.date(2026, 6, 12)
    base = datetime.datetime.combine(base_day, datetime.time(9, 0, 0))
    return [
        make_replay_tick(base),
        make_replay_tick(base.replace(second=1)),
    ]