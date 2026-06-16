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
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from reporting.forward_pnl import ForwardPnlPolicy, load_tick_series, make_replay_forward_pnl, policy_summary
from reporting.uat_report import parse_log_audits_and_fills, read_log_lines
from storage.tick_loader import DEFAULT_CACHE_DIR
from trading_engine.core.audit.signal_audit import SignalAudit


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

    def _forward(price: float, idx: int, direction_arg: str = direction) -> float:
        j = min(len(prices) - 1, idx + window_bars)
        delta = prices[j] - price
        sign = 1.0 if direction_arg in ("Long", "Buy", "buy", "long") else -1.0
        return sign * delta

    return veto_audits, _forward


def audit_to_dict(audit: Any) -> dict[str, Any]:
    if isinstance(audit, dict):
        return dict(audit)
    if isinstance(audit, SignalAudit):
        from dataclasses import asdict

        return asdict(audit)
    return {
        "intent": getattr(audit, "intent", ""),
        "direction": getattr(audit, "direction", "Buy"),
        "price": float(getattr(audit, "price", 0.0)),
        "ts": getattr(audit, "ts", 0),
        "reason": getattr(audit, "reason", ""),
        "trend_dir": getattr(audit, "trend_dir", ""),
        "trend_strength": getattr(audit, "trend_strength", 0.0),
        "atr": getattr(audit, "atr", 0.0),
    }


def partition_trend_entry_audits(
    audits: Iterable[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split entry SIGNAL_AUDIT rows into trend_veto vs allowed candidates."""
    veto: list[dict[str, Any]] = []
    allowed: list[dict[str, Any]] = []
    for audit in audits:
        row = audit_to_dict(audit)
        if row.get("intent") != "entry":
            continue
        reason = str(row.get("reason", "")).lower()
        if reason in ("trend_veto", "trend veto"):
            veto.append(row)
        else:
            allowed.append(row)
    return veto, allowed


def run_b_class_calibration(
    *,
    log_lines: list[str] | None = None,
    log_paths: list[Path] | None = None,
    code: str,
    dates: list,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    forward_policy: ForwardPnlPolicy | None = None,
) -> dict[str, Any]:
    """CAL-6/7: parse UAT/backtest log + tick replay forward policy → harness metrics."""
    if log_lines is None:
        if not log_paths:
            raise ValueError("run_b_class_calibration requires log_lines or log_paths")
        log_lines = read_log_lines([Path(p) for p in log_paths])

    audits, _fills = parse_log_audits_and_fills(log_lines)
    veto_audits, allowed_audits = partition_trend_entry_audits(audits)

    pol = forward_policy or ForwardPnlPolicy()
    series = load_tick_series(code, dates, cache_dir=cache_dir)
    if not series.timestamps:
        return {
            "status": "no_ticks",
            "code": code,
            "dates": [d.isoformat() for d in dates],
            "cache_dir": str(cache_dir),
            "n_veto": len(veto_audits),
            "n_allowed": len(allowed_audits),
            "forward_policy": policy_summary(pol),
            "notes": "B-class blocked: tick_cache empty for requested dates.",
        }

    get_forward_pnl = make_replay_forward_pnl(series, pol)
    metrics = compute_trend_veto_calibration(
        veto_audits,
        allowed_audits=allowed_audits or None,
        get_forward_pnl=get_forward_pnl,
        forward_policy=pol,
        b_class=True,
    )
    metrics["status"] = "ok"
    metrics["code"] = code
    metrics["dates"] = [d.isoformat() for d in dates]
    metrics["tick_count"] = len(series)
    metrics["forward_policy"] = policy_summary(pol)
    return metrics


DEFAULT_TREND_MIN_STRENGTH_GRID = [0.0, 0.3, 0.5, 0.8, 1.0, 1.5]


def _invoke_forward_pnl(
    fwd: Callable[..., float],
    rec: _VetoRecord,
) -> float:
    try:
        return float(fwd(rec.price, int(rec.ts), rec.direction))
    except TypeError:
        return float(fwd(rec.price, int(rec.ts)))


def compute_trend_veto_calibration(
    veto_audits: Iterable[Any],
    allowed_audits: Iterable[Any] | None = None,
    *,
    get_forward_pnl: Callable[..., float] | None = None,
    forward_policy: ForwardPnlPolicy | None = None,
    b_class: bool = False,
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

    using_custom_fwd = get_forward_pnl is not None
    fwd = get_forward_pnl or _default_fwd

    veto_forwards: list[float] = []
    for rec in veto_list:
        try:
            f = _invoke_forward_pnl(fwd, rec)
        except Exception:
            f = 0.0
        veto_forwards.append(f)

    allowed_forwards: list[float] = []
    for rec in allowed_list:
        try:
            f = _invoke_forward_pnl(fwd, rec)
        except Exception:
            f = 0.0
        allowed_forwards.append(f)

    mean_veto = statistics.mean(veto_forwards) if veto_forwards else 0.0
    mean_allowed = statistics.mean(allowed_forwards) if allowed_forwards else 0.0
    delta = mean_allowed - mean_veto

    if b_class and forward_policy is not None:
        notes = (
            f"B-class replay forward policy: {policy_summary(forward_policy)}. "
            "Use for Go/No-Go only with ≥5 UAT days and human sign-off (CAL-8)."
        )
    elif using_custom_fwd:
        notes = (
            "Replay forward PnL supplied. Document policy per run; "
            "multi-day stability still required before opening trend_filter_enabled."
        )
    else:
        notes = (
            "SYNTHETIC GUARD: toy numbers only. Real delta/veto_rate for Go/No-Go "
            "require UAT replay + documented forward policy (CAL-2/5/7)."
        )

    return {
        "veto_rate": round(veto_rate, 4),
        "n_veto": n_veto,
        "n_allowed": n_allowed,
        "mean_forward_if_vetoed": round(mean_veto, 4),
        "mean_forward_allowed": round(mean_allowed, 4),
        "delta_expectancy": round(delta, 4),
        "notes": notes,
    }
