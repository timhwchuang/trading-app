"""CLI: P6-1-CAL B-class trend filter calibration (log + tick replay + optional sweep)."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from reporting.forward_pnl import ForwardPnlPolicy
from reporting.trend_calibration import (
    DEFAULT_TREND_MIN_STRENGTH_GRID,
    run_b_class_calibration,
)
from storage.tick_loader import DEFAULT_CACHE_DIR
from sweep.param_sweep import sweep


def _parse_dates(raw: str) -> list[datetime.date]:
    out: list[datetime.date] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.append(datetime.date.fromisoformat(part))
    if not out:
        raise ValueError("at least one --date required")
    return out


def format_calibration_report(result: dict) -> str:
    lines = ["=== P6-1 Trend Filter Calibration (B-class) ==="]
    if result.get("status") == "no_ticks":
        lines.append("狀態: 無 tick 快取 — 請先 UAT 累積 TICK_ARCHIVE 或指定 --cache-dir")
        lines.append(f"code={result.get('code')} dates={result.get('dates')}")
        lines.append(f"forward_policy={result.get('forward_policy')}")
        lines.append(f"veto={result.get('n_veto')} allowed={result.get('n_allowed')}")
        return "\n".join(lines)

    lines.append(f"status={result.get('status')} code={result.get('code')}")
    lines.append(f"dates={result.get('dates')} ticks={result.get('tick_count')}")
    lines.append(f"forward_policy={result.get('forward_policy')}")
    lines.append(
        f"veto_rate={result.get('veto_rate')} "
        f"(n_veto={result.get('n_veto')} n_allowed={result.get('n_allowed')})"
    )
    lines.append(
        f"mean_forward_if_vetoed={result.get('mean_forward_if_vetoed')} "
        f"mean_forward_allowed={result.get('mean_forward_allowed')}"
    )
    lines.append(f"delta_expectancy={result.get('delta_expectancy')}")
    lines.append(f"notes: {result.get('notes')}")
    return "\n".join(lines)


def run_trend_sensitivity_sweep(
    *,
    code: str,
    dates_train: list[datetime.date],
    dates_valid: list[datetime.date],
    cache_dir: Path,
    forward_policy: ForwardPnlPolicy,
    output_path: Path | None = None,
    min_strength_grid: list[float] | None = None,
) -> list[dict]:
    """CAL-3 B-class: walk-forward grid over trend_min_strength with replay veto_metrics."""
    grid = {
        "trend_filter_enabled": [True],
        "trend_min_strength": min_strength_grid or DEFAULT_TREND_MIN_STRENGTH_GRID,
    }
    return sweep(
        grid,
        dates_train,
        dates_valid,
        code,
        cache_dir=cache_dir,
        forward_policy=forward_policy,
        output_path=output_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="P6-1-CAL B-class: trend veto harness from log + tick_cache replay."
    )
    parser.add_argument(
        "log_files",
        nargs="+",
        type=Path,
        help="Strategy log(s) with SIGNAL_AUDIT (incl. trend_veto)",
    )
    parser.add_argument("--code", default="TXFR1", help="Contract code (default: TXFR1)")
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated YYYY-MM-DD tick_cache dates for forward PnL",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="tick_cache directory",
    )
    parser.add_argument(
        "--forward-seconds",
        type=int,
        default=1800,
        help="Forward window seconds (default 1800 ≈ 30×1m)",
    )
    parser.add_argument(
        "--forward-mode",
        choices=("fixed_seconds", "fixed_ticks", "session_end"),
        default="fixed_seconds",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Also run trend_min_strength sensitivity sweep on valid dates",
    )
    parser.add_argument(
        "--train-dates",
        help="Train dates for sweep (comma-separated); default first half of --dates",
    )
    parser.add_argument(
        "--valid-dates",
        help="Valid dates for sweep (comma-separated); default second half of --dates",
    )
    parser.add_argument(
        "--sweep-output",
        type=Path,
        help="Write sweep_result.jsonl here when --sweep",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    for path in args.log_files:
        if not path.is_file():
            print(f"找不到 log 檔: {path}", file=sys.stderr)
            return 1

    dates = _parse_dates(args.dates)
    policy = ForwardPnlPolicy(
        mode=args.forward_mode,
        window_seconds=args.forward_seconds,
    )

    result = run_b_class_calibration(
        log_paths=args.log_files,
        code=args.code,
        dates=dates,
        cache_dir=args.cache_dir,
        forward_policy=policy,
    )

    if args.sweep:
        if args.train_dates and args.valid_dates:
            train_dates = _parse_dates(args.train_dates)
            valid_dates = _parse_dates(args.valid_dates)
        else:
            mid = max(1, len(dates) // 2)
            train_dates = dates[:mid]
            valid_dates = dates[mid:] or dates
        sweep_rows = run_trend_sensitivity_sweep(
            code=args.code,
            dates_train=train_dates,
            dates_valid=valid_dates,
            cache_dir=args.cache_dir,
            forward_policy=policy,
            output_path=args.sweep_output,
        )
        result["sensitivity_sweep"] = [
            {
                "params": row["params"],
                "valid_score": row["valid_score"],
                "veto_metrics": row.get("veto_metrics"),
            }
            for row in sweep_rows
        ]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_calibration_report(result))
        if args.sweep and result.get("sensitivity_sweep"):
            print()
            print("=== trend_min_strength sensitivity (valid set) ===")
            for row in result["sensitivity_sweep"]:
                vm = row.get("veto_metrics") or {}
                print(
                    f"min_strength={row['params'].get('trend_min_strength')} "
                    f"valid_score={row['valid_score']:.2f} "
                    f"delta={vm.get('delta_expectancy')} veto_rate={vm.get('veto_rate')}"
                )

    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())