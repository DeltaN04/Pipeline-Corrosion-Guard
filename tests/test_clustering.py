import pandas as pd

from src.tools.clustering import find_interactions


def test_interaction_basic():
    # Wall thickness 10mm -> axial threshold = 3*10/1000 = 0.03m
    # Clock window = 1.5 hours
    df = pd.DataFrame([
        {"anomaly_id": "A-1", "pipeline_id": "P", "chainage_m": 10.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},
        {"anomaly_id": "A-2", "pipeline_id": "P", "chainage_m": 10.02, "clock_position": 3.5, "wall_thickness_mm": 10.0},  # within 0.03m and 1.5h
        {"anomaly_id": "A-3", "pipeline_id": "P", "chainage_m": 50.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},  # too far axially
        {"anomaly_id": "A-4", "pipeline_id": "Q", "chainage_m": 10.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},  # different pipeline
        {"anomaly_id": "A-5", "pipeline_id": "P", "chainage_m": 10.01, "clock_position": 9.0, "wall_thickness_mm": 10.0},  # same chainage but clock diff > 1.5h
    ])
    out = find_interactions(df)
    assert set(out["A-1"]) == {"A-2"}
    assert out["A-3"] == []
    assert out["A-4"] == []
    assert out["A-5"] == []  # clock diff > 1.5h


def test_empty():
    df = pd.DataFrame(columns=["anomaly_id", "pipeline_id", "chainage_m", "clock_position", "wall_thickness_mm"])
    assert find_interactions(df) == {}