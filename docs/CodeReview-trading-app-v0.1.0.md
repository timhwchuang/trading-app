# Code Review — trading-app v0.1.0

**Date**: 2026-06-16  
**Scope**: theman → trading-app migration, shim removal, test fixes, strategy `trend_dir` bugfix  
**Tests**: `python run_tests.py` — **69 OK**

## Verdict

**PASS for v0.1.0 tag** — 0 high-severity blockers.

Architecture direction correct: app composes siblings via `trading_app_engine_ports()`; no kernel leakage into app; re-export shims removed.

## High severity

_None._

## Medium severity

1. ~~**Local folder still `theman/`**~~ — **Resolved** (renamed to `trading-app/`; pushed to GitHub).

2. **strategy-vwap-momentum `trend_dir` fix** — Patched locally in monorepo (`strategy.py` `_try_pullback_entry`). Published git tag `v0.1.0` may still lack fix until `v0.1.1` tag. trading-app CI installs from git tag — verify tag includes fix or bump pin.

3. **MockBroker string close** — `trading-backtest` v0.1.0 compares `tick.close` without `float()`. Sweep tests use numeric close via `_tick_helpers.py`. Real CSV replay (string close) may hit same issue in live backtest — follow-up in `trading-backtest`.

## Low severity

1. **Deprecated aliases** — `theman_engine_ports`, `ThemanTelemetryPort`, etc. kept one cycle. Remove in v0.2.0.

2. **Docs drift** — `TODO.md`, `WeeklyStatus.md`, historical CodeReview files still mention theman heavily. Non-blocking for tag; batch update post-UAT.

3. **`reporting/contract.py` split** — Deferred; `uat_report.py` imports `SignalAudit` from `trading_engine` directly (acceptable).

## Checks passed

- [x] `simulation: true` in `config/config.yaml`
- [x] No secrets in repo; `.env.example` present
- [x] Logger capture uses `trading_engine` + `strategy_vwap_momentum` (not `theman`)
- [x] `requirements.txt` git pins for standalone CI
- [x] App tests scoped to integration (~69); kernel tests removed from app
- [x] `uat_report` remains in `reporting/` (correct layer)

## Tag recommendation

Proceed with `v0.1.0` after:

1. Push `strategy-vwap-momentum` patch as `v0.1.1` (or cherry-pick into existing tag before push)
2. Rename local directory `theman` → `trading-app` when IDE releases lock
3. ~~`git push origin main && git push origin v0.1.0`~~ — **Done** (2026-06-16).