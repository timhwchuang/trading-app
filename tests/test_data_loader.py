"""Tests for data_loader (Phase 0) and injected-clock seam (Phase 1)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from storage.tick_loader import (
    ReplayTick,
    _ns_to_taipei_naive,
    cache_path,
    date_range,
    iter_replay_ticks,
    load_ticks_csv,
    save_ticks_csv,
)
from test_helpers import make_strategy


class TestTaipeiNaive(unittest.TestCase):
    def test_ns_to_taipei_naive(self):
        # 2026-06-12 09:00:00 +08:00
        aware = datetime.datetime(
            2026, 6, 12, 9, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        ts_ns = int(aware.timestamp() * 1_000_000_000)
        dt = _ns_to_taipei_naive(ts_ns)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt, datetime.datetime(2026, 6, 12, 9, 0, 0))


class TestCsvRoundTrip(unittest.TestCase):
    def test_save_load_roundtrip(self):
        ticks = [
            ReplayTick(
                datetime=datetime.datetime(2026, 6, 12, 8, 45, 1),
                close="18000",
                volume=3,
                tick_type=1,
                bid_price=17999.0,
                ask_price=18001.0,
            ),
            ReplayTick(
                datetime=datetime.datetime(2026, 6, 12, 8, 45, 2),
                close="18002",
                volume=5,
                tick_type=2,
            ),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            n = save_ticks_csv(ticks, path)
            self.assertEqual(n, 2)
            loaded = load_ticks_csv(path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].close, "18000")
            self.assertEqual(loaded[0].volume, 3)
            self.assertEqual(loaded[1].tick_type, 2)

    def test_iter_replay_ticks_multi_day(self):
        with tempfile.TemporaryDirectory() as d:
            d1 = datetime.date(2026, 6, 11)
            d2 = datetime.date(2026, 6, 12)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 11, 9, 0), "18000", 1, 0)],
                cache_path(Path(d), "TXFR1", d1),
            )
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9, 0), "18010", 1, 0)],
                cache_path(Path(d), "TXFR1", d2),
            )
            ticks = list(iter_replay_ticks("TXFR1", [d1, d2], cache_dir=Path(d)))
            self.assertEqual(len(ticks), 2)
            self.assertEqual(ticks[0].close, "18000")
            self.assertEqual(ticks[1].close, "18010")


class TestDateRange(unittest.TestCase):
    def test_inclusive(self):
        days = date_range(datetime.date(2026, 6, 10), datetime.date(2026, 6, 12))
        self.assertEqual(len(days), 3)


class TestInjectedClock(unittest.TestCase):
    def test_record_tick_arrival_uses_injected_clock(self):
        strategy = make_strategy()
        strategy._clock = MagicMock(return_value=12345.0)
        strategy._record_tick_arrival(
            100, datetime.datetime(2026, 6, 12, 9, 0), tick_type=1
        )
        self.assertEqual(strategy._last_tick_wall_time, 12345.0)
        strategy._clock.assert_called()

    def test_pending_timeout_uses_injected_clock(self):
        from config import PENDING_TIMEOUT_SEC

        strategy = make_strategy()
        clock_value = {"t": 1000.0}
        strategy._clock = lambda: clock_value["t"]
        strategy.is_pending = True
        strategy.pending_since = 1000.0
        strategy.pending_trade = None
        # not yet timed out
        strategy._check_pending_timeout()
        self.assertTrue(strategy.is_pending)
        # advance past timeout → no trade object → resets pending
        clock_value["t"] = 1000.0 + PENDING_TIMEOUT_SEC + 1
        strategy._check_pending_timeout()
        self.assertFalse(strategy.is_pending)

    def test_default_clock_is_time_time(self):
        import time

        strategy = make_strategy()
        self.assertIs(strategy._clock, time.time)

    def test_today_prefers_tick_date(self):
        strategy = make_strategy()
        self.assertEqual(strategy._today(), datetime.date.today())
        strategy._last_tick_exchange_dt = datetime.datetime(2020, 1, 2, 9, 0)
        self.assertEqual(strategy._today(), datetime.date(2020, 1, 2))


if __name__ == "__main__":
    unittest.main()
