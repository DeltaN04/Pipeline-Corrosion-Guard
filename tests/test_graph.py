"""Graph loop-termination test on a tiny batch."""
import pandas as pd

from src.graph.runner import run_triage


def _tiny_df():
    return pd.DataFrame([
        {"anomaly_id": "T-1", "pipeline_id": "P-14", "chainage_m": 1.0, "clock_position": 3.0,
         "depth_pct": 85.0, "length_mm": 120.0, "width_mm": 60.0, "wall_thickness_mm": 9.5,
         "diameter_mm": 610.0, "smys_mpa": 359.0, "maop_mpa": 6.9, "location_class": 2,
         "hca": True, "prior_depth_pct": 60.0, "years_between": 4.0, "dist_weld_m": 20.0,
         "near_road": False, "near_water": False, "inspector_note": "General wall loss.",
         "legacy_manual_label": "MONITOR", "true_class": "IMMEDIATE"},
        {"anomaly_id": "T-2", "pipeline_id": "P-14", "chainage_m": 30.0, "clock_position": 6.0,
         "depth_pct": 20.0, "length_mm": 80.0, "width_mm": 40.0, "wall_thickness_mm": 9.5,
         "diameter_mm": 610.0, "smys_mpa": 359.0, "maop_mpa": 6.9, "location_class": 1,
         "hca": False, "prior_depth_pct": 18.0, "years_between": 4.0, "dist_weld_m": 30.0,
         "near_road": False, "near_water": False, "inspector_note": "Minor pitting, monitor.",
         "legacy_manual_label": "MONITOR", "true_class": "MONITOR"},
    ])


def test_graph_terminates_and_upgrades():
    final = run_triage(_tiny_df(), request="test tiny run")
    assert final.get("iteration", 0) <= 2  # loop termination guarantee
    v = {x["anomaly_id"]: x for x in final["verdicts"]}
    assert v["T-1"]["final_class"] == "IMMEDIATE"  # critic must not let executor miss it
    assert v["T-2"]["final_class"] == "MONITOR"
    assert "outputs" in final and final["outputs"]["n_orders"] == 2
    assert len(final.get("messages", [])) >= 5  # A2A trace present
