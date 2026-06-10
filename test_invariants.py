"""P0-3 / P0-8 / partial-fill defense tests."""

from __future__ import annotations

import datetime
import unittest

from exchange_time import exchange_date, trading_day_for_daily_reset


def _dt(hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute)


class TestTradingDayAssumption(unittest.TestCase):
    def test_day_session_uses_calendar_date(self):
        dt = _dt(8, 45)
        self.assertEqual(trading_day_for_daily_reset(dt), exchange_date(dt))


class TestTrailingPeakResync(unittest.TestCase):
    def test_long_peak_calibrated_to_max_entry_and_tick(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18000.0
        strategy._resynced_position = True

        strategy._calibrate_trailing_peak_after_resync(18025.0)

        self.assertEqual(strategy.trailing_peak, 18025.0)
        self.assertFalse(strategy._resynced_position)

    def test_short_peak_calibrated_to_min_entry_and_tick(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy.has_position = True
        strategy.position_dir = "Short"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18000.0
        strategy._resynced_position = True

        strategy._calibrate_trailing_peak_after_resync(17975.0)

        self.assertEqual(strategy.trailing_peak, 17975.0)
        self.assertFalse(strategy._resynced_position)

    def test_long_peak_not_below_entry_when_tick_lower(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18000.0
        strategy._resynced_position = True

        strategy._calibrate_trailing_peak_after_resync(17990.0)

        self.assertEqual(strategy.trailing_peak, 18000.0)


class TestPartialFillDefense(unittest.TestCase):
    def test_partial_entry_requests_sync_and_clears_pending(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy.is_pending = True
        strategy.pending_intent = "entry"
        strategy.pending_order_id = "ord-1"
        strategy.pending_qty = 2

        needs_sync = strategy._apply_deal_fill(18000.0, is_buy=True, deal_qty=1)

        self.assertTrue(needs_sync)
        self.assertFalse(strategy.is_pending)
        self.assertFalse(strategy.has_position)

    def test_full_fill_entry_unchanged(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy.is_pending = True
        strategy.pending_intent = "entry"
        strategy.pending_qty = 1

        needs_sync = strategy._apply_deal_fill(18000.0, is_buy=True, deal_qty=1)

        self.assertFalse(needs_sync)
        self.assertTrue(strategy.has_position)
        self.assertEqual(strategy.entry_price, 18000.0)


class TestDisconnectGating(unittest.TestCase):
    def test_disconnected_blocks_entry_but_allows_exit(self):
        from man import VWAPMomentumStrategy

        strategy = VWAPMomentumStrategy()
        strategy._api_connected = False
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18000.0
        strategy.current_atr = 100.0
        ts = int(_dt(10, 0).timestamp())

        signal = strategy.process_strategy(ts, 17990.0, _dt(10, 0))

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.intent, "exit")


if __name__ == "__main__":
    unittest.main()
