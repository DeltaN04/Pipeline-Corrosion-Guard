"""Data-quality validation rules. Returns list of flag strings (empty = clean)."""
from __future__ import annotations

from typing import Any, Dict, List


def validate_record(rec: Dict[str, Any]) -> List[str]:
    flags: List[str] = []

    def is_missing(v: Any) -> bool:
        if v is None:
            return True
        try:
            import math

            if isinstance(v, float) and math.isnan(v):
                return True
        except Exception:
            pass
        if isinstance(v, str) and v.strip() in ("", "NA", "N/A", "null"):
            return True
        return False

    for f in ("depth_pct", "length_mm", "wall_thickness_mm", "diameter_mm", "smys_mpa", "maop_mpa"):
        if is_missing(rec.get(f)):
            flags.append(f"MISSING:{f}")
    d = rec.get("depth_pct")
    try:
        if d is not None and not (isinstance(d, float) and __import__("math").isnan(d)):
            d = float(d)
            if d < 0:
                flags.append("IMPOSSIBLE:negative_depth")
            if d > 100:
                # Likely unit error: depth entered in 0-1000 scale or mm.
                flags.append("UNIT_ERROR:depth_pct>100")
    except (TypeError, ValueError):
        flags.append("INVALID:depth_pct_not_numeric")
    for f in ("length_mm", "width_mm", "wall_thickness_mm", "diameter_mm"):
        try:
            v = rec.get(f)
            if v is not None and float(v) <= 0:
                flags.append(f"IMPOSSIBLE:{f}<=0")
        except (TypeError, ValueError):
            pass
    try:
        w = rec.get("wall_thickness_mm")
        if w is not None and float(w) > 50:
            flags.append("UNIT_ERROR:wall_mm>50_suspect_inch_mm_mixup")
    except (TypeError, ValueError):
        pass
    try:
        dia = rec.get("diameter_mm")
        if dia is not None and (float(dia) < 50 or float(dia) > 1500):
            flags.append("SUSPECT:diameter_out_of_range")
    except (TypeError, ValueError):
        pass
    if rec.get("prior_depth_pct") is not None and d is not None:
        try:
            if float(rec["prior_depth_pct"]) > float(d) + 0.5 and not any(
                "MISSING" in f for f in flags
            ):
                flags.append("SUSPECT:prior_depth exceeds current (healing impossible)")
        except (TypeError, ValueError):
            pass
    return flags
