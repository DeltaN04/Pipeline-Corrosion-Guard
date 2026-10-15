"""Lookups: pipeline metadata, prior-inspection growth, HCA/location, nearby features, note keywords."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Static pipeline metadata (matches data/generate_data.py PIPELINES).
PIPELINES: Dict[str, Dict] = {
    "P-14": {"diameter_mm": 610.0, "wall_mm": 9.5, "smys_mpa": 359.0, "maop_mpa": 6.9, "hca_segments": [(8.0, 14.0)]},
    "P-21": {"diameter_mm": 457.0, "wall_mm": 8.0, "smys_mpa": 414.0, "maop_mpa": 7.5, "hca_segments": [(20.0, 26.0)]},
    "P-07": {"diameter_mm": 762.0, "wall_mm": 12.7, "smys_mpa": 317.0, "maop_mpa": 5.2, "hca_segments": [(2.0, 6.0)]},
    "P-33": {"diameter_mm": 323.0, "wall_mm": 6.4, "smys_mpa": 448.0, "maop_mpa": 8.0, "hca_segments": [(30.0, 38.0)]},
}

SEVERE_KEYWORDS = ["severe", "sharp", "undercut", "leak", "crack", "deep", "active", "gouge"]
MODERATE_KEYWORDS = ["moderate", "pitting", "general", "patch"]


def pipeline_metadata(pipeline_id: str) -> Dict:
    return PIPELINES.get(pipeline_id, {})


def growth_rate(prior_depth: Optional[float], depth: Optional[float], years: Optional[float]) -> Optional[float]:
    if prior_depth is None or depth is None or years is None or years <= 0:
        return None
    try:
        import math

        g = (float(depth) - float(prior_depth)) / float(years)
        if math.isnan(g) or math.isinf(g):
            return None
        return round(g, 2)
    except (TypeError, ValueError):
        return None


def hca_lookup(pipeline_id: str, chainage_m: float, record_hca: Optional[bool] = None) -> Tuple[bool, str]:
    """Confirm HCA from pipeline segment table; note disagreement with record flag."""
    meta = pipeline_metadata(pipeline_id)
    confirmed = False
    try:
        for lo, hi in meta.get("hca_segments", []):
            if lo <= float(chainage_m) <= hi:
                confirmed = True
                break
    except (TypeError, ValueError):
        pass
    note = "confirmed" if confirmed == bool(record_hca) else "HCA_MISMATCH(record=%s,map=%s)" % (record_hca, confirmed)
    return confirmed, note


def nearby_features(dist_weld_m: Optional[float], near_road: bool, near_water: bool) -> Dict[str, bool]:
    try:
        near_weld = dist_weld_m is not None and float(dist_weld_m) < 5.0
    except (TypeError, ValueError):
        near_weld = False
    return {"near_weld": bool(near_weld), "near_road": bool(near_road), "near_water": bool(near_water)}


def note_keywords(note: Optional[str]) -> Tuple[List[str], bool]:
    if not note:
        return [], False
    low = note.lower()
    flags = [k for k in SEVERE_KEYWORDS if k in low]
    return flags, len(flags) > 0
