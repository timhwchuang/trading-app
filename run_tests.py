#!/usr/bin/env python3
"""Run unit tests with ``src/`` on sys.path (flat imports)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    raise SystemExit(
        unittest.main(
            module=None,
            argv=["", "discover", "-s", str(_ROOT / "tests"), "-v"],
            exit=True,
        )
    )
