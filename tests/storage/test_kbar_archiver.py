"""Tests for kbar_archiver."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from storage.kbar_loader import load_kbars_csv
from storage.kbar_archiver import archive_kbars_snapshot


class TestKbarArchiver(unittest.TestCase):
    def test_archive_writes_csv(self):
        ts = int(
            datetime.datetime(2026, 6, 12, 9, 0).timestamp() * 1_000_000_000
        )
        raw = SimpleNamespace(
            ts=[ts],
            Open=[18000.0],
            High=[18010.0],
            Low=[17990.0],
            Close=[18005.0],
            Volume=[100],
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            count = archive_kbars_snapshot(
                raw,
                product_code="TXFR1",
                trade_date=datetime.date(2026, 6, 12),
                cache_dir=cache,
            )
            self.assertEqual(count, 1)
            bars = load_kbars_csv(cache / "TXFR1_kbars_2026-06-12.csv")
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].Close, 18005.0)


if __name__ == "__main__":
    unittest.main()
