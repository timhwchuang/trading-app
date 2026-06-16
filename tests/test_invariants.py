"""P0-3 / P0-8 / partial-fill defense tests."""

from __future__ import annotations

import datetime
import unittest

from exchange_time import exchange_date, trading_day_for_daily_reset
from tests.test_helpers import make_host


def _dt(hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute)


class TestTradingDayAssumption(unittest.TestCase):
    def test_day_session_uses_calendar_date(self):
        dt = _dt(8, 45)
        self.assertEqual(trading_day_for_daily_reset(dt), exchange_date(dt))


class TestTrailingPeakResync(unittest.TestCase):
    def test_long_peak_calibrated_to_max_entry_and_tick(self):
        host = make_host()
        host.has_position = True
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.trailing_peak = 18000.0
        host._resynced_position = True

        host._calibrate_trailing_peak_after_resync(18025.0)

        self.assertEqual(host.trailing_peak, 18025.0)
        self.assertFalse(host._resynced_position)

    def test_short_peak_calibrated_to_min_entry_and_tick(self):
        host = make_host()
        host.has_position = True
        host.position_dir = "Short"
        host.entry_price = 18000.0
        host.trailing_peak = 18000.0
        host._resynced_position = True

        host._calibrate_trailing_peak_after_resync(17975.0)

        self.assertEqual(host.trailing_peak, 17975.0)
        self.assertFalse(host._resynced_position)

    def test_long_peak_not_below_entry_when_tick_lower(self):
        host = make_host()
        host.has_position = True
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.trailing_peak = 18000.0
        host._resynced_position = True

        host._calibrate_trailing_peak_after_resync(17990.0)

        self.assertEqual(host.trailing_peak, 18000.0)


class TestPartialFillDefense(unittest.TestCase):
    def test_partial_entry_keeps_pending_no_full_unlock_P2_1(self):
        """P2-1: partial (1 of 2) keeps pending (IOC not fully unlocked), no position yet, no sync forced.
        Old defensive clear+sync is replaced by accum tracking for multi-lot / proper IOC support.
        """
        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_order_id = "ord-1"
        host.pending_qty = 2
        host.filled_qty = 0

        needs_sync = host._apply_deal_fill(18000.0, is_buy=True, deal_qty=1)

        self.assertFalse(needs_sync)
        self.assertTrue(host.is_pending)  # still armed for remaining fill or cancel
        self.assertEqual(host.filled_qty, 1)
        self.assertFalse(host.has_position)

    def test_full_fill_entry_unchanged(self):
        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_qty = 1

        needs_sync = host._apply_deal_fill(18000.0, is_buy=True, deal_qty=1)

        self.assertFalse(needs_sync)
        self.assertTrue(host.has_position)
        self.assertEqual(host.entry_price, 18000.0)


class TestAtrKlineStart(unittest.TestCase):
    def test_long_lookback_when_atr_zero(self):
        import datetime

        from runtime.engine import TradingEngine

        today = datetime.date(2026, 6, 10)
        start, used_long = TradingEngine._atr_kline_start(
            today,
            current_atr=0.0,
            long_lookback_days=10,
            long_lookback_done_for=today,
        )
        self.assertTrue(used_long)
        self.assertEqual(start, today - datetime.timedelta(days=10))

    def test_intraday_when_atr_ready(self):
        import datetime

        from runtime.engine import TradingEngine

        today = datetime.date(2026, 6, 10)
        start, used_long = TradingEngine._atr_kline_start(
            today,
            current_atr=30.0,
            long_lookback_days=10,
            long_lookback_done_for=today,
        )
        self.assertFalse(used_long)
        self.assertEqual(start, today)


class TestFutoptAccountGuard(unittest.TestCase):
    def test_none_futopt_account_raises(self):
        from unittest.mock import MagicMock

        host = make_host()
        host.api = MagicMock(futopt_account=None)

        with self.assertRaises(RuntimeError) as ctx:
            host._require_futopt_account()

        self.assertIn("無期貨帳號", str(ctx.exception))


class TestIntentCancelledTag(unittest.TestCase):
    def test_open_session_entry_cancel_tag(self):
        import datetime

        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_order_id = "ord-1"
        host._pending_intent_cancel_exchange_dt = datetime.datetime(
            2026, 6, 10, 8, 50
        )

        with self.assertLogs("theman", level="INFO") as logs:
            host._handle_futures_order(
                {
                    "trade_id": "ord-1",
                    "operation": {"op_type": "Cancel", "op_code": "00"},
                    "status": {"status": "Cancelled", "deal_quantity": 0},
                }
            )

        self.assertFalse(host.is_pending)
        cancelled = [line for line in logs.output if "intent_cancelled" in line]
        self.assertEqual(len(cancelled), 1)
        self.assertIn("intent_cancelled_open_session", cancelled[0])


class TestRawOrderEventDump(unittest.TestCase):
    def test_dumps_each_stat_type_once_when_enabled(self):
        from shioaji import OrderState
        from unittest.mock import patch

        host = make_host()
        msg = {"price": "18000", "quantity": 1, "action": "Buy"}

        with patch("config.DUMP_ORDER_EVENTS", True):
            with self.assertLogs("theman", level="INFO") as logs:
                host.handle_order_event(OrderState.FuturesDeal, msg)
                host.handle_order_event(OrderState.FuturesDeal, msg)
                host.handle_order_event(OrderState.FuturesOrder, {"status": {}})

        raw_lines = [line for line in logs.output if "RAW_ORDER_EVT" in line]
        self.assertEqual(len(raw_lines), 2)


class TestDisconnectGating(unittest.TestCase):
    def test_disconnected_blocks_entry_but_allows_exit(self):
        host = make_host()
        host._api_connected = False
        host.has_position = True
        host.position_dir = "Long"
        host.entry_price = 18000.0
        host.trailing_peak = 18000.0
        host.current_atr = 100.0
        ts = int(_dt(10, 0).timestamp())

        signal = host.process_strategy(ts, 17990.0, _dt(10, 0))

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.intent, "exit")


if __name__ == "__main__":
    unittest.main()
