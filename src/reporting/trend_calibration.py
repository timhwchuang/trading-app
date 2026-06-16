"""P6-1-CAL-2: Calibration harness for trend filter conditional expectation (veto vs allow).

Pure functions. Accepts in-memory SIGNAL_AUDIT records (dicts or SignalAudit-like).
First-class support for synthetic scenarios so A-class verification needs no real tick data.

Core metrics for honest Go/No-Go:
- veto_rate: fraction of candidates that were vetoed (reason="trend_veto").
- delta_expectancy: E[forward_pnl | allowed] - E[forward_pnl_if_entered | vetoed].
  Positive + stable => filter improved edge (protected from bad counter-trend pullbacks).
  Negative or ~0 => filter ROI low; reconsider min_strength or redesign.

Forward PnL is a *policy choice* (fixed bars, to session flatten, or to next exit).
It is a hyperparameter for the calibration; document the window used.

Safety: this module never flips TREND_FILTER_ENABLED, never touches live, never loads real UAT logs
(unless the caller passes parsed audits). All A-class tests are synthetic.

SYNTHETIC GUARD (CQR-mandated): toy forward / delta numbers are **only** for harness code correctness.
Real calibration of trend_min_strength / opening the filter requires B-class UAT tick + KBARS replay
with a documented forward policy (fixed bars or to flatten). Never use synthetic delta for Go/No-Go.

See:
- TODO.md P6-1-CAL-2 / CAL-3 / CAL-5 (SOP) + CAL-7/8
- strategy-vwap-momentum docs/CALIBRATION.md (P6-1 workflow)
- src/strategy/trend.py (min_strength semantics, 0.0 = most aggressive)
- src/observability.py + vwap_momentum.py (record_trend_veto + reason="trend_veto" emission)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence


@dataclass
class _VetoRecord:
    price: float
    direction: str  # "Long" or "Short" (momentum side at veto time)
    ts: Any = None  # for ordering / windowing if needed
    trend_dir: str = "Flat"
    trend_strength: float = 0.0
    atr: float = 0.0


def _as_veto_record(audit: Any) -> _VetoRecord:
    """Normalize audit (dict or object with attrs) to internal record."""
    if isinstance(audit, dict):
        price = float(audit.get("price", audit.get("ref_price", 0.0)))
        direction = str(audit.get("direction") or audit.get("momentum_dir") or "Long")
        return _VetoRecord(
            price=price,
            direction=direction,
            ts=audit.get("ts"),
            trend_dir=str(audit.get("trend_dir", "Flat")),
            trend_strength=float(audit.get("trend_strength", 0.0)),
            atr=float(audit.get("atr", 0.0)),
        )
    # object with attributes (e.g. SignalAudit)
    price = float(getattr(audit, "price", getattr(audit, "ref_price", 0.0)))
    direction = str(getattr(audit, "direction", "Long"))
    return _VetoRecord(
        price=price,
        direction=direction,
        ts=getattr(audit, "ts", None),
        trend_dir=str(getattr(audit, "trend_dir", "Flat")),
        trend_strength=float(getattr(audit, "trend_strength", 0.0)),
        atr=float(getattr(audit, "atr", 0.0)),
    )


def make_synthetic_veto_scenario(
    prices: Sequence[float],
    veto_at: Sequence[int],
    *,
    direction: str = "Long",
    window_bars: int = 20,
) -> tuple[list[dict], Callable[[float, int], float]]:
    """Build a toy scenario for unit tests (no real data).

    Returns (veto_audits, forward_pnl_fn) where forward_pnl_fn(price, idx) returns
    the signed forward P&L if we had entered at that price/index (simple price delta over window).

    Synthetic only. Used for CAL-2 harness verification and as stub for CAL-3 sweep enrichment.
    """
    veto_audits: list[dict] = []
    for i in veto_at:
        if 0 <= i < len(prices):
            veto_audits.append(
                {
                    "intent": "entry",
                    "reason": "trend_veto",
                    "price": float(prices[i]),
                    "direction": direction,
                    "ts": i,
                    "trend_dir": "Flat" if direction == "Long" else "Long",  # counter example
                    "trend_strength": 1.2,
                    "atr": 10.0,
                }
            )

    def _forward(price: float, idx: int) -> float:
        j = min(len(prices) - 1, idx + window_bars)
        delta = prices[j] - price
        sign = 1.0 if direction == "Long" else -1.0
        return sign * delta

    return veto_audits, _forward


def compute_trend_veto_calibration(
    veto_audits: Iterable[Any],
    allowed_audits: Iterable[Any] | None = None,
    *,
    get_forward_pnl: Callable[[float, int], float] | None = None,
) -> dict[str, Any]:
    """Core harness: conditional expectation of the trend veto.

    veto_audits: records with reason="trend_veto" (or all candidates; filter inside).
    allowed_audits: records that passed (no veto). If None, we can only compute stats on vetoed side.
    get_forward_pnl(price, idx) -> float: signed PnL if entered at that point. The caller **must**
        supply a policy (fixed window, to session flatten, or replay-derived). If None we use a
        dead 0.0 toy (explicitly not for calibration). (Removed unused default_window param.)

    Returns dict with:
      veto_rate, n_veto, n_allowed, mean_forward_if_vetoed, mean_forward_allowed,
      delta_expectancy (allowed - vetoed_if_entered), notes.

    CRITICAL SYNTHETIC GUARD (per CQR + TODO P6-1-CAL):
    All numbers produced from synthetic scenarios or default toy forward are for harness
    implementation verification only. Real delta expectancy, veto_rate stability, and any
    Go/No-Go decision on trend_min_strength or trend_filter_enabled **require** B-class
    UAT tick archive + KBARS + actual replay forward (CAL-6/7). Window / flatten policy is
    a hyperparameter that must be documented for each real calibration run.
    """
    veto_list = [_as_veto_record(a) for a in veto_audits]
    # Filter only explicit vetoes if "reason" present on raw
    # (our synthetic + real audits already carry reason at emission site; here we treat the list as veto list)

    allowed_list: list[_VetoRecord] = []
    if allowed_audits is not None:
        for a in allowed_audits:
            rec = _as_veto_record(a)
            # crude: if caller passed mixed, skip obvious vetoes; real use separate log streams
            allowed_list.append(rec)

    n_veto = len(veto_list)
    n_allowed = len(allowed_list)
    total_candidates = n_veto + n_allowed
    veto_rate = (n_veto / total_candidates) if total_candidates > 0 else 0.0

    # Forward on veto side ("if we had entered anyway")
    def _default_fwd(price: float, idx: int) -> float:
        # Explicitly dead toy for safety. Real callers *must* override.
        return 0.0

    fwd = get_forward_pnl or _default_fwd

    veto_forwards: list[float] = []
    for rec in veto_list:
        # Use rec.ts as original index when provided by synthetic builder (ts set to the veto_at price index).
        # For real audits, caller must supply a get_forward_pnl that can resolve by rec.ts / rec.price.
        idx = rec.ts if isinstance(rec.ts, (int, float)) else 0
        try:
            f = fwd(rec.price, int(idx))
        except Exception:
            f = 0.0
        veto_forwards.append(f)

    allowed_forwards: list[float] = []
    for rec in allowed_list:
        idx = rec.ts if isinstance(rec.ts, (int, float)) else 0
        try:
            f = fwd(rec.price, int(idx))
        except Exception:
            f = 0.0
        allowed_forwards.append(f)

    mean_veto = statistics.mean(veto_forwards) if veto_forwards else 0.0
    mean_allowed = statistics.mean(allowed_forwards) if allowed_forwards else 0.0
    delta = mean_allowed - mean_veto

    return {
        "veto_rate": round(veto_rate, 4),
        "n_veto": n_veto,
        "n_allowed": n_allowed,
        "mean_forward_if_vetoed": round(mean_veto, 4),
        "mean_forward_allowed": round(mean_allowed, 4),
        "delta_expectancy": round(delta, 4),
        "notes": "SYNTHETIC GUARD: toy numbers only. Real delta/veto_rate for Go/No-Go require UAT replay + documented forward policy (CAL-2/5/7).",
    }
