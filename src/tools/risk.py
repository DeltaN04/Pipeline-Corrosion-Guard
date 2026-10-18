"""Risk scoring, growth projection, and executor triage rules."""
from __future__ import annotations

from typing import List, Optional, Tuple

SEVERITY = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}
INV_SEVERITY = {v: k for k, v in SEVERITY.items()}


def project_depth(depth_pct: Optional[float], growth: Optional[float], years: float = 2.0) -> Optional[float]:
    if depth_pct is None or growth is None:
        return None
    try:
        return min(100.0, depth_pct + growth * years)
    except TypeError:
        return None


def more_severe(a: str, b: str) -> str:
    return a if SEVERITY[a] >= SEVERITY[b] else b


def risk_score(
    depth_pct: Optional[float] = None,
    erf_val: Optional[float] = None,
    growth: Optional[float] = None,
    hca: bool = False,
    location_class: int = 1,
    near_road: bool = False,
    near_water: bool = False,
    interacting: bool = False,
    near_weld: bool = False,
    note_severe: bool = False,
) -> Tuple[float, List[str]]:
    """Transparent weighted likelihood x consequence score in [0,100]. Returns (score, factors)."""
    d = depth_pct or 0
    e = erf_val or 0
    g = growth if growth is not None else 0
    likelihood = min(100.0, 0.55 * d + 25.0 * min(e, 1.5) + 4.0 * min(max(g, 0), 8.0))
    consequence = 20.0
    factors: List[str] = []
    if hca:
        consequence += 30.0
        factors.append("HCA")
    consequence += {1: 0, 2: 5, 3: 10, 4: 15}.get(location_class or 1, 0)
    if (location_class or 1) >= 3:
        factors.append(f"LocationClass-{location_class}")
    if near_road:
        consequence += 8.0
        factors.append("near_road_crossing")
    if near_water:
        consequence += 10.0
        factors.append("near_water_body")
    if near_weld:
        consequence += 5.0
        factors.append("near_weld(<5m)")
    if interacting:
        likelihood = min(100.0, likelihood + 10.0)
        factors.append("interacting_anomalies")
    if note_severe:
        likelihood = min(100.0, likelihood + 8.0)
        factors.append("inspector_note_severe_keywords")
    if d >= 80:
        factors.append("depth>=80%")
    elif d >= 60:
        factors.append("depth>=60%")
    if e >= 1.0:
        factors.append("ERF>=1.0")
    elif e >= 0.85:
        factors.append("ERF>=0.85")
    if (g or 0) >= 4:
        factors.append("rapid_growth>=4%/yr")
    score = round((0.6 * likelihood + 0.4 * consequence), 1)
    return max(0.0, min(100.0, score)), factors


def executor_triage(
    depth_pct: Optional[float],
    erf_val: Optional[float],
    growth: Optional[float],
    projected_2yr: Optional[float],
) -> str:
    """Executor (numbers-only) triage: deliberately ignores notes/context/interaction.

    The Critic independently re-adds context, which is how missed criticals get caught.
    """
    d = depth_pct if depth_pct is not None else -1
    e = erf_val if erf_val is not None else -1
    g = growth if growth is not None else -1
    p = projected_2yr if projected_2yr is not None else -1
    if d >= 80 or (e is not None and e >= 1.0) or (d >= 60 and (g or -1) >= 5):
        return "IMMEDIATE"
    if d >= 60 or (e is not None and e >= 0.85) or (g or -1) >= 4 or (p or -1) >= 80:
        return "60_DAY"
    if d >= 40 or (e is not None and e >= 0.6) or (g or -1) >= 2:
        return "180_DAY"
    return "MONITOR"


def executor_triage_conservative(
    depth_pct: Optional[float],
    erf_val: Optional[float],
    growth: Optional[float],
    projected_2yr: Optional[float],
    hca: bool = False,
    near_road: bool = False,
    near_water: bool = False,
    near_weld: bool = False,
    interacting: bool = False,
    note_severe: bool = False,
) -> str:
    """Conservative re-run triage: applies full context when critic demands rework.

    This allows the rework loop to actually raise the class when constraints
    like force_interaction, depth_bump, growth_bump, hca, note_severe are applied.
    """
    # Use full_screen_class logic but with a slightly lower threshold for IMMEDIATE
    # to avoid over-escalation, then map to triage classes.
    d = depth_pct if depth_pct is not None else -1
    e = erf_val if erf_val is not None else -1
    g = growth if growth is not None else -1
    p = projected_2yr if projected_2yr is not None else -1

    # IMMEDIATE thresholds (conservative)
    if d >= 80 or (e is not None and e >= 1.0) or (d >= 60 and (g or -1) >= 4):
        return "IMMEDIATE"
    # Note contradiction with moderate depth -> IMMEDIATE
    if note_severe and d >= 50:
        return "IMMEDIATE"
    # Deep defect with interaction/HCA
    if d >= 70 and (interacting or hca):
        return "IMMEDIATE"

    # 60_DAY thresholds
    if d >= 60:
        return "60_DAY"
    if e is not None and e >= 0.85:
        return "60_DAY"
    if (g or -1) >= 4:
        return "60_DAY"
    if d >= 50 and (hca or near_road or near_water or interacting or near_weld):
        return "60_DAY"
    if (p or -1) >= 80:
        return "60_DAY"

    # 180_DAY thresholds
    if d >= 40:
        return "180_DAY"
    if e is not None and e >= 0.6:
        return "180_DAY"
    if (g or -1) >= 2:
        return "180_DAY"
    if interacting:
        return "180_DAY"
    if hca and d >= 30:
        return "180_DAY"

    return "MONITOR"


def full_screen_class(
    depth_pct: Optional[float],
    erf_val: Optional[float],
    growth: Optional[float],
    projected_2yr: Optional[float],
    hca: bool = False,
    near_road: bool = False,
    near_water: bool = False,
    near_weld: bool = False,
    interacting: bool = False,
    note_severe: bool = False,
) -> Tuple[str, List[str]]:
    """Full engineering + context screening (used for ground truth and Critic)."""
    d = depth_pct if depth_pct is not None else -1
    e = erf_val if erf_val is not None else -1
    g = growth if growth is not None else -1
    reasons: List[str] = []
    if d >= 80:
        reasons.append("depth>80%")
    if e != -1 and e >= 1.0:
        reasons.append("ERF>=1.0 (fails at MAOP)")
    if d >= 60 and (g or -1) >= 4:
        reasons.append("depth>=60% with rapid growth>=4%/yr")
    if note_severe and d >= 50:
        reasons.append("inspector note contradicts numeric depth (severe keywords)")
    if d >= 70 and (interacting or hca):
        reasons.append("deep defect with interaction/HCA context")
    if reasons:
        return "IMMEDIATE", reasons
    if d >= 60:
        reasons.append("depth>=60%")
    if e != -1 and e >= 0.85:
        reasons.append("ERF>=0.85")
    if (g or -1) >= 4:
        reasons.append("rapid growth>=4%/yr")
    if d >= 50 and (hca or near_road or near_water or interacting or near_weld):
        reasons.append("depth>=50% with HCA/crossing/weld/interaction context")
    if (projected_2yr or -1) >= 80:
        reasons.append("projected depth>=80% within 2yr")
    if reasons:
        return "60_DAY", reasons
    if d >= 40:
        reasons.append("depth>=40%")
    if e != -1 and e >= 0.6:
        reasons.append("ERF>=0.6")
    if (g or -1) >= 2:
        reasons.append("growth>=2%/yr")
    if interacting:
        reasons.append("interacting anomalies")
    if hca and d >= 30:
        reasons.append("HCA with depth>=30%")
    if reasons:
        return "180_DAY", reasons
    return "MONITOR", ["no screening threshold breached"]
