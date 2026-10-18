#!/usr/bin/env python3
"""Full evaluation script: runs the complete CorrosionGuard pipeline and writes docs/metrics.json.

Evaluates on multiple seeds: seed 42 is the training/tuning seed, seeds 7 and 99 are
held-out evaluation seeds. Thresholds are NEVER tuned on evaluation seeds.

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
from data.ground_truth import generate_true_anomalies


def bootstrap_ci(pairs: list, statistic_fn, n_bootstrap: int = 1000, confidence: float = 0.95) -> tuple:
    """Compute bootstrap confidence interval for a statistic over (truth, pred) pairs."""
    rng = np.random.default_rng(42)
    stats = []
    n = len(pairs)
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = [pairs[i] for i in idx]
        stats.append(statistic_fn(sample))
    alpha = (1 - confidence) / 2
    lower = float(np.percentile(stats, alpha * 100))
    upper = float(np.percentile(stats, (1 - alpha) * 100))
    return lower, upper


def eval_seed(seed: int) -> dict:
    """Run full pipeline on one seed and return metrics."""
    df = generate_true_anomalies(seed=seed, n_total=300)
    gt = extract_ground_truth(df)
    final = run_triage(df, ground_truth=gt, verbose=False)
    m = final["metrics"]

    # Interacting share
    anomalies = df_to_anomalies(df)
    enriched = research.enrich(anomalies)
    interacting = sum(1 for r in enriched if r.get("interacting"))

    # Build (truth, legacy, executor_only, executor_after_rework, final) pairs
    eci = m.get("executor_class_initial", {})
    ear = m.get("executor_after_rework", {})
    by_enrich = {str(r.get("anomaly_id")): r for r in enriched}
    verdicts = final["verdicts"]
    vmap = {v["anomaly_id"]: v for v in verdicts}
    pairs = []
    for a, t in gt.items():
        pairs.append({
            "truth": t,
            "legacy": by_enrich.get(a, {}).get("legacy_manual_label", "MONITOR"),
            "executor_only": eci.get(a, "MONITOR"),
            "executor_after_rework": ear.get(a, "MONITOR"),
            "final": vmap.get(a, {}).get("final_class", "MONITOR"),
        })

    def crit(c):
        return c in ("IMMEDIATE", "60_DAY")

    def recall(pairs_):
        tp = sum(1 for p in pairs_ if crit(p["truth"]) and crit(p["final"]))
        fn = sum(1 for p in pairs_ if crit(p["truth"]) and not crit(p["final"]))
        return tp / max(1, tp + fn)

    def precision(pairs_):
        tp = sum(1 for p in pairs_ if crit(p["truth"]) and crit(p["final"]))
        fp = sum(1 for p in pairs_ if not crit(p["truth"]) and crit(p["final"]))
        return tp / max(1, tp + fp)

    ci_lo, ci_hi = bootstrap_ci(pairs, recall)
    p_lo, p_hi = bootstrap_ci(pairs, precision)

    return {
        "seed": seed,
        "n_total": len(df),
        "iterations": final.get("iteration", 0),
        "legacy": m["legacy"],
        "executor_only": m["executor_only"],
        "executor_after_rework": m["executor_after_rework"],
        "final": m["final"],
        "final_recall_ci95": [round(ci_lo, 3), round(ci_hi, 3)],
        "final_precision_ci95": [round(p_lo, 3), round(p_hi, 3)],
        "confusion_final": m.get("confusion_final", {}),
        "missed_caught": m["missed_caught"],
        "false_alarms": m["false_alarms"],
        "rework_stats": m.get("rework_stats", {}),
        "interacting_share": round(interacting / len(enriched), 4),
        "escalated_share": round(len(final.get("escalated_ids", [])) / len(final["verdicts"]), 4),
        "validation_errors": len(final.get("validation_errors", [])),
        "runtime_seconds": final.get("elapsed_s", 0),
    }


def main() -> None:
    seeds = [42, 7, 99]  # 42 = tuning seed, 7/99 = held-out evaluation
    per_seed = {s: eval_seed(s) for s in seeds}

    # Aggregate across evaluation seeds only (7, 99)
    eval_seeds = [7, 99]
    agg = {}
    for row in ("legacy", "executor_only", "executor_after_rework", "final"):
        recalls = [per_seed[s][row]["recall_critical"] for s in eval_seeds]
        precs = [per_seed[s][row]["precision_critical"] for s in eval_seeds]
        agg[row] = {
            "recall_critical_mean": round(float(np.mean(recalls)), 3),
            "precision_critical_mean": round(float(np.mean(precs)), 3),
        }

    metrics = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "tuning_seed": 42,
        "evaluation_seeds": eval_seeds,
        "per_seed": {str(s): per_seed[s] for s in seeds},
        "aggregate_eval_seeds": agg,
        "notes": [
            "Thresholds tuned on seed 42 only; seeds 7 and 99 are held-out evaluation.",
            "Precision target >= 0.40 not reachable by threshold tuning alone; root cause is ILI measurement noise.",
            "Rework convergence comes from the conservative Executor sharing the Critic's rule family.",
        ],
    }

    out_path = ROOT / "docs" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2))
    print(f"Wrote metrics to {out_path}")

    # Print summary table
    print("\n=== Final Metrics (critical = IMMEDIATE + 60_DAY) ===")
    print(f"{'Seed':>6} | {'System':>22} | {'Recall':>7} | {'Precision':>9} | {'TP':>3} | {'FP':>3} | {'FN':>3}")
    print("-" * 70)
    for s in seeds:
        ps = per_seed[s]
        for row in ("legacy", "executor_only", "executor_after_rework", "final"):
            d = ps[row]
            print(f"{s:>6} | {row:>22} | {d['recall_critical']:>7.3f} | {d['precision_critical']:>9.3f} | {d['tp']:>3} | {d['fp']:>3} | {d['fn']:>3}")
        print(f"       | missed_caught={ps['missed_caught']} false_alarms={ps['false_alarms']} interacting={ps['interacting_share']:.1%} escalated={ps['escalated_share']:.1%}")
        print("-" * 70)
    print(f"Aggregate eval seeds {eval_seeds}:")
    for row, d in agg.items():
        print(f"  {row}: recall={d['recall_critical_mean']:.3f} precision={d['precision_critical_mean']:.3f}")


if __name__ == "__main__":
    main()
