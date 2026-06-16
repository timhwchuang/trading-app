"""Tests for P4-11 order error classification and P4-12 session watchdog."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from core.types import OrderSignal
from order_errors import OrderErrorCategory, classify_order_error, should_retry_order
from test_helpers import arm_pending_exit, make_strategy


class TestOrderErrors(unittest.TestCase):
    def test_classify_retryable_timeout(self):
        self.assertEqual(
            classify_order_error(TimeoutError("connection timed out")),
            OrderErrorCategory.RETRYABLE,
        )

    def test_classify_fatal_balance(self):
        self.assertEqual(
            classify_order_error(RuntimeError("insufficient margin balance")),
            OrderErrorCategory.FATAL,
        )

    def test_exit_retry_policy(self):
        self.assertTrue(
            should_retry_order(
                intent="exit",
                category=OrderErrorCategory.RETRYABLE,
                attempt=0,
                max_retries=3,
            )
        )
        self.assertFalse(
            should_retry_order(
                intent="entry",
                category=OrderErrorCategory.RETRYABLE,
                attempt=0,
                max_retries=3,
            )
        )


class TestLiveGuards(unittest.TestCase):
    def test_entry_failure_clears_pending(self):
        strategy = make_strategy()
        strategy.contract = MagicMock(code="TXFR1")
        strategy.api.futopt_account = MagicMock()
        strategy.api.place_order.side_effect = TimeoutError("timeout")
        strategy.is_pending = True
        strategy.pending_intent = "entry"

        strategy.place_order(OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100))
        self.assertFalse(strategy.is_pending)

    def test_exit_failure_keeps_pending_and_schedules_retry(self):
        strategy = make_strategy()
        strategy.contract = MagicMock(code="TXFR1")
        strategy.api.futopt_account = MagicMock()
        strategy.api.place_order.side_effect = TimeoutError("timeout")
        arm_pending_exit(strategy)

        strategy.place_order(
            OrderSignal("Sell", 1, 18000.0, "exit", exchange_ts=200)
        )
        self.assertTrue(strategy.is_pending)
        self.assertGreater(strategy._exit_order_retry_at, 0)

    def test_session_watchdog_triggers_relogin(self):
        strategy = make_strategy()
        strategy._api_connected = False
        strategy._disconnect_since = strategy._clock() - 60
        strategy._session_relogin_attempts = 0
        strategy._next_relogin_at = 0
        strategy.contract = MagicMock(code="TXFR1")
        strategy.api.login = MagicMock()
        strategy._on_reconnected = MagicMock()

        strategy._check_session_watchdog()
        strategy.api.login.assert_called_once()
        strategy._on_reconnected.assert_called_once()


if __name__ == "__main__":
    unittest.main()
