"""End-to-end: Critic+Executor recall on criticals must beat legacy labels,
and a stated fraction of planted missed-criticals must be caught."""
from pathlib import Path

import pandas as pd

from src.graph.runner import run_triage

DATA = Path(__file__).resolve().parent.parent / "data" / "ili_anomalies.csv"
# Threshold: catch at least 50% of planted missed-criticals as critical (IMMEDIATE/60_DAY).
CATCH_THRESHOLD = 0.50


def test_e2e_critic_beats_legacy():
    assert DATA.exists(), f"Generate data first: python data/generate_data.py (missing {DATA})"
    df = pd.read_csv(DATA)
    assert len(df) >= 250, "expected ~300 anomalies"
    final = run_triage(df, request="e2e validation run")
    m = final["metrics"]
    assert m, "metrics missing (true_class column required)"
    assert m["final"]["recall_critical"] > m["legacy"]["recall_critical"], (
        f"final recall {m['final']['recall_critical']} must exceed legacy {m['legacy']['recall_critical']}")
    planted = df[df.get("is_planted_miss", False)] if "is_planted_miss" in df.columns else df.iloc[0:0]
    if len(planted):
        v = {x["anomaly_id"]: x for x in final["verdicts"]}
        caught = sum(1 for aid in planted["anomaly_id"].astype(str)
                     if v.get(aid, {}).get("final_class") in ("IMMEDIATE", "60_DAY"))
        rate = caught / len(planted)
        assert rate >= CATCH_THRESHOLD, f"caught {caught}/{len(planted)}={rate:.2f} < {CATCH_THRESHOLD}"
    assert final.get("elapsed_s", 999) < 30, "full run must complete in under 30s"
