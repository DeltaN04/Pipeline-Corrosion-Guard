"""Planner Agent: explicit task plan + routing. Plan is visible in the UI."""
from __future__ import annotations

from typing import Any, Dict, List

from src.llm.provider import llm_text


def build_plan(request: str, n_anomalies: int, dirty_estimate: int, llm) -> Dict[str, Any]:
    """Build dynamic task plan based on data characteristics.

    Args:
        request: User request string
        n_anomalies: Number of anomalies to process
        dirty_estimate: Estimated count of dirty/malformed records
        llm: LLM for narrative generation
    """
    # Dynamic routing
    routing = "large_batch" if n_anomalies > 500 else "small_batch"
    deep_checks = n_anomalies <= 1000  # disable deep checks for very large batches

    # Base tasks
    tasks: List[Dict[str, Any]] = [
        {"order": 1, "task": "Validate + enrich anomalies (metadata, growth, HCA, neighbours, quality)", "owner": "research", "tools": "lookup, clustering, quality"},
        {"order": 2, "task": "Compute B31G safe pressure, ERF, projection, risk score and triage class", "owner": "executor", "tools": "b31g, risk"},
        {"order": 3, "task": "Independently re-screen, compare vs executor + legacy, verdict AGREE/UPGRADE/DOWNGRADE", "owner": "critic", "tools": "full_screen_class, note_keywords"},
        {"order": 4, "task": "Loop-back to executor with critic constraints (max 2 iterations), else escalate severe", "owner": "orchestrator", "tools": "graph_router"},
        {"order": 5, "task": "Human approval gate for IMMEDIATE items", "owner": "human", "tools": "streamlit_gate"},
        {"order": 6, "task": "Generate work orders, summary report, notification payloads", "owner": "automation", "tools": "writers"},
    ]

    # Add quarantine task if dirty records detected
    if dirty_estimate > 0:
        tasks.insert(1, {"order": 1.5, "task": f"Quarantine {dirty_estimate} dirty/malformed records for conservative review", "owner": "research", "tools": "quality.validate_record"})

    # Large batch: process in chunks
    if routing == "large_batch":
        tasks[0]["task"] = "Validate + enrich anomalies in chunks (metadata, growth, HCA, neighbours, quality)"
        tasks[1]["task"] = "Compute B31G safe pressure, ERF, projection, risk score and triage class (chunked)"
        tasks[2]["task"] = "Independently re-screen, compare vs executor + legacy, verdict AGREE/UPGRADE/DOWNGRADE (chunked)"

    text = llm_text(llm, f"[PLAN]\nrequest={request}\nn_anomalies={n_anomalies}\ndirty_estimate={dirty_estimate}\nrouting={routing}")
    return {"request": request, "tasks": tasks, "routing": routing, "deep_checks": deep_checks, "dirty_estimate": dirty_estimate, "narrative": text}