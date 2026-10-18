"""Synthetic ILI anomaly generator (seeded, reproducible). SYNTHETIC DATA ONLY.

This module now uses data/ground_truth.py for the independent truth model.
The observed columns agents see = true values + measurement noise (ILI sizing tolerance).
Legacy manual labels are derived from observed values with human lapses.
~5% dirty records are planted for the Research Agent.

Formulas are simplified educational approximations, NOT for real integrity decisions.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.ground_truth import generate_true_anomalies


def generate(seed: int = 42, n_total: int = 300):
    """Generate synthetic ILI data using the independent ground truth model."""
    df = generate_true_anomalies(seed=seed, n_total=n_total)

    # Select columns for CSV output (includes truth_class for evaluation, stripped before agents)
    output_cols = [
        "anomaly_id", "pipeline_id", "chainage_m", "clock_position",
        "depth_pct", "length_mm", "width_mm",
        "wall_thickness_mm", "diameter_mm",
        "smys_mpa", "maop_mpa", "location_class",
        "hca", "prior_depth_pct", "years_between",
        "dist_weld_m", "near_road", "near_water",
        "inspector_note",
        "legacy_manual_label",
        "truth_class",  # For evaluation (ground truth)
        "is_planted_miss", "is_dirty",  # For evaluation
    ]
    return df[output_cols]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--out", default=str(Path(__file__).parent / "ili_anomalies.csv"))
    args = ap.parse_args()
    df = generate(seed=args.seed, n_total=args.n)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out} | missed={int(df.is_planted_miss.sum())} dirty={int(df.is_dirty.sum())}")
    # Print truth distribution by re-importing ground truth
    from data.ground_truth import generate_true_anomalies
    truth_df = generate_true_anomalies(seed=args.seed, n_total=args.n)
    print("Truth class:", truth_df["truth_class"].value_counts().to_dict())
    print("Legacy:", df["legacy_manual_label"].value_counts().to_dict())


if __name__ == "__main__":
    main()