"""P2-3: session flatten and entry cutoff tests."""

from __future__ import annotations

import datetime
import unittest

from config import (
    FLATTEN_SLIPPAGE_POINTS,
    SESSION_FLATTEN_TIME,
    SESSION_FORCE_FLATTEN_TIME,
)
from exchange_time import is_at_or_after
from test_helpers import make_strategy


def _dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute, second)


class TestSessionFlattenTimes(unittest.TestCase):
    def test_entry_blocked_from_flatten_time(self):
        self.assertFalse(is_at_or_after(_dt(13, 39, 59), SESSION_FLATTEN_TIME))
        self.assertTrue(is_at_or_after(_dt(13, 40, 0), SESSION_FLATTEN_TIME))

    def test_force_flatten_from_1344(self):
        self.assertFalse(
            is_at_or_after(_dt(13, 43, 59), SESSION_FORCE_FLATTEN_TIME)
        )
        self.assertTrue(is_at_or_after(_dt(13, 44, 0), SESSION_FORCE_FLATTEN_TIME))


class TestSessionFlattenStrategy(unittest.TestCase):
    def test_force_flatten_signal(self):
        strategy = make_strategy()
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        ts = int(_dt(13, 44).timestamp())

        signal = strategy._session_force_flatten_signal(17990.0, ts)

        self.assertEqual(signal.action, "Sell")
        self.assertEqual(signal.intent, "exit")
        self.assertEqual(signal.slippage_points, FLATTEN_SLIPPAGE_POINTS)
        self.assertIsNotNone(signal.audit)
        assert signal.audit is not None
        self.assertEqual(signal.audit.reason, "session_force_flatten")

    def test_no_entry_after_flatten_time(self):
        strategy = make_strategy()
        strategy.current_atr = 100.0
        ts = int(_dt(13, 40).timestamp())

        signal = strategy.process_strategy(ts, 18000.0, _dt(13, 40))

        self.assertIsNone(signal)

    def test_force_flatten_overrides_manage_exit(self):
        strategy = make_strategy()
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18000.0
        ts = int(_dt(13, 44).timestamp())

        signal = strategy.process_strategy(ts, 18000.0, _dt(13, 44))

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.audit.reason, "session_force_flatten")


class TestSignalAudit(unittest.TestCase):
    def test_format_is_valid_json(self):
        import json

        from core.audit.signal_audit import SignalAudit, format_signal_audit

        raw = format_signal_audit(
            SignalAudit(
                intent="entry",
                direction="Buy",
                price=18000.0,
                ts=1,
                vol_1s=200,
                buy_ratio=0.85,
                atr=30.0,
                multiplier=2.5,
                vol_threshold=375.0,
                vwap=17995.0,
                reason="pullback",
            )
        )
        parsed = json.loads(raw)
        self.assertEqual(parsed["intent"], "entry")
        self.assertEqual(parsed["vol_threshold"], 375.0)


if __name__ == "__main__":
    unittest.main()
