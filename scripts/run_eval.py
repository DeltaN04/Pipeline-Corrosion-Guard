#!/usr/bin/env python3
"""Full evaluation script: runs the complete CorrosionGuard pipeline and writes docs/metrics.json.

Usage: .venv/bin/python scripts/run_eval.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.graph.runner import run_triage, extract_ground_truth, df_to_anomalies
from src.agents import research


def bootstrap_ci(data: list, statistic_fn, n_bootstrap: int = 1000, confidence: float = 0.95) -> tuple:
    """Compute bootstrap confidence interval for a statistic."""
    rng = np.random.default_rng(42)
    stats = []
    n = len(data)
    for _ in range(n_bootstrap):
        sample = rng.choice(data, size=n, replace=True)
        stats.append(statistic_fn(sample))
    alpha = (1 - confidence) / 2
    lower = float(np.percentile(stats, alpha * 100))
    upper = float(np.percentile(stats, (1 - alpha) * 100))
    return lower, upper


def main() -> None:
    # Load data
    data_path = ROOT / "data" / "ili_anomalies.csv"
    df = pd.read_csv(data_path)
    gt = extract_ground_truth(df)

    # Run full pipeline
    final = run_triage(df, request="eval run", ground_truth=gt, verbose=True)
    m = final["metrics"]

    # Compute interacting share
    anomalies = df_to_anomalies(df)
    enriched = research.enrich(anomalies)
    interacting = sum(1 for r in enriched if r.get("interacting"))
    interacting_share = interacting / len(enriched)

    # Escalated share
    escalated = len(final.get("escalated_ids", []))
    total = len(final["verdicts"])
    escalated_share = escalated / total if total > 0 else 0

    # Class distribution
    from collections import Counter
    final_classes = Counter(v["final_class"] for v in final["verdicts"])
    class_dist = dict(final_classes)

    # Validation errors count
    val_errors = len(final.get("validation_errors", []))

    # Bootstrap CI for critical recall (final)
    verdicts = final["verdicts"]
    gt_items = [(aid, gt[aid]) for aid in gt]
    def final_critical_recall(sample):
        tp = sum(1 for aid, t in sample if t in ("IMMEDIATE", "60_DAY") and
                 next((v["final_class"] for v in verdicts if v["anomaly_id"] == aid), "MONITOR") in ("IMMEDIATE", "60_DAY"))
        fn = sum(1 for aid, t in sample if t in ("IMMEDIATE", "60_DAY") and
                 next((v["final_class"] for v in verdicts if v["anomaly_id"] == aid), "MONITOR") not in ("IMMEDIATE", "60_DAY"))
        return tp / max(1, tp + fn)

    ci_lower, ci_upper = bootstrap_ci(gt_items, final_critical_recall, n_bootstrap=1000)

    # Planted miss catch rate
    planted = df[df.get("is_planted_miss", False)] if "is_planted_miss" in df.columns else df.iloc[0:0]
    v_map = {x["anomaly_id"]: x for x in final["verdicts"]}
    caught = sum(1 for aid in planted["anomaly_id"].astype(str)
                 if v_map.get(aid, {}).get("final_class") in ("IMMEDIATE", "60_DAY"))
    planted_catch_rate = caught / len(planted) if len(planted) > 0 else 0

    # Assemble metrics
    metrics = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "n_total": len(df),
        "n_anomalies": len(final["verdicts"]),
        "iterations": final.get("iteration", 0),
        "legacy": m["legacy"],
        "executor": m["executor"],
        "final": m["final"],
        "confusion_final": m.get("confusion_final", {}),
        "missed_caught": m.get("missed_caught", 0),
        "rework_stats": m.get("rework_stats", {}),
        "interacting_count": interacting,
        "interacting_share": round(interacting_share, 4),
        "escalated_count": escalated,
        "escalated_share": round(escalated_share, 4),
        "final_class_distribution": class_dist,
        "monitor_share": round(final_classes.get("MONITOR", 0) / total, 4) if total > 0 else 0,
        "planted_miss_total": int(len(planted)),
        "planted_miss_caught": caught,
        "planted_miss_catch_rate": round(planted_catch_rate, 4),
        "final_critical_recall_ci": [round(ci_lower, 4), round(ci_upper, 4)],
        "validation_errors": val_errors,
        "runtime_seconds": final.get("elapsed_s", 0),
    }

    # Write metrics.json
    out_path = ROOT / "docs" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2))
    print(f"Wrote metrics to {out_path}")

    # Print summary
    print("\n=== Metrics Summary ===")
    for k, v in metrics.items():
        if k not in ("confusion_final", "rework_stats"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()