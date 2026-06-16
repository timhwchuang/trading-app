"""Test tick fixtures — str close matches tick_cache CSV / Shioaji replay."""

from __future__ import annotations

import datetime

from storage.tick_loader import ReplayTick


def make_replay_tick(
    dt: datetime.datetime,
    *,
    close: str = "18000",
    volume: int = 1,
    tick_type: int = 1,
) -> ReplayTick:
    return ReplayTick(dt, close, volume, tick_type)


def session_ticks(
    day: datetime.date | None = None,
) -> list[ReplayTick]:
    base_day = day or datetime.date(2026, 6, 12)
    base = datetime.datetime.combine(base_day, datetime.time(9, 0, 0))
    return [
        make_replay_tick(base),
        make_replay_tick(base.replace(second=1)),
    ]