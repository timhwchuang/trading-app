"""Tests for alerts.py."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from alerts import send_alert


class TestAlerts(unittest.TestCase):
    @patch("alerts._post_json", return_value=True)
    @patch.dict(
        "os.environ",
        {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"},
        clear=False,
    )
    def test_send_telegram(self, mock_post):
        self.assertTrue(send_alert("hello", level="WARNING"))
        mock_post.assert_called_once()

    def test_no_channel_still_logs(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(send_alert("noop"))


if __name__ == "__main__":
    unittest.main()
