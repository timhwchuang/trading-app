"""Tests for P0-11 tick archiver and compress_tick_cache."""

from __future__ import annotations

import datetime
import gzip
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from storage.compress import compress_tick_cache
from storage.tick_loader import (
    ReplayTick,
    cache_path,
    iter_replay_ticks,
    load_ticks_csv,
    resolve_tick_cache_path,
    save_ticks_csv,
)
from storage.tick_archiver import TickArchiveRecord, TickArchiver, gzip_csv_file


def _record(
    dt: datetime.datetime,
    *,
    close: str = "18000",
    volume: int = 1,
    tick_type: int = 1,
) -> TickArchiveRecord:
    return TickArchiveRecord(
        datetime=dt,
        close=close,
        volume=volume,
        tick_type=tick_type,
        bid_price=17999.0,
        ask_price=18001.0,
    )


class TestGzipCsv(unittest.TestCase):
    def test_gzip_csv_roundtrip(self):
        ticks = [
            ReplayTick(
                datetime=datetime.datetime(2026, 6, 12, 9, 0),
                close="18000",
                volume=2,
                tick_type=1,
            )
        ]
        with tempfile.TemporaryDirectory() as d:
            csv_path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            save_ticks_csv(ticks, csv_path)
            gz_path = gzip_csv_file(csv_path)
            self.assertFalse(csv_path.is_file())
            self.assertTrue(gz_path.is_file())
            loaded = load_ticks_csv(gz_path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].close, "18000")


class TestResolveTickCachePath(unittest.TestCase):
    def test_prefers_gz_over_plain(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            date = datetime.date(2026, 6, 12)
            plain = cache_path(root, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9), "18000", 1, 0)],
                plain,
            )
            gz_path = gzip_csv_file(plain)
            resolved = resolve_tick_cache_path(root, "TXFR1", date)
            self.assertEqual(resolved, gz_path)


class TestTickArchiver(unittest.TestCase):
    def test_enqueue_flush_shutdown(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=2,
                flush_interval_sec=0.05,
                queue_maxsize=100,
            )
            archiver.start()
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 1))
            )
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 2), close="18001")
            )
            time.sleep(0.2)
            archiver.shutdown()

            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            self.assertTrue(path.is_file())
            loaded = load_ticks_csv(path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[1].close, "18001")
            self.assertEqual(archiver.written, 2)
            self.assertEqual(archiver.dropped, 0)

    def test_day_rotation_gzips_previous_csv(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=1,
                flush_interval_sec=0.05,
            )
            archiver.start()
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 11, 13, 44, 59))
            )
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 0))
            )
            time.sleep(0.25)
            archiver.shutdown()

            root = Path(d)
            old_plain = cache_path(root, "TXFR1", datetime.date(2026, 6, 11))
            new_plain = cache_path(root, "TXFR1", datetime.date(2026, 6, 12))
            old_gz = Path(str(old_plain) + ".gz")
            self.assertFalse(old_plain.is_file())
            self.assertTrue(old_gz.is_file())
            self.assertTrue(new_plain.is_file())
            self.assertEqual(len(load_ticks_csv(old_gz)), 1)
            self.assertEqual(len(load_ticks_csv(new_plain)), 1)

    def test_queue_full_drops_without_blocking(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                queue_maxsize=1,
                flush_batch=1000,
                flush_interval_sec=60.0,
            )
            archiver.start()
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0)))
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0, 1)))
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0, 2)))
            time.sleep(0.05)
            archiver.shutdown()
            self.assertGreaterEqual(archiver.dropped, 1)

    def test_interval_flush_during_continuous_stream(self):
        """Time-based flush must fire even when queue never empties."""
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=500,
                flush_interval_sec=0.1,
                queue_maxsize=100,
            )
            archiver.start()
            base = datetime.datetime(2026, 6, 12, 9, 0)
            for i in range(5):
                archiver.enqueue(_record(base.replace(second=i)))
            time.sleep(0.25)
            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            self.assertTrue(path.is_file())
            self.assertEqual(len(load_ticks_csv(path)), 5)
            archiver.shutdown()

    def test_enqueue_tick_from_mock(self):
        tick = MagicMock()
        tick.datetime = datetime.datetime(2026, 6, 12, 9, 0)
        tick.close = "18010"
        tick.volume = 4
        tick.bid_price = 18009.0
        tick.ask_price = 18011.0

        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=1,
                flush_interval_sec=0.05,
            )
            archiver.start()
            archiver.enqueue_tick(tick, tick_type=2)
            time.sleep(0.15)
            archiver.shutdown()

            loaded = load_ticks_csv(
                cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            )
            self.assertEqual(loaded[0].tick_type, 2)
            self.assertEqual(loaded[0].volume, 4)


class TestCompressTickCache(unittest.TestCase):
    def test_compress_default_excludes_today(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            save_ticks_csv(
                [
                    ReplayTick(
                        datetime.datetime.combine(yesterday, datetime.time(9)),
                        "18000",
                        1,
                        0,
                    )
                ],
                cache_path(root, "TXFR1", yesterday),
            )
            save_ticks_csv(
                [
                    ReplayTick(
                        datetime.datetime.combine(today, datetime.time(9)),
                        "18010",
                        1,
                        0,
                    )
                ],
                cache_path(root, "TXFR1", today),
            )
            n = compress_tick_cache(root, exclude_date=today)
            self.assertEqual(n, 1)
            self.assertTrue(cache_path(root, "TXFR1", today).is_file())
            self.assertTrue(
                Path(str(cache_path(root, "TXFR1", yesterday)) + ".gz").is_file()
            )

    def test_compress_excludes_today(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            d1 = datetime.date(2026, 6, 11)
            d2 = datetime.date(2026, 6, 12)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 11, 9), "18000", 1, 0)],
                cache_path(root, "TXFR1", d1),
            )
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9), "18010", 1, 0)],
                cache_path(root, "TXFR1", d2),
            )
            n = compress_tick_cache(root, exclude_date=d2)
            self.assertEqual(n, 1)
            self.assertTrue(cache_path(root, "TXFR1", d2).is_file())
            self.assertTrue(Path(str(cache_path(root, "TXFR1", d1)) + ".gz").is_file())

    def test_iter_replay_ticks_reads_gz(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            date = datetime.date(2026, 6, 12)
            plain = cache_path(root, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9), "18055", 1, 0)],
                plain,
            )
            gzip_csv_file(plain)
            ticks = list(iter_replay_ticks("TXFR1", [date], cache_dir=root))
            self.assertEqual(len(ticks), 1)
            self.assertEqual(ticks[0].close, "18055")


if __name__ == "__main__":
    unittest.main()
