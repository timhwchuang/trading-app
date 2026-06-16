"""P1: single canonical tick_cache path for backtest + sweep + B-class replay."""

from __future__ import annotations

import unittest

from backtest.engine import BacktestEngine
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.tick_loader import DEFAULT_CACHE_DIR
from sweep.param_sweep import sweep


class TestCachePathsUnified(unittest.TestCase):
    def test_tick_loader_and_cache_paths_match(self):
        self.assertEqual(DEFAULT_CACHE_DIR, DEFAULT_TICK_CACHE_DIR)
        self.assertTrue(DEFAULT_TICK_CACHE_DIR.name == "tick_cache")
        self.assertTrue(DEFAULT_TICK_CACHE_DIR.is_absolute())

    def test_backtest_engine_default_cache_is_repo_tick_cache(self):
        import inspect

        sig = inspect.signature(BacktestEngine.__init__)
        default = sig.parameters["cache_dir"].default
        self.assertEqual(default, DEFAULT_TICK_CACHE_DIR)

    def test_sweep_default_cache_is_repo_tick_cache(self):
        import inspect

        sig = inspect.signature(sweep)
        default = sig.parameters["cache_dir"].default
        self.assertEqual(default, DEFAULT_TICK_CACHE_DIR)


if __name__ == "__main__":
    unittest.main()