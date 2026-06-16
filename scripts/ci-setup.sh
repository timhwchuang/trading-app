#!/usr/bin/env bash
# Install trading-app dependencies for CI (standalone clone) or monorepo dev fallback.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(cd "$ROOT/.." && pwd)"

pip install -r "$ROOT/requirements.txt" -q

if ! python - <<'PY'
import importlib
for m in ("trading_engine", "trading_backtest", "strategy_vwap_momentum"):
    importlib.import_module(m)
PY
then
  for pkg in trading-engine strategy-vwap-momentum trading-backtest; do
    if [[ -f "$WORKSPACE/$pkg/pyproject.toml" ]]; then
      pip install -e "$WORKSPACE/$pkg" -q
    fi
  done
fi