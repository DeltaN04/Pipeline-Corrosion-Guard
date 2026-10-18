"""Business Automation Agent: work orders, summary report, notification payloads (written to disk, not sent)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from src.llm.provider import llm_text

DUE = {"IMMEDIATE": 0, "60_DAY": 60, "180_DAY": 180, "MONITOR": 365}
ACTION = {
    "IMMEDIATE": "Immediate field verification + pressure restriction review; schedule dig within 7 days.",
    "60_DAY": "Schedule excavation and recoat/repair within 60 days; interim monitoring.",
    "180_DAY": "Schedule assessment/repair within 180 days; trend growth at next review.",
    "MONITOR": "No dig; retain in monitoring program and re-evaluate at next ILI run.",
}

# Only IMMEDIATE and 60_DAY generate work orders
WORK_ORDER_CLASSES = {"IMMEDIATE", "60_DAY"}
# 180_DAY goes to scheduled monitoring list
SCHEDULED_CLASSES = {"180_DAY"}
# MONITOR produces no output


def build_outputs(
    enriched: List[Dict[str, Any]],
    verdicts: List[Dict[str, Any]],
    risk_results: List[Dict[str, Any]],
    run_id: str,
    outdir: str | Path,
    llm,
    approvals: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    approvals = approvals or {}
    by_enrich = {str(r.get("anomaly_id")): r for r in enriched}
    by_risk = {r["anomaly_id"]: r for r in risk_results}

    work_orders: List[Dict[str, Any]] = []
    scheduled_monitoring: List[Dict[str, Any]] = []
    notifs: List[Dict[str, Any]] = []

    for v in verdicts:
        aid = v["anomaly_id"]
        r = by_enrich.get(aid, {})
        final = v["final_class"]

        # Status: IMMEDIATE needs human approval; others auto-approved (headless = AUTO_APPROVED_HEADLESS)
        if final == "IMMEDIATE":
            status = "PENDING_APPROVAL"
        else:
            status = "AUTO_APPROVED"
        if aid in approvals:
            status = approvals[aid]

        due = (date.today() + timedelta(days=DUE[final])).isoformat()

        base_record = {
            "anomaly_id": aid,
            "pipeline_id": r.get("pipeline_id"),
            "chainage_m": r.get("chainage_m"),
            "priority": final,
            "recommended_action": ACTION[final],
            "due_date": due,
            "location_detail": f"ch {r.get('chainage_m')}m, clock {r.get('clock_position')}, "
                               f"HCA={r.get('hca')}, road={r.get('near_road')}, water={r.get('near_water')}",
            "status": status,
            "erf": (by_risk.get(aid) or {}).get("erf"),
            "risk_score": (by_risk.get(aid) or {}).get("risk_score"),
        }

        # Work order ID is used for notifications even for non-work-order classes
        work_order_id = f"WO-{run_id}-{aid}"

        if final in WORK_ORDER_CLASSES:
            wo = {"work_order_id": work_order_id, **base_record}
            work_orders.append(wo)
        elif final in SCHEDULED_CLASSES:
            scheduled_monitoring.append(base_record)

        # Notifications for all non-MONITOR
        if final != "MONITOR":
            notifs.append({
                "channel": "email" if final == "IMMEDIATE" else "slack",
                "to": "integrity-team@operator.example" if final == "IMMEDIATE" else "#integrity-ops",
                "subject": f"[{final}] {aid} on {r.get('pipeline_id')} @ {r.get('chainage_m')}m",
                "body": llm_text(llm, f"[WORKORDER]\nwork_order_id={work_order_id}\n"
                                      f"anomaly_id={aid}\npipeline_id={r.get('pipeline_id')}\n"
                                      f"chainage={r.get('chainage_m')}\npriority={final}\n"
                                      f"action={ACTION[final]}\ndue={due}"),
                "simulated": True
            })

    import csv

    # Work orders CSV
    wo_path = outdir / f"work_orders_{run_id}.csv"
    with open(wo_path, "w", newline="") as f:
        fieldnames = ["work_order_id", "anomaly_id", "pipeline_id", "chainage_m", "priority",
                      "recommended_action", "due_date", "location_detail", "status", "erf", "risk_score"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(work_orders)

    # Scheduled monitoring CSV (180_DAY items)
    sched_path = outdir / f"scheduled_monitoring_{run_id}.csv"
    with open(sched_path, "w", newline="") as f:
        fieldnames = ["anomaly_id", "pipeline_id", "chainage_m", "priority",
                      "recommended_action", "due_date", "location_detail", "status", "erf", "risk_score"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(scheduled_monitoring)

    import json
    notif_path = outdir / f"notifications_{run_id}.json"
    notif_path.write_text(json.dumps(notifs, indent=2))

    md_path = outdir / f"summary_{run_id}.md"
    md_path.write_text(_summary_md(run_id, verdicts, work_orders, scheduled_monitoring, llm))

    return {
        "work_orders_csv": str(wo_path),
        "scheduled_monitoring_csv": str(sched_path),
        "notifications_json": str(notif_path),
        "summary_md": str(md_path),
        "n_work_orders": len(work_orders),
        "n_scheduled": len(scheduled_monitoring),
    }


def _summary_md(run_id: str, verdicts: List[Dict], work_orders: List[Dict], scheduled: List[Dict], llm) -> str:
    from collections import Counter

    br = Counter(v["final_class"] for v in verdicts)
    ch = sum(1 for v in verdicts if v["verdict"] != "AGREE")
    up = sum(1 for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED")
    es = sum(1 for v in verdicts if v.get("escalated"))
    mc = sum(1 for v in verdicts if v.get("missed_critical"))
    imm = br.get("IMMEDIATE", 0)
    head = llm_text(llm, f"[SUMMARY]\nrun_id={run_id}\nn_total={len(verdicts)}\n"
                          f"breakdown={dict(br)}\nn_challenged={ch}\nn_upgraded={up}\n"
                          f"n_escalated={es}\nn_missed_caught={mc}\nn_immediate={imm}")
    lines = [f"# CorrosionGuard run {run_id} — engineer summary", "", head, "",
             "## Class breakdown", ""]
    for k in ("IMMEDIATE", "60_DAY", "180_DAY", "MONITOR"):
        lines.append(f"- {k}: {br.get(k, 0)}")
    lines += ["", "## Work orders generated (IMMEDIATE + 60_DAY)", ""]
    for o in work_orders:
        lines.append(f"- {o['work_order_id']}: {o['anomaly_id']} ch {o['chainage_m']}m due {o['due_date']} [{o['status']}]")
    lines += ["", "## Scheduled monitoring (180_DAY)", ""]
    for s in scheduled:
        lines.append(f"- {s['anomaly_id']} ch {s['chainage_m']}m due {s['due_date']} [{s['status']}]")
    return "\n".join(lines) + "\n"