#!/usr/bin/env python3
"""Run unit tests with ``src/`` and ``tests/`` on sys.path.

Supports the mirrored layout under tests/ (backtest/, runtime/, storage/ etc.)
while preserving cross-test imports such as ``from tests.test_helpers import ...``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Make the project root importable. This lets tests (including those in subpackages
# such as tests/backtest/) use clean absolute imports like ``from tests.test_helpers import ...``.
# src/ remains early enough on sys.path that bare production packages (backtest, runtime,
# storage, reporting, strategy, sweep) always resolve from src/ and are never shadowed
# (no bare package directories with those names exist at the project root).
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Maintenance note (for future src/ changes):
# When adding a new package under src/ (e.g. src/foo/), create the mirror
# tests/foo/ (with __init__.py) and move or add the corresponding test_*.py there.
# Keep test_helpers.py and tests for top-level src/*.py modules at tests/ root.
# Always verify with `python run_tests.py` after structural changes.

if __name__ == "__main__":
    raise SystemExit(
        unittest.main(
            module=None,
            argv=["", "discover", "-s", str(_ROOT / "tests"), "-t", str(_ROOT), "-v"],
            exit=True,
        )
    )
