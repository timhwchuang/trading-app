"""P0-6: exchange-time session boundary tests."""

from __future__ import annotations

import datetime
import unittest

from config import SESSION_END, SESSION_START
from exchange_time import (
    TAIWAN_TZ,
    exchange_date,
    is_opening_session_window,
    is_trading_session,
)
from tests.test_helpers import make_host


def _dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute, second)


class TestTradingSessionBoundaries(unittest.TestCase):
    def test_before_session_start(self):
        self.assertFalse(is_trading_session(_dt(8, 44, 59), SESSION_START, SESSION_END))

    def test_session_start_inclusive(self):
        self.assertTrue(is_trading_session(_dt(8, 45, 0), SESSION_START, SESSION_END))

    def test_before_session_end(self):
        self.assertTrue(is_trading_session(_dt(13, 44, 59), SESSION_START, SESSION_END))

    def test_session_end_inclusive(self):
        self.assertTrue(is_trading_session(_dt(13, 45, 0), SESSION_START, SESSION_END))

    def test_after_session_end(self):
        self.assertFalse(is_trading_session(_dt(13, 45, 1), SESSION_START, SESSION_END))


class TestExchangeDate(unittest.TestCase):
    def test_naive_date(self):
        self.assertEqual(exchange_date(_dt(8, 45)), datetime.date(2026, 6, 10))

    def test_utc_converts_to_taiwan_date(self):
        # 2026-06-09 16:30 UTC = 2026-06-10 00:30 Taiwan
        utc = datetime.datetime(2026, 6, 9, 16, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(exchange_date(utc), datetime.date(2026, 6, 10))


class TestOpeningSessionWindow(unittest.TestCase):
    def test_opening_window_boundaries(self):
        self.assertTrue(is_opening_session_window(_dt(8, 45, 0)))
        self.assertTrue(is_opening_session_window(_dt(9, 14, 59)))
        self.assertFalse(is_opening_session_window(_dt(9, 15, 0)))
        self.assertFalse(is_opening_session_window(_dt(8, 44, 59)))


class TestCooldownUsesExchangeTs(unittest.TestCase):
    def test_exit_fill_records_exchange_ts_not_system_clock(self):
        host = make_host()
        exit_ts = 1_700_000_000
        host.has_position = True
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.trailing_peak = 18020.0
        host.pending_intent = "exit"
        host.pending_exchange_ts = exit_ts

        host._apply_deal_fill(18011.0, is_buy=False)

        self.assertEqual(host.last_exit_time, exit_ts)
        self.assertNotEqual(host.last_exit_time, int(__import__("time").time()))

    def test_cooldown_blocks_until_exchange_ts_elapsed(self):
        from config import COOLDOWN_SEC

        host = make_host()
        exit_ts = 1_700_000_000
        host.last_exit_time = exit_ts
        host.current_atr = 100.0

        during = host.process_strategy(
            exit_ts + COOLDOWN_SEC - 1,
            18000.0,
            datetime.datetime.fromtimestamp(
                exit_ts + COOLDOWN_SEC - 1, tz=TAIWAN_TZ
            ),
        )
        self.assertIsNone(during)


class TestDailyStateReset(unittest.TestCase):
    def test_reset_on_exchange_date_change(self):
        host = make_host()
        host.daily_pnl = -150.0
        host.block_new_entry = True
        host.consecutive_loss = 3
        host._trading_date = datetime.date(2026, 6, 9)

        host._maybe_reset_daily_state(_dt(8, 45))

        self.assertEqual(host.daily_pnl, 0.0)
        self.assertFalse(host.block_new_entry)
        self.assertEqual(host.consecutive_loss, 0)
        self.assertEqual(host._trading_date, datetime.date(2026, 6, 10))

    def test_same_day_no_reset(self):
        host = make_host()
        host.daily_pnl = -80.0
        host.block_new_entry = True
        host._trading_date = datetime.date(2026, 6, 10)

        host._maybe_reset_daily_state(_dt(10, 0))

        self.assertEqual(host.daily_pnl, -80.0)
        self.assertTrue(host.block_new_entry)


class TestP6Cal1RecentTradingDaySlice(unittest.TestCase):
    """P6-1-CAL-1: direct unit coverage for select_recent_trading_days_closes + trading_day boundaries."""

    def test_select_keeps_only_recent_days_and_includes_latest(self):
        from exchange_time import select_recent_trading_days_closes, trading_day_for_daily_reset
        import datetime as dt_mod

        # Two days, 5 bars each (simulated 1m)
        d1 = dt_mod.datetime(2026, 6, 12, 9, 0)
        d2 = dt_mod.datetime(2026, 6, 13, 9, 0)
        day1 = [100.0 + i for i in range(5)]
        day2 = [110.0 + i for i in range(5)]
        all_c = day1 + day2
        all_ts = [int((d1 + dt_mod.timedelta(minutes=i)).timestamp() * 1e9) for i in range(5)] + \
                 [int((d2 + dt_mod.timedelta(minutes=i)).timestamp() * 1e9) for i in range(5)]

        class R:
            ts = all_ts
            Close = all_c

        ref = d2 + dt_mod.timedelta(minutes=3)
        sliced = select_recent_trading_days_closes(R(), ref, max_days=2)
        # With 2 days both present and max=2 -> all 10 bars (recent days include both)
        self.assertEqual(len(sliced), 10)
        # Force max_days=1 -> only the last distinct trading day (the hygiene cut)
        sliced1 = select_recent_trading_days_closes(R(), ref, max_days=1)
        self.assertEqual(sliced1, day2)
        self.assertEqual(trading_day_for_daily_reset(d2), trading_day_for_daily_reset(ref))

    def test_select_cross_night_gap_and_choppy_prior(self):
        from exchange_time import select_recent_trading_days_closes
        import datetime as dt_mod
        # Prior night/close polluted flat + new day ramp
        d_prior = dt_mod.datetime(2026, 6, 12, 13, 40)
        d_new = dt_mod.datetime(2026, 6, 13, 8, 50)
        prior = [100.0] * 10
        new = [100.0 + i * 0.7 for i in range(15)]
        closes = prior + new
        tss = [int((d_prior + dt_mod.timedelta(minutes=i)).timestamp()*1e9) for i in range(10)] + \
              [int((d_new + dt_mod.timedelta(minutes=i)).timestamp()*1e9) for i in range(15)]
        class R2:
            ts = tss
            Close = closes
        sliced = select_recent_trading_days_closes(R2(), d_new + dt_mod.timedelta(minutes=5), max_days=1)
        self.assertEqual(sliced, new)  # prior day dropped


if __name__ == "__main__":
    unittest.main()
