"""Exit grace period: decouple VWAP stop from hard stop after entry."""

from __future__ import annotations

import unittest

from config import EXIT_GRACE_SEC, EXIT_GRACE_TICKS, HARD_STOP_POINTS, VWAP_STOP_POINTS


class TestExitGracePeriod(unittest.TestCase):
    def _long_strategy(self):
        from test_helpers import make_strategy

        strategy = make_strategy()
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.current_vwap = 18000.0
        strategy.trailing_peak = 18000.0
        strategy.entry_exchange_ts = 1000
        strategy.ticks_since_entry = 10
        return strategy

    def test_in_grace_vwap_stop_suppressed(self):
        strategy = self._long_strategy()
        vwap_stop_price = strategy.current_vwap - VWAP_STOP_POINTS
        ts = strategy.entry_exchange_ts + 10

        signal = strategy.manage_exit(vwap_stop_price, ts)

        self.assertIsNone(signal)

    def test_in_grace_hard_stop_still_fires(self):
        strategy = self._long_strategy()
        hard_stop_price = strategy.entry_price - HARD_STOP_POINTS
        ts = strategy.entry_exchange_ts + 10

        signal = strategy.manage_exit(hard_stop_price, ts)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.audit.reason, "stop_loss")

    def test_out_of_grace_vwap_stop_active(self):
        strategy = self._long_strategy()
        strategy.ticks_since_entry = EXIT_GRACE_TICKS
        vwap_stop_price = strategy.current_vwap - VWAP_STOP_POINTS
        ts = strategy.entry_exchange_ts + EXIT_GRACE_SEC

        signal = strategy.manage_exit(vwap_stop_price, ts)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.audit.reason, "stop_loss_vwap")

    def test_still_in_grace_when_ticks_met_but_time_not(self):
        strategy = self._long_strategy()
        strategy.ticks_since_entry = EXIT_GRACE_TICKS
        vwap_stop_price = strategy.current_vwap - VWAP_STOP_POINTS
        ts = strategy.entry_exchange_ts + EXIT_GRACE_SEC - 1

        signal = strategy.manage_exit(vwap_stop_price, ts)

        self.assertIsNone(signal)

    def test_short_in_grace_vwap_stop_suppressed(self):
        from test_helpers import make_strategy

        strategy = make_strategy()
        strategy.has_position = True
        strategy.position_dir = "Short"
        strategy.entry_price = 18000.0
        strategy.current_vwap = 18000.0
        strategy.trailing_peak = 18000.0
        strategy.entry_exchange_ts = 1000
        strategy.ticks_since_entry = 5
        vwap_stop_price = strategy.current_vwap + VWAP_STOP_POINTS

        signal = strategy.manage_exit(vwap_stop_price, 1010)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
