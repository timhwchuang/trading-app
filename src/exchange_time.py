"""Exchange-time helpers (Taiwan / TAIFEX).

策略內所有「幾點幾分」與 tick 驅動的時間差一律用 tick.datetime（交易所時間）。
"""

from __future__ import annotations

import datetime

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))


def exchange_local_dt(dt: datetime.datetime) -> datetime.datetime:
    """Normalize tick datetime to Taiwan local (naive = already exchange local)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(TAIWAN_TZ)


def exchange_local_time(dt: datetime.datetime) -> datetime.time:
    return exchange_local_dt(dt).time()


def exchange_date(dt: datetime.datetime) -> datetime.date:
    return exchange_local_dt(dt).date()


def trading_day_for_daily_reset(dt: datetime.datetime) -> datetime.date:
    """P0-8: 日內風控重置用的「交易日」。

    目前策略僅日盤（08:45–13:45），交易日 = 台灣日曆日。
    若未來擴展夜盤，須改為 TAIFEX 交易日（切換點約 15:00），不可再用午夜日曆日。
    """
    return exchange_date(dt)


def is_trading_session(
    dt: datetime.datetime,
    session_start: datetime.time,
    session_end: datetime.time,
) -> bool:
    """SESSION_START <= t <= SESSION_END (inclusive on both ends)."""
    t = exchange_local_time(dt)
    return session_start <= t <= session_end


# P1-2 opening windows (exchange local, half-open intervals)
_OPEN_FUTURES = datetime.time(8, 45)
_OPEN_SPOT = datetime.time(9, 0)
_OPEN_NORMAL = datetime.time(9, 15)


def opening_session_multiplier(
    dt: datetime.datetime,
    *,
    mult_futures: float,
    mult_spot: float,
    mult_normal: float,
) -> float:
    """08:45 <= t < 09:00 → futures; 09:00 <= t < 09:15 → spot; else normal."""
    t = exchange_local_time(dt)
    if _OPEN_FUTURES <= t < _OPEN_SPOT:
        return mult_futures
    if _OPEN_SPOT <= t < _OPEN_NORMAL:
        return mult_spot
    return mult_normal


def is_at_or_after(dt: datetime.datetime, cutoff: datetime.time) -> bool:
    """True when exchange local time >= cutoff (inclusive)."""
    return exchange_local_time(dt) >= cutoff


def is_opening_session_window(dt: datetime.datetime) -> bool:
    """08:45 <= t < 09:15（期貨 + 現貨開盤衝擊窗）；P2-5 IOC 取消統計用。"""
    t = exchange_local_time(dt)
    return _OPEN_FUTURES <= t < _OPEN_NORMAL


def compute_vol_threshold(
    current_atr: float,
    dt: datetime.datetime,
    *,
    base_vol: float,
    atr_vol_mult: float,
    mult_futures: float,
    mult_spot: float,
    mult_normal: float,
) -> tuple[float, float, float]:
    """Return (base_vol, multiplier, vol_threshold)."""
    effective_base = max(base_vol, current_atr * atr_vol_mult)
    multiplier = opening_session_multiplier(
        dt,
        mult_futures=mult_futures,
        mult_spot=mult_spot,
        mult_normal=mult_normal,
    )
    return effective_base, multiplier, effective_base * multiplier
