"""RuntimeConfig bridge tests."""

from __future__ import annotations

import unittest
from unittest import mock

import config as config_module
from core.runtime_config import (
    TradingAppRuntimeConfig,
    _to_engine_settings,
    default_runtime_config,
)
from trading_engine.core.runtime_config import RuntimeConfig as EngineRuntimeConfig


class TestTradingAppRuntimeConfig(unittest.TestCase):
    def test_archive_flags_delegate_to_config_module(self):
        cfg = TradingAppRuntimeConfig(_to_engine_settings())
        with mock.patch.object(config_module, "TICK_ARCHIVE", True):
            self.assertTrue(cfg.tick_archive)
        with mock.patch.object(config_module, "KBARS_ARCHIVE", True):
            self.assertTrue(cfg.kbars_archive)
        with mock.patch.object(config_module, "DUMP_ORDER_EVENTS", True):
            self.assertTrue(cfg.dump_order_events)

    def test_default_runtime_config_tick_archive_from_env(self):
        with mock.patch.object(config_module, "TICK_ARCHIVE", True):
            cfg = default_runtime_config()
            self.assertTrue(cfg.tick_archive)

    def test_engine_runtime_config_archive_flags_default_false(self):
        cfg = EngineRuntimeConfig(_to_engine_settings())
        self.assertFalse(cfg.tick_archive)
        self.assertFalse(cfg.kbars_archive)
        self.assertFalse(cfg.dump_order_events)


if __name__ == "__main__":
    unittest.main()