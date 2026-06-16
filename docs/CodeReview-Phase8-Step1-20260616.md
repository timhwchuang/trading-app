# Code Review: Phase 8 Step 1 — Broker/Engine Decoupling (BrokerPort + trading-engine extraction)
**Date**: 2026-06-16
**Reviewer persona**: Meticulous code reviewer (maintainability, structural simplification, safety, per code-review/SKILL.md + shared/personas/reviewer.md)
**Scope**: Local uncommitted changes (working tree) in theman/ for "Phase 8 Step 1". Includes re-exports in src/runtime/*, src/adapters/*, src/core/* (except runtime_config bridge), new src/integrations/*, wiring in live/backtest/tests, run_tests.py sys.path hack, docs updates, and the sibling trading-engine/ package (source of truth). Diff at /tmp/theman-phase8-diff.txt sampled.
**Process**: Git scope via dir inspection + diff chunks; exhaustive multi-pass reads of all listed files + cross-greps (shioaji isolation, theman leakage, import patterns, call sites); static analysis of correctness before style; no source edits.

## Summary
This change is a large net-negative-LOC extraction (~-2k) that correctly names the implicit broker seam as `BrokerPort` (Protocol, documentation+typing only) in `core/ports.py`, moves the giant engine+mixins+core+adapters+calendar+indicators+... into a standalone `trading-engine` sibling package, reduces many former monolith files in theman to 2-5 line re-exports, and introduces a clean `src/integrations/` layer (`Theman*Port` impls + `theman_engine_ports` wiring) so theman becomes the thin domain-specific integrator (strategy/storage/reporting/sweep + theman ports + config + live entrypoint).

**Correctness**: High. Shioaji usage is properly isolated (only `src/live/__main__.py` has top-level `import shioaji` + direct construction; runtime/core/backtest/strategy/tests have zero top-level shioaji; trading-engine uses only lazy `import shioaji` inside live-only paths + inside `adapters/shioaji.py:place_ioc_limit`; all 155 tests remain conceptually green per docs + wiring updates). Backtest determinism preserved (MockBroker + VirtualClock + no-tick sync mode + injected ports). Live entrypoints remain the sole real-Shioaji constructors. BrokerPort + adapters already achieve the stated goal of broker decoupling for the engine.

**Dominant wins**: Successful extraction with thin integrator pattern; integrations/ correctly lives in theman (domain-specific side effects, calendar usage in trend port, config bridge); order adapter seam extracted earlier than the "next step" notes claimed (construction of `FuturesOrder` now only in trading-engine/adapters/shioaji.py); zero behavior change.

**Dominant risk areas / structural regressions** (why this does *not* yet pass the ambitious approval bar of code-review/SKILL.md):
- Missed "code judo" simplification around the re-export + strategy surface (duplication instead of re-export for the canonical Protocol).
- theman-specific heuristic (`hasattr(api, "inflight")`) leaked into trading-engine's engine.py adapter selection (violates "trading-engine free of theman concerns").
- Path hack + import mixing (core vs trading_engine direct) creates fragile boundaries instead of inevitable clean layering.
- Docs drift on the remaining work and some post-extraction realities.
- Small but real duplication + surface inconsistency that will make future changes (Phase 8 Step 2, more brokers, more apps) harder rather than inevitable.

The change *works* and is directionally correct, but the bar requires no structural regression and no missed dramatic simplifications. Several clear paths exist to delete complexity rather than rearrange it. Must-fix items below before merge; others are strong recommendations for the next Step.

## Issues

### Issue 1 — Severity: bug (structural leakage + future fragility)
- **File**: /Users/tim_chuang/workaround/future/trading-engine/src/trading_engine/engine.py:52
- **Description**: `_default_order_adapter` contains the theman-specific heuristic `if hasattr(api, "inflight"):` to decide `MockOrderAdapter` vs `ShioajiOrderAdapter`. `inflight` is an implementation detail of `theman/src/backtest/mock_broker.py:50` (and its test double). This logic lives in the "standalone reusable" trading-engine package and is executed for *every* `TradingEngine()` construction (live, backtest, tests via make_host). trading-engine must remain free of theman-specific concerns per task spec and extraction contract.
- **Suggestion**: Push adapter selection *out* to the wiring layer (theman-only). Change `TradingEngine.__init__` to require an explicit `order_adapter` (or always default to a no-op/Null that errors, forcing callers). Update `theman_engine_ports` (and backtest/live call sites + test_helpers) to construct and pass the correct adapter based on the api they are injecting. Remove the `hasattr` test and the "inflight" knowledge entirely from trading-engine. (This is the "code judo" move that makes the boundary inevitable and removes an ad-hoc conditional.)
- **Status**: open

### Issue 2 — Severity: bug (duplication of canonical interface; violates DRY + extraction intent)
- **File**: /Users/tim_chuang/workaround/future/theman/src/strategy/base.py:1 (entire ~194-line file, identical to trading-engine counterpart)
- **Description**: `theman/src/strategy/base.py` (Strategy Protocol + BaseStrategy + all docstrings) is a verbatim duplicate of `/Users/tim_chuang/workaround/future/trading-engine/src/trading_engine/core/strategy.py:1`. The Protocol is part of the engine's dependency surface (engine imports it; trading-engine/__init__.py reexports it). theman strategy/ is intended for *domain-specific concrete* (vwap_momentum, trend, params), yet the interface source-of-truth is duplicated instead of re-exported like every other extracted core module (core/ports.py, core/types.py, core/side_effect_ports.py, runtime/engine.py, adapters/*, indicators.py, exchange_time.py, etc.). This is exactly the "random spaghetti growth" and "file from <1k to >1k without strong reason" pattern the skill guidelines forbid. Divergence risk is immediate on any future Protocol change.
- **Suggestion**: Convert `theman/src/strategy/base.py` to a 3-5 line re-export exactly like `src/core/ports.py` or `src/runtime/engine.py`:
  ```python
  """Re-export Strategy / BaseStrategy from trading-engine (source of truth)."""
  from trading_engine.core.strategy import *  # noqa: F403
  __all__ = ["Strategy", "BaseStrategy", "StrategySideEffects"]
  ```
  Keep only the concrete implementations + theman-specific wiring (params.py, vwap_momentum.py, trend.py, __init__.py) under `theman/src/strategy/`. Update any internal theman imports if needed (they already mix trading_engine.core in places). Update AGENTS.md, docs, Architecture.md, BackTestingSpec.md to point at the trading-engine location for the canonical contract or note the re-export. This deletes ~180 lines of duplication and makes the split feel inevitable.
- **Status**: open

### Issue 3 — Severity: bug (import layering violation + brittle sys.path contract)
- **File**: /Users/tim_chuang/workaround/future/theman/run_tests.py:15
- **Description**: The sys.path hack (`_TE_SRC` insert before `_SRC`, then root) is the only thing making "from core.xxx", "from runtime.xxx", "from strategy.base", "from trading_engine.*" and bare-package tests work after extraction. It is documented as a "maintenance note" but is exactly the kind of ad-hoc sequential state the guidelines demand be replaced by a dedicated abstraction or proper packaging. Multiple theman files now mix styles in the same module: `from core.runtime_config import ...` (theman re-export/bridge) + `from trading_engine.core.runtime_config import SWEEP...` (direct). See also `/Users/tim_chuang/workaround/future/theman/src/strategy/params.py:9`, `/Users/tim_chuang/workaround/future/theman/src/integrations/trend_refresh.py:10`, `/Users/tim_chuang/workaround/future/theman/src/strategy/vwap_momentum.py:9` (core vs trading_engine), and engine_wiring + test_helpers.
- **Suggestion**:
  1. Make the trading-engine package properly installable (pyproject.toml already exists; add editable dev install or requirements in theman).
  2. Or introduce a single `theman/_vendor.py` or `theman/ports.py` compatibility shim that does the resolution once and re-exports everything theman code needs under stable local names.
  3. Standardize all theman code on either (a) local re-exports under `core/`, `runtime/`, `strategy/base.py` etc. (preferred for thin integrator) or (b) explicit `from trading_engine.*` with clear comments. Eliminate direct cross-package imports mixed with "core" aliases.
  4. Update run_tests.py comment to describe the *intended* long-term mechanism, not just the hack.
- **Status**: open

### Issue 4 — Severity: suggestion (high; docs/code drift on extraction reality + remaining shioaji surface)
- **File**: /Users/tim_chuang/workaround/future/theman/docs/WeeklyStatus.md:95 (and mirrored in AGENTS.md:165, TODO.md:33, Architecture.md:30, BackTestingSpec.md:52)
- **Description**: Multiple docs still claim "`runtime/order_executor.py` still directly constructs `shioaji.FuturesOrder` + compares `OrderState`/`Action`" and list it as the "next抽離目標". Post-extraction, order construction lives exclusively in `trading-engine/adapters/shioaji.py:24` (lazy import + `sj.FuturesOrder` only inside `place_ioc_limit`); the re-exported `order_executor.py` (and its mixin) only calls `self._order_adapter.place_ioc_limit(...)`. The *only* remaining direct shioaji enum usage in the engine layer is the `sj.Action.Buy` compare inside `trading-engine/src/trading_engine/session.py:164` (in `sync_positions`). The adapter extraction was effectively done in this step.
- **Suggestion**: Update all four docs in one pass to accurately describe the current state: "order construction is now isolated to `trading_engine.adapters` (shioaji only inside the adapter); remaining enum compare in session.py for positions is the narrow next target (or can be normalized to strings at the handle_order_event boundary)." Explicitly call out the adapter seam in Architecture.md as already achieved. This keeps "文件即真相".
- **Status**: open

### Issue 5 — Severity: suggestion (medium-high; config bridge duplication + property override risk)
- **File**: /Users/tim_chuang/workaround/future/theman/src/core/runtime_config.py:27 (ThemanRuntimeConfig) and trading-engine counterpart
- **Description**: `ThemanRuntimeConfig` subclasses `EngineRuntimeConfig` and overrides `dump_order_events`, `tick_archive`, `kbars_archive` (delegating to theman `config` module / yaml+env). But `trading_engine/core/runtime_config.py:124` already implements those three properties (via direct os.environ). The bridge also copies all fields from ThemanSettings into EngineSettings via `dataclasses.fields`. Any new field added to trading-engine Settings requires coordinated change in the copy logic + ThemanSettings. `default_runtime_config` in theman returns the subclass while trading-engine's RuntimeConfig is the base.
- **Suggestion**: Either (preferred) make RuntimeConfig in trading-engine accept an optional provider for the archive/dump flags (or take them as explicit ctor args), or move the env fallbacks entirely into the theman bridge and have trading-engine's base not implement them at all. At minimum, add a unit test that constructs both and asserts the three flags come from the right source under both env and yaml settings. Consider whether `ThemanRuntimeConfig` should be the only public type exposed from theman's core/runtime_config re-export surface.
- **Status**: open

### Issue 6 — Severity: suggestion (boundary cleanliness)
- **File**: /Users/tim_chuang/workaround/future/theman/src/integrations/trend_refresh.py:10 and trading-engine/calendar
- **Description**: `ThemanTrendRefresh` (theman-specific) directly imports and instantiates `TaifexMarketCalendar` from `trading_engine.calendar.port` inside its `__init__`, then calls `self._calendar.select_recent_trading_days_closes`. The calendar port + impl were extracted to trading-engine (correct), but this creates a direct dependency from a theman integrations module into trading-engine's calendar subpackage rather than receiving the calendar via the existing `calendar=` kwarg already supported on `TradingEngine` (and thus available via wiring).
- **Suggestion**: Inject the calendar (or a minimal "recent closes" helper) through `theman_engine_ports` / the engine ctor when wiring trend_refresh, or expose a narrower theman-specific helper. This keeps theman integrations as pure adapters and prevents trading-engine internals from leaking upward.
- **Status**: open

### Issue 7 — Severity: nit (but symptomatic of re-export surface)
- **File**: /Users/tim_chuang/workaround/future/theman/src/core/ports.py:1 (and similarly adapters/__init__.py:1, runtime/__init__.py, core/audit/__init__.py, core/side_effect_ports.py, etc.)
- **Description**: Re-export files are inconsistent: some use `from trading_engine... import *  # noqa: F403`, some do explicit `__all__` + selective import (exchange_time.py does the latter; runtime/__init__.py only reexports TradingEngine while the real package has more). `core/__init__.py` is almost empty ("Shared core types..."). Adapters __init__ has only a one-line docstring. No central place documents "which names are re-exported for backward compat in theman code".
- **Suggestion**: Adopt a single re-export template (e.g., always explicit `__all__` listing the public surface + comment "Phase 8 re-export — edit trading-engine, not here"). Add a short table in Architecture.md or docs/README.md listing the re-exported packages and their theman-side aliases. Consider `src/core/__init__.py` exposing the key ports + types under one `from core import BrokerPort, OrderSignal...` for convenience without forcing bare "core" imports everywhere.
- **Status**: open

### Issue 8 — Severity: nit (maintainability)
- **File**: /Users/tim_chuang/workaround/future/trading-engine/src/trading_engine/logging_setup.py:70
- **Description**: The root logger name is hardcoded to `"theman"`. The package is now reusable; other future integrators will see "theman" in their logs.
- **Suggestion**: Parameterize or default to a generic name (`"trading_engine"`) with theman overriding at its wiring layer if desired. Minor, but part of making the extraction feel complete.
- **Status**: open

### Issue 9 — Severity: nit (edge case in test wiring)
- **File**: /Users/tim_chuang/workaround/future/theman/tests/backtest/test_mock_broker.py:234 (and similar in test_backtester.py)
- **Description**: Several backtest tests do `host = make_host(); host.api = broker; ...; host.refresh_atr()` (or mutate). Because adapter selection + wrapping happens at `TradingEngine()` construction time, rebinding `host.api` after the fact means any future call to `place_order` (or code paths using the adapter) would talk to the stale MagicMock adapter rather than the rebound broker. Current tests happen to only exercise `api.kbars` (direct on host.api) or pre-place matching, so they pass. This is a latent test fragility introduced by the new ports + lazy defaults.
- **Suggestion**: Either (a) make the adapter re-selectable or overridable after construction, or (b) update make_host and all post-construction api= sites to also accept/construct+inject an explicit order_adapter (or pass it through in the ports dict). Add a regression test that exercises place_order after api rebound in a mock host.
- **Status**: open

### Issue 10 — Severity: suggestion (ambitious further simplification)
- **File**: /Users/tim_chuang/workaround/future/theman/src/integrations/engine_wiring.py:12 (and call sites in live/__main__.py:15, backtest/engine.py:55, test_helpers.py:19)
- **Description**: `theman_engine_ports` is a good thin factory, but the backtest path still has ad-hoc strategy defaulting + cfg extraction after the call (lines 57-60 in backtest/engine.py), duplicating similar logic in live and test_helpers. The ports dict is passed with `**ports` which is convenient but opaque (no type checking on the side-effect ports at call sites).
- **Suggestion**: Make `theman_engine_ports` take an optional strategy factory or always return a fully-wired set of kwargs that backtest/live can consume with less post-processing. Consider a small `EngineConfig` dataclass or TypedDict for the returned ports so call sites and TradingEngine ctor have better IDE/docs support. This reduces the "new ad-hoc conditionals" in the thin integrator layer.
- **Status**: open

## Additional Observations (no individual issue filed)
- BrokerPort docstring is honest about looseness ("Any on purpose... name the seam"). With the parallel OrderAdapter Protocol (tighter, action=str, no shioaji enums), the looseness is acceptable for Step 1. Future brokers should implement both.
- Remaining lazy shioaji in trading-engine (engine.py:88/564/684/701, session.py:162) are all inside live-only methods (`start`, reconnect, no-tick watchdog, sync_positions for Action compare) or TYPE_CHECKING. This matches the safety contract.
- MockBroker (theman) still normalizes action str vs enum-like in two places; order_executor has `_is_buy_action` doing similar. This is the shared contract surface mentioned in Architecture.md; cleanup can be part of the next order-adapter or event work.
- No "theman" hard imports/strings in trading-engine source (only README, one docstring, and legacy logger name). Extraction hygiene good.
- `core/order_events.py` re-export + FUTURES_* constants used by both MockBroker and handle_order_event is the right narrow shared vocabulary.
- No evidence of broken backtest determinism or live safety bleed.

## Recommendations for Next Phase 8 Steps
- **Immediate (pre-merge)**: Fix Issues 1-4 (especially leakage + dupe + docs). Re-run full `python run_tests.py` after any wiring changes.
- **Step 2**: Extract the remaining Action/OrderState compares (session.py + any order path) into the adapters or a tiny `core/order_types.py` that both mock and shioaji paths can use as strings/constants. Consider whether BrokerPort can be narrowed or largely replaced by the combination of OrderAdapter + injected Calendar + side-effect ports.
- **Packaging**: Make trading-engine a real dependency (editable install or monorepo tooling) and retire the sys.path hack.
- **Ambitious refactor**: Once the adapter is the only order seam, consider whether BrokerPort itself can become a pure marker or be removed in favor of Protocol composition in the side-effect ports + calendar.
- Keep the "thin integrator" discipline: new theman-specific behavior (new alerts, new storage, new trend logic) belongs in `integrations/` or domain packages, never inside trading-engine.

**Verdict on approval bar**: Does not yet pass. The extraction is a clear win on LOC and isolation, but the structural regressions (leaked heuristic, duplicated Protocol, path-hack-as-architecture, docs drift) are exactly what the skill guidelines say must be caught and fixed. With the targeted simplifications above (especially pushing adapter choice to wiring and eliminating the strategy base dupe), this becomes a model extraction. Do the must-fix items, then merge.

---
*Review written from exhaustive reads of the post-change files + diff samples. All line citations are from the current (post-Phase-8-Step-1) source. No source was modified.*