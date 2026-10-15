"""Critic Agent: independent re-screen with a DIFFERENT method (full context rules).

Never reuses the executor's class blindly: re-derives critic_screen_class from
enriched inputs via risk.full_screen_class, compares vs executor + legacy label,
and emits AGREE / DOWNGRADE_RISK / UPGRADE_REQUIRED. Can reject executor results.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.tools import risk

SEV = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}


def review(
    enriched: List[Dict[str, Any]],
    risk_results: List[Dict[str, Any]],
    llm,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (verdicts, objections_for_rework)."""
    by_risk = {r["anomaly_id"]: r for r in risk_results}
    verdicts: List[Dict[str, Any]] = []
    objections: List[Dict[str, Any]] = []
    for r in enriched:
        aid = str(r.get("anomaly_id"))
        ex = by_risk.get(aid, {})
        ex_class = ex.get("triage_class", "MONITOR")
        growth = r.get("growth_rate_pct_per_yr")
        depth = ex.get("depth_pct_used", r.get("depth_pct"))
        try:
            depth_f = float(depth) if depth is not None else None
        except (TypeError, ValueError):
            depth_f = None
        proj = risk.project_depth(depth_f, growth, 2.0)
        screen, reasons = risk.full_screen_class(
            depth_f, ex.get("erf"), growth, proj, bool(r.get("hca_confirmed", r.get("hca"))),
            bool(r.get("near_road")), bool(r.get("near_water")), bool(r.get("near_weld")),
            bool(r.get("interacting")), bool(r.get("note_severe")),
        )
        # Dirty-record rule: invalid depth + severe note or HCA context -> upgrade to IMMEDIATE review.
        if (depth_f is None or (depth_f is not None and (depth_f < 0 or depth_f > 100))) and (
            r.get("note_severe") or r.get("hca") or (r.get("quality_flags"))
        ):
            screen, reasons = "IMMEDIATE", ["invalid_numeric_depth_with_risk_context:quarantine_upgrade"] + reasons
        legacy = r.get("legacy_manual_label")
        s_ex, s_sc = SEV[ex_class], SEV[screen]
        missed = bool(legacy is not None and legacy in SEV and SEV[legacy] < SEV[screen] and SEV[screen] >= SEV["60_DAY"])
        if s_sc > s_ex:
            verdict = "UPGRADE_REQUIRED"
            final = screen
            objections.append({"anomaly_id": aid, "executor_class": ex_class, "screen_class": screen,
                               "reasons": reasons,
                               "constraints": _constraints_for(reasons)})
        elif s_ex - s_sc >= 2:
            verdict = "DOWNGRADE_RISK"
            final = screen
        else:
            verdict = "AGREE"
            final = ex_class
        text = llm.render(
            f"[CRITIC]\nanomaly_id={aid}\nexecutor_class={ex_class}\nscreen_class={screen}\nlegacy={legacy}\n"
            f"verdict={verdict}\nreasons={'; '.join(reasons)}"
        )
        _ = text  # rationale embedded in verdict record below
        verdicts.append({"anomaly_id": aid, "executor_class": ex_class, "critic_screen_class": screen,
                         "legacy_label": legacy, "verdict": verdict, "reasons": reasons + [text],
                         "missed_critical": missed, "escalated": False, "final_class": final})
    return verdicts, objections


def _constraints_for(reasons: List[str]) -> Dict[str, Any]:
    blob = " ".join(reasons).lower()
    con: Dict[str, Any] = {}
    if "contradict" in blob or "severe" in blob:
        con["depth_bump"] = 10.0
    if "growth" in blob:
        con["growth_bump"] = 1.0
    if "interaction" in blob:
        con["force_interaction"] = True
    if "erf" in blob:
        con["depth_bump"] = max(float(con.get("depth_bump", 0)), 5.0)
    if not con:
        con["depth_bump"] = 5.0
    return con
