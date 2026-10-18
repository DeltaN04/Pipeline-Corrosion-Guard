"""End-to-end: Critic+Executor recall on criticals must beat legacy labels,
and a stated fraction of planted missed-criticals must be caught."""
from pathlib import Path

import pandas as pd

from src.graph.runner import run_triage, extract_ground_truth
from src.agents import research


DATA = Path(__file__).resolve().parent.parent / "data" / "ili_anomalies.csv"
# Thresholds for honest acceptance criteria
RECALL_IMPROVEMENT_THRESHOLD = 0.05  # final recall must exceed legacy by at least this
CATCH_THRESHOLD = 0.70  # catch at least 70% of planted missed-criticals
INTERACTING_SHARE_MAX = 0.15  # interacting share < 15%
ESCALATED_SHARE_MAX = 0.20  # escalated share < 20%
MONITOR_SHARE_MIN = 0.10  # final MONITOR share >= 10%


def test_e2e_critic_beats_legacy():
    assert DATA.exists(), f"Generate data first: python data/generate_data.py (missing {DATA})"
    df = pd.read_csv(DATA)
    assert len(df) >= 250, "expected ~300 anomalies"
    gt = extract_ground_truth(df)
    final = run_triage(df, request="e2e validation run", ground_truth=gt)
    m = final["metrics"]
    assert m, "metrics missing (ground truth required)"

    # 1. Final critical recall exceeds legacy by at least 0.05
    assert m["final"]["recall_critical"] > m["legacy"]["recall_critical"] + RECALL_IMPROVEMENT_THRESHOLD, (
        f"final recall {m['final']['recall_critical']} must exceed legacy {m['legacy']['recall_critical']} by > {RECALL_IMPROVEMENT_THRESHOLD}")

    # 2. Planted missed-criticals caught
    planted = df[df.get("is_planted_miss", False)] if "is_planted_miss" in df.columns else df.iloc[0:0]
    if len(planted):
        v = {x["anomaly_id"]: x for x in final["verdicts"]}
        caught = sum(1 for aid in planted["anomaly_id"].astype(str)
                     if v.get(aid, {}).get("final_class") in ("IMMEDIATE", "60_DAY"))
        rate = caught / len(planted)
        assert rate >= CATCH_THRESHOLD, f"caught {caught}/{len(planted)}={rate:.2f} < {CATCH_THRESHOLD}"

    # 3. Interacting share < 15%
    enriched = research.enrich(final["anomalies"])  # re-enrich to get interaction flags
    interacting = sum(1 for r in enriched if r.get("interacting"))
    interacting_share = interacting / len(enriched)
    assert interacting_share < INTERACTING_SHARE_MAX, f"interacting share {interacting_share:.2f} >= {INTERACTING_SHARE_MAX}"

    # 4. Escalated share < 20%
    escalated = len(final.get("escalated_ids", []))
    escalated_share = escalated / len(final["verdicts"])
    assert escalated_share < ESCALATED_SHARE_MAX, f"escalated share {escalated_share:.2f} >= {ESCALATED_SHARE_MAX}"

    # 5. Final MONITOR share >= 10%
    from collections import Counter
    final_classes = Counter(v["final_class"] for v in final["verdicts"])
    monitor_share = final_classes.get("MONITOR", 0) / len(final["verdicts"])
    assert monitor_share >= MONITOR_SHARE_MIN, f"MONITOR share {monitor_share:.2f} < {MONITOR_SHARE_MIN}"

    # 6. Runtime < 30s
    assert final.get("elapsed_s", 999) < 30, "full run must complete in under 30s"

    # 7. No truth leakage (truth columns not in agent inputs)
    # This is tested separately in test_truth_stripped.py