# Release checklist — trading-app

Use this before tagging a release on GitHub.  
Four-repo coordination: [`UPGRADE_RUNBOOK.md`](UPGRADE_RUNBOOK.md).

## v0.1.2 — completed 2026-06-17

- [x] Sibling tags: `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- [x] `python run_tests.py` — 81 OK (app); engine 80 + strategy 33 OK
- [x] P4-13 config + `UPGRADE_RUNBOOK.md`
- [x] `requirements.txt` pins `@v0.2.2` / `@v0.1.2`
- [x] `git push origin main && git push origin v0.1.2`

---

## v0.1.1 — completed 2026-06-16

- [x] Sibling tags: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`
- [x] `python run_tests.py` — 79 OK (app); siblings 27 + 31 OK
- [x] Remove `theman_*` aliases; ops docs → `trading-app`
- [x] `requirements.txt` pins `@v0.1.1`
- [x] `git push origin main && git push origin v0.1.1`

---

## v0.1.0 — reference (completed 2026-06-16)

Use this before tagging `v0.1.0` on GitHub.

## Pre-tag verification

- [ ] `python run_tests.py` — all tests pass (~30 integration tests)
- [ ] `ruff check src tests` — no lint errors (if ruff installed)
- [ ] `README.md` / `SPEC.md` / `docs/releases/v0.1.0.md` — no broken links
- [ ] `pyproject.toml` version = `0.1.0`
- [ ] `CHANGELOG.md` date and `[0.1.0]` link ready
- [ ] `config/config.yaml` → `simulation: true`
- [ ] No committed `.env`, `*.pfx`, API keys
- [ ] No `from theman` / no re-export shim imports in `src/`

## Code review gate (required before tag)

- [ ] Run `/review` on full PR-1 + PR-2 diff
- [ ] Code review via `/review` or GitHub PR review (conclusions → `WeeklyStatus.md`)
- [ ] **0 high-severity issues** (medium/low documented or fixed)
- [ ] Re-run `python run_tests.py` after review fixes

## Dependency pins (document in release)

```bash
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.0"
pip install "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0"
pip install "strategy-vwap-momentum @ git+https://github.com/timhwchuang/strategy-vwap-momentum.git@v0.1.0"
pip install -r requirements.txt
```

## Tag and publish

```bash
git add -A
git commit -m "Release v0.1.0: reference integrator app, UAT-ready"
git tag -a v0.1.0 -m "v0.1.0 — reference integrator app, UAT-ready"
git remote add origin https://github.com/timhwchuang/trading-app.git  # if needed
git push origin main
git push origin v0.1.0
```

## Post-tag

- [ ] GitHub Release notes — copy from `docs/releases/v0.1.0.md`
- [ ] CI green on `main`
- [ ] Update workspace `docs/three-repo/README.md` → trading-app ✅
- [ ] Begin UAT per `docs/UAT_CHECKLIST.md`

## Scope reminder

v0.1.0 is suitable for:

- Windows simulation UAT with tick archive + `uat_report`
- Reference wiring for custom integrator apps

v0.1.0 is **not** suitable as sole evidence for live / Pilot Go — Phase 6 calibration still required.