"""Tests for integrations.engine_wiring."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

from integrations.engine_wiring import default_strategy, trading_app_engine_ports
from trading_engine.logging_setup import shutdown_async_logging


class TestEngineWiring(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_async_logging()

    def test_shared_obs_between_telemetry_and_strategy(self):
        api = MagicMock()
        ports = trading_app_engine_ports(api=api, use_mock_adapter=True)
        strategy = default_strategy(ports["runtime_config"], ports["obs"])

        self.assertIs(strategy.obs, ports["obs"])
        self.assertIs(ports["telemetry"].underlying, ports["obs"])

    def test_log_file_env_writes_audit_lines(self):
        import integrations.engine_wiring as wiring

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "uat.log"
            wiring._logging_configured = False
            with mock.patch.object(wiring, "LOG_FILE", str(log_path)):
                with mock.patch.object(wiring, "LOG_LEVEL", "INFO"):
                    api = MagicMock()
                    wiring.trading_app_engine_ports(api=api, use_mock_adapter=True)
                    logging.getLogger("trading_engine").info("SIGNAL_AUDIT smoke")
                    shutdown_async_logging()
                    self.assertTrue(log_path.exists())
                    self.assertIn("SIGNAL_AUDIT", log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()