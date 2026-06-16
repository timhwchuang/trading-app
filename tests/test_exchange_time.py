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


if __name__ == "__main__":
    unittest.main()
