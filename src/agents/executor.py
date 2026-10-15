"""Executor Agent (Risk Engine): every number traceable to a tool call."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.tools import b31g, risk


def _clean_depth(depth: Any, constraints: Optional[Dict[str, Any]] = None) -> Any:
    """Apply critic conservative constraints on rework iterations."""
    if depth is None:
        return None
    try:
        d = float(depth)
    except (TypeError, ValueError):
        return None
    if constraints:
        d += float(constraints.get("depth_bump", 0) or 0)
    if d is not None and d > 100:
        return None  # unit-error rows cannot be triaged numerically; critic handles them
    return d


def execute(enriched: List[Dict[str, Any]], llm, constraints: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    constraints = constraints or {}
    results: List[Dict[str, Any]] = []
    for r in enriched:
        aid = str(r.get("anomaly_id"))
        con = constraints.get(aid, {})
        depth = _clean_depth(r.get("depth_pct"), con)
        growth = r.get("growth_rate_pct_per_yr")
        if growth is not None and con.get("growth_bump"):
            try:
                growth = float(growth) + float(con["growth_bump"])
            except (TypeError, ValueError):
                pass
        trace: Dict[str, Any] = {}
        if depth is None or depth < 0:
            # Dirty record: cannot compute strength; quarantine to 60_DAY for review (conservative),
            # critic will confirm/upgrade. Trace records why.
            trace = {"quarantined": True, "reason": f"invalid depth {r.get('depth_pct')}", "quality_flags": r.get("quality_flags", [])}
            cls = "60_DAY"
            score, factors = risk.risk_score(50, 0.7, growth, bool(r.get("hca")))
            score, factors = 65.0, ["quarantined_dirty_record"] + factors
            rationale = llm.render(
                f"[RISK_RATIONALE]\nanomaly_id={aid}\ndepth_pct={r.get('depth_pct')}\nerf=n/a\nclass={cls}\n"
                f"factors=quarantined_dirty_record\nsafe_pressure=n/a\nmaop={r.get('maop_mpa')}\nprojected=n/a\ngrowth={growth}"
            )
            results.append({"anomaly_id": aid, "safe_pressure_mpa": None, "erf": None, "depth_pct_used": None,
                            "projected_depth_pct_2yr": None, "risk_score": score, "risk_factors": factors,
                            "triage_class": cls, "rationale": rationale, "trace": trace})
            continue
        sp = b31g.safe_pressure_mpa(depth, r.get("length_mm") or 0, r.get("wall_thickness_mm") or 0,
                                    r.get("diameter_mm") or 0, r.get("smys_mpa") or 0)
        e = b31g.erf(r.get("maop_mpa"), sp)
        proj = risk.project_depth(depth, growth, 2.0)
        interacting = bool(con.get("force_interaction", False) or r.get("interacting"))
        score, factors = risk.risk_score(depth, e, growth, bool(r.get("hca")), int(r.get("location_class") or 1),
                                         bool(r.get("near_road")), bool(r.get("near_water")), interacting,
                                         bool(r.get("near_weld")), bool(r.get("note_severe")))
        cls = risk.executor_triage(depth, e, growth, proj)
        rationale = llm.render(
            f"[RISK_RATIONALE]\nanomaly_id={aid}\ndepth_pct={depth}\nerf={round(e, 3) if e is not None else 'n/a'}\n"
            f"class={cls}\nfactors={','.join(factors)}\nsafe_pressure={round(sp, 3) if sp else 'n/a'}\n"
            f"maop={r.get('maop_mpa')}\nprojected={round(proj, 1) if proj is not None else 'n/a'}\ngrowth={growth}"
        )
        trace = {"safe_pressure_tool": "b31g.safe_pressure_mpa", "erf_tool": "b31g.erf",
                 "projection_tool": "risk.project_depth", "score_tool": "risk.risk_score",
                 "triage_tool": "risk.executor_triage", "constraints_applied": con}
        results.append({"anomaly_id": aid, "safe_pressure_mpa": round(sp, 3) if sp else None,
                        "erf": round(e, 3) if e is not None else None, "depth_pct_used": round(depth, 1),
                        "projected_depth_pct_2yr": round(proj, 1) if proj is not None else None,
                        "risk_score": score, "risk_factors": factors, "triage_class": cls,
                        "rationale": rationale, "trace": trace})
    return results
