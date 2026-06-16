#!/usr/bin/env python3
"""P0-11: Compress plain ``tick_cache/*.csv`` to ``*.csv.gz`` (scheduler / manual)."""

from __future__ import annotations

import argparse
import datetime
import logging
from pathlib import Path

from storage.tick_loader import DEFAULT_CACHE_DIR
from storage.tick_archiver import gzip_csv_file

logger = logging.getLogger(__name__)


def compress_tick_cache(
    cache_dir: Path,
    *,
    exclude_date: datetime.date | None = None,
) -> int:
    """Gzip all ``*.csv`` in *cache_dir* except the in-progress day file."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        logger.warning("快取目錄不存在: %s", cache_dir)
        return 0

    compressed = 0
    for csv_path in sorted(cache_dir.glob("*.csv")):
        if exclude_date is not None and csv_path.name.endswith(
            f"_{exclude_date.isoformat()}.csv"
        ):
            continue
        gz_path = Path(str(csv_path) + ".gz")
        if gz_path.is_file():
            continue
        try:
            gzip_csv_file(csv_path)
            compressed += 1
        except OSError as e:
            logger.warning("壓縮失敗 | %s: %s", csv_path.name, e)
    return compressed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compress tick_cache plain CSV files to .csv.gz"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Tick cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "--include-today",
        action="store_true",
        help="Also compress today's in-progress CSV (default: skip today)",
    )
    parser.add_argument(
        "--exclude-date",
        type=str,
        default="",
        help="Skip files for this date (YYYY-MM-DD); overrides default exclude-today",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    exclude: datetime.date | None = datetime.date.today()
    if args.include_today and not args.exclude_date:
        exclude = None
    elif args.exclude_date:
        exclude = datetime.date.fromisoformat(args.exclude_date)

    n = compress_tick_cache(args.cache_dir, exclude_date=exclude)
    logger.info("壓縮完成 | %d file(s) | dir=%s", n, args.cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
