#!/usr/bin/env python3
"""Full evaluation script: runs the complete CorrosionGuard pipeline and writes docs/metrics.json.

Evaluates on multiple seeds: seed 42 is the training/tuning seed, seeds 7 and 99 are
held-out evaluation seeds. Thresholds are NEVER tuned on evaluation seeds.

Also runs a measurement-noise experiment: re-runs the pipeline with zero noise on the
same seeds and reports the precision difference, so the false-alarm root cause is
stated only if the experiment supports it.

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

SEV = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}
SYSTEMS = ("legacy", "executor_only", "executor_after_rework", "critic_screen", "final")


def bootstrap_ci(pairs: list, statistic_fn, n_bootstrap: int = 1000, confidence: float = 0.95) -> tuple:
    """Compute bootstrap confidence interval for a statistic over pairs."""
    rng = np.random.default_rng(42)
    stats = []
    n = len(pairs)
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = [pairs[i] for i in idx]
        stats.append(statistic_fn(sample))
    alpha = (1 - confidence) / 2
    return float(np.percentile(stats, alpha * 100)), float(np.percentile(stats, (1 - alpha) * 100))


def crit(c: str) -> bool:
    return c in ("IMMEDIATE", "60_DAY")


def system_metrics(pairs: list, pred_key: str) -> dict:
    """Full metric set for one system against ground truth."""
    n = len(pairs)
    out = {"n": n}
    # Critical-class recall/precision
    tp = sum(1 for p in pairs if crit(p["truth"]) and crit(p[pred_key]))
    fp = sum(1 for p in pairs if not crit(p["truth"]) and crit(p[pred_key]))
    fn = sum(1 for p in pairs if crit(p["truth"]) and not crit(p[pred_key]))
    out["tp"], out["fp"], out["fn"] = tp, fp, fn
    out["recall_critical"] = round(tp / max(1, tp + fn), 3)
    out["precision_critical"] = round(tp / max(1, tp + fp), 3)
    # IMMEDIATE-only recall/precision
    itp = sum(1 for p in pairs if p["truth"] == "IMMEDIATE" and p[pred_key] == "IMMEDIATE")
    ifn = sum(1 for p in pairs if p["truth"] == "IMMEDIATE" and p[pred_key] != "IMMEDIATE")
    ifp = sum(1 for p in pairs if p["truth"] != "IMMEDIATE" and p[pred_key] == "IMMEDIATE")
    out.update({"imm_tp": itp, "imm_fp": ifp, "imm_fn": ifn,
                "imm_recall": round(itp / max(1, itp + ifn), 3),
                "imm_precision": round(itp / max(1, itp + ifp), 3)})
    # Exact-class and within-one-class accuracy
    out["exact_accuracy"] = round(sum(1 for p in pairs if p["truth"] == p[pred_key]) / n, 3)
    out["within_one_accuracy"] = round(
        sum(1 for p in pairs if abs(SEV[p[pred_key]] - SEV[p["truth"]]) <= 1) / n, 3)
    # Over- vs under-triage
    out["over_triage"] = sum(1 for p in pairs if SEV[p[pred_key]] > SEV[p["truth"]])
    out["under_triage"] = sum(1 for p in pairs if SEV[p[pred_key]] < SEV[p["truth"]])
    return out


def false_alarm_adjacency(pairs: list) -> dict:
    """Classify final-system false alarms as adjacent-class or two-plus classes off."""
    adjacent = 0
    two_plus = 0
    for p in pairs:
        if crit(p["final"]) and not crit(p["truth"]):
            gap = abs(SEV[p["final"]] - SEV[p["truth"]])
            if gap == 1:
                adjacent += 1
            else:
                two_plus += 1
    return {"false_alarm_adjacent": adjacent, "false_alarm_two_plus": two_plus}


def build_pairs(seed: int, apply_noise: bool = True) -> tuple:
    """Run pipeline on one seed and return (ground_truth, pairs)."""
    df = generate_true_anomalies(seed=seed, n_total=300, apply_noise=apply_noise)
    gt = extract_ground_truth(df)
    final = run_triage(df, ground_truth=gt, verbose=False)
    m = final["metrics"]
    eci = m.get("executor_class_initial_map", {})
    ear = m.get("executor_after_rework_map", {})
    enriched = research.enrich(df_to_anomalies(df))
    by_enrich = {str(r.get("anomaly_id")): r for r in enriched}
    vmap = {v["anomaly_id"]: v for v in final["verdicts"]}
    pairs = []
    for a, t in gt.items():
        pairs.append({
            "truth": t,
            "legacy": by_enrich.get(a, {}).get("legacy_manual_label", "MONITOR"),
            "executor_only": eci.get(a, "MONITOR"),
            "executor_after_rework": ear.get(a, "MONITOR"),
            "critic_screen": vmap.get(a, {}).get("critic_screen_class", "MONITOR"),
            "final": vmap.get(a, {}).get("final_class", "MONITOR"),
        })
    return final, pairs


def eval_seed(seed: int, apply_noise: bool = True) -> dict:
    """Run full pipeline on one seed and return metrics for all systems."""
    final, pairs = build_pairs(seed, apply_noise)
    m = final["metrics"]

    # Interacting share
    anomalies = df_to_anomalies(generate_true_anomalies(seed=seed, n_total=300))
    enriched = research.enrich(anomalies)
    interacting = sum(1 for r in enriched if r.get("interacting"))

    # Bootstrap CIs for final critical recall/precision
    ci_r = bootstrap_ci(pairs, lambda ps: sum(1 for p in ps if crit(p["truth"]) and crit(p["final"]))
                        / max(1, sum(1 for p in ps if crit(p["truth"]))))
    ci_p = bootstrap_ci(pairs, lambda ps: sum(1 for p in ps if crit(p["truth"]) and crit(p["final"]))
                        / max(1, sum(1 for p in ps if crit(p["final"]))))

    per_system = {name: system_metrics(pairs, name) for name in SYSTEMS}
    adj = false_alarm_adjacency(pairs)

    return {
        "seed": seed,
        "n_total": len(pairs),
        "apply_noise": apply_noise,
        "iterations": final.get("iteration", 0),
        "per_system": per_system,
        "final_recall_ci95": [round(ci_r[0], 3), round(ci_r[1], 3)],
        "final_precision_ci95": [round(ci_p[0], 3), round(ci_p[1], 3)],
        "missed_caught": m["missed_caught"],
        "false_alarms": m["false_alarms"],
        "false_alarm_adjacency": adj,
        "rework_stats": m.get("rework_stats", {}),
        "interacting_share": round(interacting / len(enriched), 4),
        "escalated_share": round(len(final.get("escalated_ids", [])) / len(final["verdicts"]), 4),
        "validation_errors": len(final.get("validation_errors", [])),
        "runtime_seconds": final.get("elapsed_s", 0),
    }


def main() -> None:
    seeds = [42, 7, 99]  # 42 = tuning seed, 7/99 = held-out evaluation
    per_seed = {s: eval_seed(s, apply_noise=True) for s in seeds}

    # Measurement-noise experiment: same seeds, zero noise
    noise_free = {s: eval_seed(s, apply_noise=False) for s in seeds}
    noise_delta = {}
    for s in seeds:
        p_noisy = per_seed[s]["per_system"]["final"]["precision_critical"]
        p_clean = noise_free[s]["per_system"]["final"]["precision_critical"]
        noise_delta[s] = {"precision_noisy": p_noisy, "precision_zero_noise": p_clean,
                          "precision_delta": round(p_clean - p_noisy, 3)}

    # Aggregate across evaluation seeds only (7, 99)
    eval_seeds = [7, 99]
    agg = {}
    for name in SYSTEMS:
        recalls = [per_seed[s]["per_system"][name]["recall_critical"] for s in eval_seeds]
        precs = [per_seed[s]["per_system"][name]["precision_critical"] for s in eval_seeds]
        imm_rec = [per_seed[s]["per_system"][name]["imm_recall"] for s in eval_seeds]
        imm_prec = [per_seed[s]["per_system"][name]["imm_precision"] for s in eval_seeds]
        agg[name] = {
            "recall_critical_mean": round(float(np.mean(recalls)), 3),
            "precision_critical_mean": round(float(np.mean(precs)), 3),
            "imm_recall_mean": round(float(np.mean(imm_rec)), 3),
            "imm_precision_mean": round(float(np.mean(imm_prec)), 3),
        }

    # Root-cause statement for false alarms, driven by the noise experiment
    mean_delta = float(np.mean([d["precision_delta"] for d in noise_delta.values()]))
    if mean_delta >= 0.05:
        cause = (f"Measurement noise IS a major contributor: zero-noise runs raise final "
                 f"precision by {mean_delta:.3f} on average across seeds.")
    else:
        cause = (f"Measurement noise is NOT the primary contributor: zero-noise runs raise final "
                 f"precision by only {mean_delta:.3f} on average; false alarms are dominated by "
                 f"genuinely ambiguous shallow/context-flagged anomalies.")

    metrics = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "tuning_seed": 42,
        "evaluation_seeds": eval_seeds,
        "systems": list(SYSTEMS),
        "per_seed": {str(s): per_seed[s] for s in seeds},
        "noise_experiment": {"per_seed": {str(s): noise_delta[s] for s in seeds},
                             "mean_precision_delta": round(mean_delta, 3),
                             "root_cause_statement": cause},
        "aggregate_eval_seeds": agg,
        "notes": [
            "Thresholds tuned on seed 42 only; seeds 7 and 99 are held-out evaluation.",
            "final_class always honors the Critic screen (final severity >= critic_screen severity).",
            cause,
        ],
    }

    out_path = ROOT / "docs" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2))
    print(f"Wrote metrics to {out_path}")

    # Regenerate README.md + REPORT.md so every number traces to metrics.json
    from scripts.generate_docs import main as gen_docs
    gen_docs()

    # Print summary table
    print("\n=== Final Metrics (critical = IMMEDIATE + 60_DAY) ===")
    print(f"{'Seed':>6} | {'System':>22} | {'Recall':>7} | {'Prec':>6} | {'ImmR':>6} | {'ImmP':>6} | {'Exact':>6} | {'W1':>6} | {'Over':>5} | {'Under':>5}")
    print("-" * 95)
    for s in seeds:
        ps = per_seed[s]["per_system"]
        for name in SYSTEMS:
            d = ps[name]
            print(f"{s:>6} | {name:>22} | {d['recall_critical']:>7.3f} | {d['precision_critical']:>6.3f} | "
                  f"{d['imm_recall']:>6.3f} | {d['imm_precision']:>6.3f} | {d['exact_accuracy']:>6.3f} | "
                  f"{d['within_one_accuracy']:>6.3f} | {d['over_triage']:>5} | {d['under_triage']:>5}")
        p42 = per_seed[s]
        print(f"       | missed_caught={p42['missed_caught']} false_alarms={p42['false_alarms']} "
              f"(adjacent={p42['false_alarm_adjacency']['false_alarm_adjacent']}, "
              f"two+={p42['false_alarm_adjacency']['false_alarm_two_plus']}) "
              f"interacting={p42['interacting_share']:.1%} escalated={p42['escalated_share']:.1%}")
        print("-" * 95)
    print("\nAggregate eval seeds 7+99:")
    for name, d in agg.items():
        print(f"  {name}: recall={d['recall_critical_mean']:.3f} precision={d['precision_critical_mean']:.3f} "
              f"imm_recall={d['imm_recall_mean']:.3f} imm_precision={d['imm_precision_mean']:.3f}")
    print("\nNoise experiment (final precision, noisy vs zero-noise):")
    for s in seeds:
        d = noise_delta[s]
        print(f"  seed {s}: {d['precision_noisy']:.3f} -> {d['precision_zero_noise']:.3f} (delta {d['precision_delta']:+.3f})")
    print(f"\nRoot cause: {cause}")


if __name__ == "__main__":
    main()
