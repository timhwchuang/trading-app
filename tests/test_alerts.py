"""Tests for alerts.py."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from alerts import flush_alerts_for_test, send_alert


class TestAlerts(unittest.TestCase):
    @patch("alerts._send_alert_sync", return_value=True)
    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"},
        clear=False,
    )
    def test_send_telegram(self, mock_send):
        self.assertTrue(send_alert("hello", level="WARNING"))
        flush_alerts_for_test()
        mock_send.assert_called_once_with("hello", level="WARNING")

    @patch("alerts._send_alert_sync", return_value=False)
    def test_no_channel_still_logs(self, mock_send):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(send_alert("noop"))
            flush_alerts_for_test()
            mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
