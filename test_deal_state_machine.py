"""P2-8: FuturesDeal-driven state machine tests with mock API."""

from __future__ import annotations

import unittest

from shioaji import OrderState

from test_helpers import make_strategy


class TestDealStateMachine(unittest.TestCase):
    def test_entry_deal_updates_position(self):
        strategy = make_strategy()
        strategy.is_pending = True
        strategy.pending_intent = "entry"
        strategy.pending_order_id = "ord-entry-1"
        strategy.pending_qty = 1
        strategy.pending_exchange_ts = 1000

        msg = {
            "price": "18000",
            "quantity": 1,
            "action": "Buy",
            "trade_id": "ord-entry-1",
        }
        strategy.handle_order_event(OrderState.FuturesDeal, msg)

        self.assertFalse(strategy.is_pending)
        self.assertTrue(strategy.has_position)
        self.assertEqual(strategy.position_dir, "Long")
        self.assertEqual(strategy.entry_price, 18000.0)
        self.assertEqual(strategy.entry_exchange_ts, 1000)
        self.assertEqual(strategy.ticks_since_entry, 0)

    def test_wrong_order_id_ignored(self):
        strategy = make_strategy()
        strategy.is_pending = True
        strategy.pending_intent = "entry"
        strategy.pending_order_id = "ord-a"
        strategy.pending_qty = 1

        msg = {
            "price": "18000",
            "quantity": 1,
            "action": "Buy",
            "trade_id": "ord-b",
        }
        strategy.handle_order_event(OrderState.FuturesDeal, msg)

        self.assertTrue(strategy.is_pending)
        self.assertFalse(strategy.has_position)

    def test_exit_deal_clears_position_and_updates_pnl(self):
        strategy = make_strategy()
        strategy.is_pending = True
        strategy.pending_intent = "exit"
        strategy.pending_order_id = "ord-exit-1"
        strategy.pending_qty = 1
        strategy.pending_exchange_ts = 2000
        strategy.has_position = True
        strategy.position_dir = "Long"
        strategy.entry_price = 18000.0
        strategy.trailing_peak = 18010.0
        strategy.entry_exchange_ts = 1000
        strategy.ticks_since_entry = 80

        msg = {
            "price": "18020",
            "quantity": 1,
            "action": "Sell",
            "trade_id": "ord-exit-1",
        }
        strategy.handle_order_event(OrderState.FuturesDeal, msg)

        self.assertFalse(strategy.is_pending)
        self.assertFalse(strategy.has_position)
        self.assertEqual(strategy.daily_pnl, 20.0)
        self.assertEqual(strategy.entry_exchange_ts, 0)
        self.assertEqual(strategy.ticks_since_entry, 0)


if __name__ == "__main__":
    unittest.main()
