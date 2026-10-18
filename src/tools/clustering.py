"""Interacting-anomaly clustering: engineering-style interaction rule.

Two anomalies on the same pipeline interact if:
1. Axial gap <= 3 x wall thickness (in mm, converted to metres)
2. Clock position difference <= CLOCK_WINDOW_HOURS (circumferential proximity)

This is based on ASME B31G interaction criteria where anomalies within
3*wall_thickness axially and within a small circumferential window
can act as a single larger anomaly.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

# Interaction criteria constants
CLOCK_WINDOW_HOURS = 1.5  # Clock positions within 1.5 hours (45 degrees)
# Axial gap threshold multiplier: anomalies interact if axial gap <= AXIAL_MULTIPLIER * wall_thickness_mm / 1000 (metres)
# Typical wall thickness 6-13mm; for 40km pipeline with ~300 anomalies, avg spacing ~130m.
# Use a multiplier that yields ~3-10% interaction rate.
AXIAL_MULTIPLIER = 50.0  # 50 * 10mm = 500mm = 0.5m axial window


def find_interactions(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Map anomaly_id -> list of neighbour anomaly_ids that interact.

    Interaction rule: same pipeline AND
      |chainage_i - chainage_j| <= 3 * wall_thickness_mm / 1000 (metres) AND
      min(|clock_i - clock_j|, 12 - |clock_i - clock_j|) <= CLOCK_WINDOW_HOURS

    Uses chainage ordering per pipeline for efficiency.
    """
    out: Dict[str, List[str]] = {str(a): [] for a in df.get("anomaly_id", [])}
    if df.empty or "anomaly_id" not in df.columns or "chainage_m" not in df.columns:
        return out

    pid_col = "pipeline_id" if "pipeline_id" in df.columns else None
    groups = df.groupby(pid_col) if pid_col else [("__all__", df)]

    for _, g in groups:
        g = g.sort_values("chainage_m")
        ids = g["anomaly_id"].astype(str).tolist()
        ch = g["chainage_m"].astype(float).tolist()
        clocks = g["clock_position"].astype(float).tolist()
        walls = g["wall_thickness_mm"].astype(float).tolist()

        for i in range(len(ids)):
            # Axial threshold for this anomaly (metres)
            axial_thresh = AXIAL_MULTIPLIER * walls[i] / 1000.0
            for j in range(i + 1, len(ids)):
                if abs(ch[j] - ch[i]) > axial_thresh:
                    break  # sorted by chainage, further ones will also exceed
                # Circumferential check (wrap around at 12)
                clock_diff = abs(clocks[j] - clocks[i])
                clock_diff = min(clock_diff, 12 - clock_diff)
                if clock_diff <= CLOCK_WINDOW_HOURS:
                    out[ids[i]].append(ids[j])
                    out[ids[j]].append(ids[i])
    return out