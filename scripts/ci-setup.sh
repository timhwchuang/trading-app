#!/usr/bin/env bash
# Install sibling packages when theman lives in a monorepo workspace (future/theman + siblings).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(cd "$ROOT/.." && pwd)"

for pkg in trading-engine strategy-vwap-momentum trading-backtest; do
  if [[ -f "$WORKSPACE/$pkg/pyproject.toml" ]]; then
    pip install -e "$WORKSPACE/$pkg" -q
  fi
done

pip install -r "$ROOT/requirements.txt" -q
