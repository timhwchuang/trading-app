"""Tick replay entry point for backtests (patch anchor for tests)."""

from trading_backtest.loader import DEFAULT_CACHE_DIR, iter_replay_ticks

__all__ = ["DEFAULT_CACHE_DIR", "iter_replay_ticks"]