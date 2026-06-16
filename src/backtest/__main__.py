"""CLI: run tick replay backtest (delegates to trading-backtest)."""

from __future__ import annotations

import argparse
import datetime
import logging

from storage.tick_loader import DEFAULT_CACHE_DIR

# App-wired BacktestEngine (trading-app ports + default strategy)
from .engine import BacktestEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run VWAP momentum backtest")
    parser.add_argument("--code", default="TXFR1", help="Futures product code")
    parser.add_argument(
        "--dates",
        nargs="+",
        required=True,
        help="Trade dates YYYY-MM-DD",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=str(DEFAULT_CACHE_DIR),
        help="Tick cache directory",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    dates = [datetime.date.fromisoformat(d) for d in args.dates]
    engine = BacktestEngine(args.code, dates, cache_dir=args.cache_dir)
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
