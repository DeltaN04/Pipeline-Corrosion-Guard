#!/usr/bin/env python3
"""LLM ablation: keyword-only notes vs keyword+LLM notes on paraphrased-note data.

Runs on seeds 7 and 99 (held-out). For each seed:
  (a) keyword-only   — mock backend, paraphrased notes (LLM never sees notes)
  (b) keyword + LLM  — real backend, paraphrased notes (LLM can raise severe)

Writes docs/metrics_llm.json. If no real-LLM backend is reachable, skips (b) with
a clear message rather than crashing.

Usage: LLM_BACKEND=ollama .venv/bin/python scripts/run_llm_ablation.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from data.ground_truth import generate_true_anomalies
from src.graph.runner import run_triage, extract_ground_truth, df_to_anomalies

SEEDS = (7, 99)
SYSTEMS = ("legacy", "executor_only", "executor_after_rework", "critic_screen", "final")


def _backend_label() -> str:
    return os.environ.get("LLM_BACKEND", "mock")


def _run_one(seed: int, backend: str, paraphrased: bool) -> dict:
    df = generate_true_anomalies(seed=seed, n_total=300, apply_noise=True, paraphrased_notes=paraphrased)
    gt = extract_ground_truth(df)
    final = run_triage(df, ground_truth=gt, verbose=False)
    m = final["metrics"]
    per = m["per_system"] if "per_system" in m else None
    out = {"seed": seed, "backend": backend, "paraphrased_notes": paraphrased,
           "missed_caught": m["missed_caught"], "false_alarms": m["false_alarms"]}
    if per:
        out["per_system"] = {name: {"recall_critical": per[name]["recall_critical"],
                                    "precision_critical": per[name]["precision_critical"],
                                    "imm_recall": per[name].get("imm_recall"),
                                    "imm_precision": per[name].get("imm_precision")}
                             for name in SYSTEMS}
    else:
        # builder._metrics rows: legacy / executor_only / executor_after_rework / critic_screen / final
        out["critical"] = {name: {"recall": m[name]["recall_critical"], "precision": m[name]["precision_critical"]}
                           for name in SYSTEMS}
    return out


def main() -> None:
    backend = _backend_label()
    results = {"requested_backend": backend, "paraphrased_seeds": list(SEEDS), "runs": []}

    # (a) keyword-only: mock backend always sees keyword path (LLM_BACKEND=mock → keyword result)
    os.environ["LLM_BACKEND"] = "mock"
    import src.llm.provider as provider
    provider.LLM_BACKEND = "mock"
    for seed in SEEDS:
        results["runs"].append(_run_one(seed, backend="mock(keyword-only)", paraphrased=True))

    # (b) keyword + LLM: only if a real backend is configured AND reachable
    if backend != "mock":
        provider.LLM_BACKEND = backend
        try:
            from src.llm.provider import get_chat_model
            llm = get_chat_model()
            # Reachability probe: one tiny invoke; on failure we skip (b)
            from src.llm.provider import llm_text
            probe = llm_text(llm, "[SUMMARY]\nprobe=ok")
            if not probe:
                raise RuntimeError("empty probe response")
            for seed in SEEDS:
                results["runs"].append(_run_one(seed, backend=backend, paraphrased=True))
        except Exception as e:  # noqa: BLE001 — fail soft, skip (b)
            results["skip_reason"] = (
                f"Real-LLM backend '{backend}' not reachable ({type(e).__name__}: {e}). "
                "Keyword-only results written; keyword+LLM skipped (no crash)."
            )
    else:
        results["skip_reason"] = (
            "LLM_BACKEND=mock: keyword-only baseline only. "
            "Set LLM_BACKEND=ollama or anthropic to also run keyword+LLM."
        )

    out_path = ROOT / "docs" / "metrics_llm.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_path}")
    for r in results["runs"]:
        crit = r.get("critical") or r.get("per_system", {})
        f = crit.get("final", {})
        print(f"  seed {r['seed']} [{r['backend']}] paraphrased={r['paraphrased_notes']}: "
              f"final recall={f.get('recall', f.get('recall_critical'))} "
              f"precision={f.get('precision', f.get('precision_critical'))} "
              f"missed_caught={r['missed_caught']} false_alarms={r['false_alarms']}")
    if results.get("skip_reason"):
        print(f"NOTE: {results['skip_reason']}")


if __name__ == "__main__":
    main()
