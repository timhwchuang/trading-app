# Changelog

All notable changes to `trading-app` are documented here.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [SemVer](https://semver.org/) (0.x = API may still evolve).

## [Unreleased]

## [0.1.2] - 2026-06-17

### Added

- P4-13 `operations` config: reconnect warmup, disconnect limits, `atr_stale_multiplier`
- Cumulative MDD risk budget in `uat_report` / `performance_metrics` (`initial_capital_points`, `max_acceptable_mdd_points`)
- [`docs/UPGRADE_RUNBOOK.md`](docs/UPGRADE_RUNBOOK.md) — four-repo upgrade SOP

### Changed

- Pin `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- Docs sync: README, SPEC, UAT_CHECKLIST, Architecture, WeeklyStatus

[0.1.2]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.2

## [0.1.1] - 2026-06-16

### Changed

- Remove deprecated `theman_*` port / config aliases; use `trading_app_*` symbols only
- Alert prefix `[theman]` → `[trading-app]`
- Windows ops: `start-trading-app.ps1`, `register-task.ps1` default task `trading-app-vwap`
- Pin siblings: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`
- Docs sync: `TODO.md`, `WeeklyStatus.md`, `README.md`, `docs/*` ops paths

### Fixed

- Sweep tick helpers: `ReplayTick.close` as `str` (realistic CSV replay) — pairs with backtest `MockBroker` float coercion fix

[0.1.1]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.1

## [0.1.0] - 2026-06-16

First public release as **reference integrator app** (renamed from internal `theman`).

### Added

- `pyproject.toml`, `SPEC.md`, `LICENSE`, `.env.example`, `docs/RELEASE_CHECKLIST.md`
- `trading_app_engine_ports()` wiring for live, backtest, and tests
- `TradingAppTelemetryPort`, `TradingAppAlertPort`, `TradingAppArchivePort`, `TradingAppTrendRefresh`
- `reporting/` UAT log parser (`python -m reporting`)
- `storage/` tick/kbar archive + `sweep/` param research tooling
- CI: standalone clone via git-tagged sibling packages

### Changed

- Renamed from `theman` → `trading-app` (repo / docs / symbols)
- Dependencies: `trading-engine`, `trading-backtest`, `strategy-vwap-momentum` (no vendored kernel)
- Removed transitional re-export shims (`runtime/`, `strategy/`, `adapters/`, most of `core/`)
- App tests scoped to integration / storage / reporting / sweep (~30 tests)

### Notes

- **UAT-ready**, not Live-ready — see `docs/UAT_CHECKLIST.md`
- Pin siblings: `trading-engine@v0.2.0`, `trading-backtest@v0.1.0`, `strategy-vwap-momentum@v0.1.0`

[0.1.0]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.0