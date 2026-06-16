# Sweep & Determinism Spec

> **Owner**: `trading-app` (`src/sweep/`, `src/reporting/`)  
> **Backtest driver**: `trading-backtest`  
> **Strategy params**: `strategy-vwap-momentum` [CALIBRATION.md](https://github.com/timhwchuang/strategy-vwap-momentum/blob/main/docs/CALIBRATION.md)

App-layer research tooling: determinism hash gate + walk-forward param sweep. Former monolith `BackTestingSpec.md` Phase 4–5 + hash-related Phase 6/7 items.

---

## Phase 4 — Determinism (`sweep/determinism_check.py`)

### `run_hash(code, dates, cache_dir) -> str`

Collect `SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY` JSON; normalize; SHA-256.

Rules:

- Hash JSON body only (no log timestamps)
- `sort_keys=True, separators=(",", ":")` (6.8)
- Strip `DAILY_SUMMARY.operational` wall-clock fields: `lock_wait_max_ms`, `lock_wait_over_50ms`, `no_tick_resubscribe`, `atr_min`, `atr_max` (7.5)
- Include `DAILY_SUMMARY` decision fields (6.2)

### Acceptance (`tests/sweep/test_determinism.py`)

| Test | Purpose |
|------|---------|
| `test_three_runs_same_hash` | Empty/degenerate path stable |
| `test_three_runs_same_hash_with_kbars_and_fills` | Real fills path (7.6) |
| `test_daily_summary_in_hash` | KPI change changes hash |
| `test_hash_robust_to_key_order` | Key order immune |
| `test_hash_ignores_operational_wall_clock` | Operational fields excluded |
| `test_uat_report_parses_backtest_log` | Reporting integration |

---

## Phase 5 — Param sweep (`sweep/param_sweep.py`)

### `sweep(grid, dates_train, dates_valid, code, cache_dir)`

For each grid point:

1. Patch strategy params via `StrategyParams` / config overlay (6.6, 7.7)
2. Run train backtest → KPI
3. Run valid backtest → KPI (out-of-sample)
4. Emit `{params, train_kpi, valid_kpi, veto_metrics?}`

**Walk-forward**: rank on **valid** only.

Output: `sweep_result.jsonl`

### Trend grid (CAL-3)

When grid contains `trend_*` keys, attach `veto_metrics` from harness.

**B-class replay**: pass `forward_policy=ForwardPnlPolicy(...)` to `sweep()`. When tick_cache has data for `dates_valid`, `veto_metrics.delta_expectancy` uses `reporting/forward_pnl.py` (not toy 0). CLI: `python -m reporting.calibration_cli ... --sweep`.

### KPI aggregation (7.8)

`quick_stop_loss_rate` = `Σ quick_sl / Σ exits` (weighted, not daily average).

### Acceptance (`tests/sweep/test_param_sweep.py`)

- `test_sweep_small_grid`
- `test_config_restored`
- `test_daily_summary_params_match_sweep`
- `test_sweep_params_affect_entry`
- `test_sweep_with_trend_params_attaches_veto_metrics`

---

## Reporting integration

- `python -m reporting <log>` — UAT / backtest log parser
- `reporting/trend_calibration.py` — veto harness (see strategy CALIBRATION.md)
- `reporting/performance_metrics.py` — survival KPIs for sweep scoring

---

## File map

| Module | Path |
|--------|------|
| Determinism | `src/sweep/determinism_check.py` |
| Param sweep | `src/sweep/param_sweep.py` |
| UAT report | `src/reporting/uat_report.py` |
| Trend harness | `src/reporting/trend_calibration.py` |
| Forward PnL replay | `src/reporting/forward_pnl.py` |
| B-class CLI | `src/reporting/calibration_cli.py` |
| Tests | `tests/sweep/`, `tests/reporting/` |

---

## Definition of done (app integration)

- [x] `python run_tests.py` — 79 tests green
- [x] Same inputs → same hash (with fills path)
- [x] Sweep restores config after grid
- [x] `uat_report` parses backtest logs

**Not a UAT gate** — research / calibration tooling only.