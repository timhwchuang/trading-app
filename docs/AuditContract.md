# Audit log contract (runtime → UAT / reporting)

Stable interface between live/backtest runtime and `reporting/uat_report.py`.
Do not change field names or log prefixes without updating UAT parsers and determinism tests.

## Log prefixes

| Prefix | Emitter | Consumer |
|--------|---------|----------|
| `SIGNAL_AUDIT {json}` | runtime on each `OrderSignal` | `uat_report.parse_log_audits_and_fills` |
| `FILL_AUDIT {json}` | runtime on each fill | `uat_report.parse_log_audits_and_fills` |
| `DAILY_SUMMARY {json}` | runtime on trading-day rollover / shutdown | `uat_report`, `param_sweep` |

## SIGNAL_AUDIT JSON fields

Defined in `core/audit/signal_audit.py` (`SignalAudit` dataclass):

- `intent`: `"entry"` | `"exit"`
- `direction`: `"Buy"` | `"Sell"`
- `price`, `ts`
- `vol_1s`, `buy_ratio`, `sell_ratio`
- `atr`, `multiplier`, `vol_threshold`, `vwap`
- `reason`, `trend_dir`, `trend_strength`, `trail_points_used`

Serialization: `json.dumps(asdict(audit), ensure_ascii=False, separators=(",", ":"))`

## FILL_AUDIT JSON fields

Defined in `observability.FillAudit`:

- `intent`, `direction`, `signal_price`, `fill_price`
- `slippage_pts`, `limit_price`, `slippage_vs_limit_pts`
- `order_id`, `ts`, `hold_sec`, `pnl_points`, `exit_reason`, `ioc_slippage_allowed`

## DAILY_SUMMARY JSON fields

Built by `observability.DailyObservability.build_summary()` — includes near-miss stats,
tick-type distribution, risk state, and optional `performance` block from `performance_metrics`.

## Auxiliary UAT log lines (regex-parsed)

- `MOMENTUM Long|Short 突破` — momentum trigger count
- `tick_type 分布 | ...` — tick quality
- `委託未成交/已取消` — intent cancel stats

## Determinism

`determinism_check` captures `SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY` lines only.
Canonical JSON key order must remain stable for SHA-256 gate.
