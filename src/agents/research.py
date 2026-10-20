"""Research Agent: enrich every anomaly via tools; validate data quality."""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.tools import clustering, lookup, note_llm, quality


def enrich(anomalies: List[Dict[str, Any]], llm=None) -> List[Dict[str, Any]]:
    df = pd.DataFrame(anomalies)
    interactions = clustering.find_interactions(df) if not df.empty else {}
    enriched: List[Dict[str, Any]] = []
    for rec in anomalies:
        r = dict(rec)
        # Growth from prior inspection
        try:
            g = lookup.growth_rate(r.get("prior_depth_pct"), r.get("depth_pct"), r.get("years_between"))
        except Exception:
            g = None
        r["growth_rate_pct_per_yr"] = g
        # HCA / location confirmation
        try:
            hca_conf, hca_note = lookup.hca_lookup(str(r.get("pipeline_id")), float(r.get("chainage_m", 0)), r.get("hca"))
        except Exception:
            hca_conf, hca_note = bool(r.get("hca")), "lookup_failed"
        r["hca_confirmed"] = hca_conf
        r["location_class_confirmed"] = r.get("location_class")
        feats = lookup.nearby_features(r.get("dist_weld_m"), bool(r.get("near_road")), bool(r.get("near_water")))
        r["near_weld"] = feats["near_weld"]
        flags, severe, reason = note_llm.assess_note(llm, r.get("inspector_note"), r.get("depth_pct"))
        r["note_flags"] = flags
        r["note_severe"] = severe
        r["note_reason"] = reason
        nbrs = interactions.get(str(r.get("anomaly_id")), [])
        r["interacting"] = len(nbrs) > 0
        r["interacting_with"] = nbrs
        q = quality.validate_record(r)
        if hca_note.startswith("HCA_MISMATCH"):
            q.append(hca_note)
        r["quality_flags"] = q
        enriched.append(r)
    return enriched
