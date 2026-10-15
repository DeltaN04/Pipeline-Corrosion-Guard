import pandas as pd

from src.tools.clustering import find_interactions


def test_interaction_basic():
    df = pd.DataFrame([
        {"anomaly_id": "A-1", "pipeline_id": "P", "chainage_m": 10.0},
        {"anomaly_id": "A-2", "pipeline_id": "P", "chainage_m": 10.5},
        {"anomaly_id": "A-3", "pipeline_id": "P", "chainage_m": 50.0},
        {"anomaly_id": "A-4", "pipeline_id": "Q", "chainage_m": 10.2},
    ])
    out = find_interactions(df, spacing_m=1.0)
    assert set(out["A-1"]) == {"A-2"}
    assert out["A-3"] == []
    assert out["A-4"] == []  # different pipeline never interacts


def test_empty():
    df = pd.DataFrame(columns=["anomaly_id", "pipeline_id", "chainage_m"])
    assert find_interactions(df) == {}
