import pandas as pd

from src.tools.clustering import find_interactions


def test_interaction_basic():
    # Wall thickness 10mm -> axial threshold = 50*10/1000 = 0.5m (documented screening window, not 3x)
    # Clock window = 1.5 hours
    df = pd.DataFrame([
        {"anomaly_id": "A-1", "pipeline_id": "P", "chainage_m": 10.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},
        {"anomaly_id": "A-2", "pipeline_id": "P", "chainage_m": 10.02, "clock_position": 3.5, "wall_thickness_mm": 10.0},  # within 0.5m and 1.5h
        {"anomaly_id": "A-3", "pipeline_id": "P", "chainage_m": 50.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},  # too far axially
        {"anomaly_id": "A-4", "pipeline_id": "Q", "chainage_m": 10.0, "clock_position": 3.0, "wall_thickness_mm": 10.0},  # different pipeline
        {"anomaly_id": "A-5", "pipeline_id": "P", "chainage_m": 10.01, "clock_position": 9.0, "wall_thickness_mm": 10.0},  # same chainage but clock diff > 1.5h
    ])
    out = find_interactions(df)
    assert set(out["A-1"]) == {"A-2"}
    assert out["A-3"] == []
    assert out["A-4"] == []
    assert out["A-5"] == []  # clock diff > 1.5h


def test_3x_rule_would_miss_clusters():
    """Document why 3x wall_thickness is too tight for screening on long pipelines.

    ASME B31G's 3x rule is a mechanical-coalescence criterion, not a screening window.
    On a 40 km pipeline with ~75 anomalies per segment, a 30mm window would almost
    never trigger — the docstring justifies the 50x screening window instead.
    """
    from src.tools.clustering import AXIAL_MULTIPLIER
    # 3x window for 10mm wall = 0.03m — a genuine cluster at 0.1m spacing would be missed
    tight = 3.0 * 10.0 / 1000.0
    df = pd.DataFrame([
        {"anomaly_id": "C-1", "pipeline_id": "P", "chainage_m": 100.0, "clock_position": 6.0, "wall_thickness_mm": 10.0},
        {"anomaly_id": "C-2", "pipeline_id": "P", "chainage_m": 100.1, "clock_position": 6.2, "wall_thickness_mm": 10.0},
    ])
    # With the tight 3x rule they would NOT interact; with the documented 50x window they DO
    assert AXIAL_MULTIPLIER * 10.0 / 1000.0 >= 0.1, "50x window must catch 0.1m-spaced clusters"
    assert tight < 0.1, "3x rule would miss 0.1m-spaced clusters — justifying the wider screening window"
    out = find_interactions(df)
    assert set(out["C-1"]) == {"C-2"}  # our 50x rule catches them


def test_empty():
    df = pd.DataFrame(columns=["anomaly_id", "pipeline_id", "chainage_m", "clock_position", "wall_thickness_mm"])
    assert find_interactions(df) == {}