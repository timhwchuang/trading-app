"""Exit grace period: decouple VWAP stop from hard stop after entry."""

from __future__ import annotations

import unittest

from config import EXIT_GRACE_SEC, EXIT_GRACE_TICKS, HARD_STOP_POINTS, VWAP_STOP_POINTS
from tests.test_helpers import make_host


class TestExitGracePeriod(unittest.TestCase):
    def _long_strategy(self):
        host = make_host()
        host.has_position = True
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.current_vwap = 18000.0
        host.trailing_peak = 18000.0
        host.entry_exchange_ts = 1000
        host.ticks_since_entry = 10
        return host

    def test_in_grace_vwap_stop_suppressed(self):
        host = self._long_strategy()
        vwap_stop_price = host.current_vwap - VWAP_STOP_POINTS
        ts = host.entry_exchange_ts + 10

        signal = host.manage_exit(vwap_stop_price, ts)

        self.assertIsNone(signal)

    def test_in_grace_hard_stop_still_fires(self):
        host = self._long_strategy()
        hard_stop_price = host.entry_price - HARD_STOP_POINTS
        ts = host.entry_exchange_ts + 10

        signal = host.manage_exit(hard_stop_price, ts)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.audit.reason, "stop_loss")

    def test_out_of_grace_vwap_stop_active(self):
        host = self._long_strategy()
        host.ticks_since_entry = EXIT_GRACE_TICKS
        vwap_stop_price = host.current_vwap - VWAP_STOP_POINTS
        ts = host.entry_exchange_ts + EXIT_GRACE_SEC

        signal = host.manage_exit(vwap_stop_price, ts)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.audit.reason, "stop_loss_vwap")

    def test_still_in_grace_when_ticks_met_but_time_not(self):
        host = self._long_strategy()
        host.ticks_since_entry = EXIT_GRACE_TICKS
        vwap_stop_price = host.current_vwap - VWAP_STOP_POINTS
        ts = host.entry_exchange_ts + EXIT_GRACE_SEC - 1

        signal = host.manage_exit(vwap_stop_price, ts)

        self.assertIsNone(signal)

    def test_short_in_grace_vwap_stop_suppressed(self):
        host = make_host()
        host.has_position = True
        host.position_dir = "Short"
        host.entry_price = 18000.0
        host.current_vwap = 18000.0
        host.trailing_peak = 18000.0
        host.entry_exchange_ts = 1000
        host.ticks_since_entry = 5
        vwap_stop_price = host.current_vwap + VWAP_STOP_POINTS

        signal = host.manage_exit(vwap_stop_price, 1010)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
