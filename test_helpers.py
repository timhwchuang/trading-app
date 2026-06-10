"""Shared test utilities (P2-8: avoid real Shioaji client in unit tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

from man import VWAPMomentumStrategy


def make_strategy() -> VWAPMomentumStrategy:
    return VWAPMomentumStrategy(api=MagicMock())
