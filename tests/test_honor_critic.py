"""Honor-the-Critic invariant: final_class severity is never below critic_screen_class."""
from data.ground_truth import generate_true_anomalies

from src.graph.runner import run_triage, extract_ground_truth, df_to_anomalies

SEV = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}


def test_final_always_honors_critic():
    df = generate_true_anomalies(seed=42, n_total=100)
    gt = extract_ground_truth(df)
    final = run_triage(df, ground_truth=gt, verbose=False)
    violations = []
    for v in final["verdicts"]:
        if SEV[v["final_class"]] < SEV.get(v.get("critic_screen_class", "MONITOR"), 0):
            violations.append(v["anomaly_id"])
    assert not violations, f"final below critic screen for: {violations}"
    # Also confirm every verdict carries a critic_screen_class
    assert all("critic_screen_class" in v for v in final["verdicts"])


def test_critic_screen_metrics_row_present():
    df = generate_true_anomalies(seed=7, n_total=50)
    gt = extract_ground_truth(df)
    final = run_triage(df, ground_truth=gt, verbose=False)
    m = final["metrics"]
    assert "critic_screen" in m, "critic_screen metrics row missing"
    assert m["n_total"] == len(final["verdicts"])
