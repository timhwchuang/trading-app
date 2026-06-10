"""P2-7: Parse strategy log and report UAT metrics from SIGNAL_AUDIT + MOMENTUM lines."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from signal_audit import SignalAudit

MOMENTUM_TRIGGER_RE = re.compile(r"MOMENTUM (Long|Short) 突破")
SIGNAL_AUDIT_RE = re.compile(r"SIGNAL_AUDIT (.+)$")


@dataclass
class TradeRound:
    entry_ts: int
    entry_direction: str
    exit_ts: int | None = None
    exit_reason: str = ""


def parse_signal_audit_line(line: str) -> SignalAudit | None:
    match = SIGNAL_AUDIT_RE.search(line)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return SignalAudit(**payload)


def count_momentum_triggers(lines: list[str]) -> int:
    return sum(1 for line in lines if MOMENTUM_TRIGGER_RE.search(line))


def build_trade_rounds(audits: list[SignalAudit]) -> list[TradeRound]:
    rounds: list[TradeRound] = []
    open_round: TradeRound | None = None

    for audit in audits:
        if audit.intent == "entry":
            if open_round is not None:
                rounds.append(open_round)
            open_round = TradeRound(
                entry_ts=audit.ts,
                entry_direction=audit.direction,
            )
        elif audit.intent == "exit":
            if open_round is None:
                continue
            open_round.exit_ts = audit.ts
            open_round.exit_reason = audit.reason
            rounds.append(open_round)
            open_round = None

    if open_round is not None:
        rounds.append(open_round)

    return rounds


def compute_metrics(
    lines: list[str],
    *,
    quick_sl_sec: int = 5,
) -> dict:
    momentum_triggers = count_momentum_triggers(lines)
    audits = [
        audit
        for line in lines
        if (audit := parse_signal_audit_line(line)) is not None
    ]
    entries = [a for a in audits if a.intent == "entry"]
    exits = [a for a in audits if a.intent == "exit"]
    rounds = build_trade_rounds(audits)
    completed = [r for r in rounds if r.exit_ts is not None]

    stop_loss_reasons = {"stop_loss", "stop_loss_vwap"}
    quick_stop_loss = [
        r
        for r in completed
        if r.exit_reason in stop_loss_reasons
        and r.exit_ts is not None
        and (r.exit_ts - r.entry_ts) < quick_sl_sec
    ]

    exit_reasons: dict[str, int] = {}
    for audit in exits:
        exit_reasons[audit.reason] = exit_reasons.get(audit.reason, 0) + 1

    conversion_rate = (
        len(entries) / momentum_triggers if momentum_triggers else None
    )
    quick_sl_rate = (
        len(quick_stop_loss) / len(completed) if completed else None
    )

    return {
        "momentum_triggers": momentum_triggers,
        "entry_signals": len(entries),
        "exit_signals": len(exits),
        "momentum_to_entry_conversion": conversion_rate,
        "completed_rounds": len(completed),
        "open_rounds": len(rounds) - len(completed),
        f"quick_stop_loss_lt_{quick_sl_sec}s": len(quick_stop_loss),
        f"quick_stop_loss_rate_lt_{quick_sl_sec}s": quick_sl_rate,
        "exit_reasons": exit_reasons,
        "quick_stop_loss_examples": [
            {
                "direction": r.entry_direction,
                "entry_ts": r.entry_ts,
                "exit_ts": r.exit_ts,
                "hold_sec": (r.exit_ts - r.entry_ts) if r.exit_ts else None,
            }
            for r in quick_stop_loss[:10]
        ],
    }


def format_report(metrics: dict, *, quick_sl_sec: int = 5) -> str:
    conv = metrics["momentum_to_entry_conversion"]
    qsl_rate = metrics[f"quick_stop_loss_rate_lt_{quick_sl_sec}s"]
    conv_text = f"{conv:.1%}" if conv is not None else "N/A"
    qsl_text = f"{qsl_rate:.1%}" if qsl_rate is not None else "N/A"

    lines = [
        "=== UAT Report (P2-7) ===",
        f"動量觸發數:           {metrics['momentum_triggers']}",
        f"進場 signal 數:       {metrics['entry_signals']}",
        f"出場 signal 數:       {metrics['exit_signals']}",
        f"動量→進場轉換率:      {conv_text}",
        f"完整 round-trip:      {metrics['completed_rounds']}",
        f"未平倉 round:         {metrics['open_rounds']}",
        (
            f"秒停損 (<{quick_sl_sec}s, stop_loss): "
            f"{metrics[f'quick_stop_loss_lt_{quick_sl_sec}s']} ({qsl_text})"
        ),
    ]

    if metrics["exit_reasons"]:
        lines.append("出場 reason 分布:")
        for reason, count in sorted(metrics["exit_reasons"].items()):
            lines.append(f"  {reason or '(empty)'}: {count}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze theman log for UAT metrics (P2-7)."
    )
    parser.add_argument(
        "log_file",
        type=Path,
        help="Strategy log file containing SIGNAL_AUDIT and MOMENTUM lines",
    )
    parser.add_argument(
        "--quick-sl-sec",
        type=int,
        default=5,
        help="Seconds threshold for quick stop-loss (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metrics as JSON instead of text report",
    )
    args = parser.parse_args(argv)

    if not args.log_file.is_file():
        print(f"找不到 log 檔: {args.log_file}", file=sys.stderr)
        return 1

    lines = args.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    metrics = compute_metrics(lines, quick_sl_sec=args.quick_sl_sec)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(format_report(metrics, quick_sl_sec=args.quick_sl_sec))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
