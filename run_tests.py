#!/usr/bin/env python3
"""Run unit tests with ``src/`` and ``tests/`` on sys.path.

Supports the mirrored layout under tests/ (backtest/, runtime/, storage/ etc.)
while preserving cross-test imports such as ``from tests.test_helpers import ...``.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_TE_ROOT = _ROOT / "trading-engine"
_TE_SRC = _TE_ROOT / "src"
_SRC = _ROOT / "src"


def _ensure_trading_engine() -> None:
    """Prefer installed package; else editable install; else vendored/sibling src."""
    try:
        import trading_engine  # noqa: F401
        return
    except ImportError:
        pass

    sibling = _ROOT.parent / "trading-engine"
    for candidate in (_TE_ROOT, sibling):
        if (candidate / "pyproject.toml").is_file():
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-e", str(candidate), "-q"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                import trading_engine  # noqa: F401
                return
            except (subprocess.CalledProcessError, ImportError):
                src = candidate / "src"
                if src.is_dir():
                    sys.path.insert(0, str(src))
                    return


_ensure_trading_engine()

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