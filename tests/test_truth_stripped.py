"""Test that truth columns are stripped before reaching agents."""
from src.graph.runner import df_to_anomalies, EVAL_ONLY_COLS
import pandas as pd
from data.ground_truth import generate_true_anomalies


def test_truth_columns_stripped():
    df = generate_true_anomalies(seed=42, n_total=10)
    anomalies = df_to_anomalies(df)
    for a in anomalies:
        for col in EVAL_ONLY_COLS:
            assert col not in a, f"Evaluation column {col} leaked to agent input"
    # Ensure key agent columns are present
    assert "anomaly_id" in anomalies[0]
    assert "depth_pct" in anomalies[0]
    assert "legacy_manual_label" in anomalies[0]