"""App-level integration tests for order-event wiring (not kernel invariants)."""

from __future__ import annotations

import datetime
import unittest

from tests.test_helpers import make_host
from trading_engine.core.order_events import FUTURES_DEAL, FUTURES_ORDER


class TestIntentCancelledTag(unittest.TestCase):
    def test_open_session_entry_cancel_tag(self):
        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_order_id = "ord-1"
        host._pending_intent_cancel_exchange_dt = datetime.datetime(2026, 6, 10, 8, 50)

        with self.assertLogs("trading_engine", level="INFO") as logs:
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
        from unittest.mock import patch

        host = make_host()
        msg = {"price": "18000", "quantity": 1, "action": "Buy"}

        with patch("config.DUMP_ORDER_EVENTS", True):
            with self.assertLogs("trading_engine", level="INFO") as logs:
                host.handle_order_event(FUTURES_DEAL, msg)
                host.handle_order_event(FUTURES_DEAL, msg)
                host.handle_order_event(FUTURES_ORDER, {"status": {}})

        raw_lines = [line for line in logs.output if "RAW_ORDER_EVT" in line]
        self.assertEqual(len(raw_lines), 2)


if __name__ == "__main__":
    unittest.main()