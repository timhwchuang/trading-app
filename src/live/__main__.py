"""Thin live entry: assemble Shioaji API + TradingEngine."""

from __future__ import annotations

import shioaji as sj

from config import SIMULATION
from runtime.engine import TradingEngine


def main() -> None:
    TradingEngine(api=sj.Shioaji(simulation=SIMULATION)).start()


if __name__ == "__main__":
    main()
