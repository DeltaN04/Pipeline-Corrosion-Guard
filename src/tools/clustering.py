"""Interacting-anomaly clustering: anomalies on the same pipeline within a spacing threshold interact."""
from __future__ import annotations

from typing import Dict, List

import pandas as pd


def find_interactions(df: pd.DataFrame, spacing_m: float = 1.0) -> Dict[str, List[str]]:
    """Map anomaly_id -> list of neighbour anomaly_ids within spacing_m on same pipeline.

    Uses chainage ordering per pipeline; neighbours linked transitively share a cluster.
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
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if abs(ch[j] - ch[i]) <= spacing_m:
                    out[ids[i]].append(ids[j])
                    out[ids[j]].append(ids[i])
                else:
                    break
    return out
