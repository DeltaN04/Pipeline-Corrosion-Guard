"""Planner Agent: explicit task plan + routing. Plan is visible in the UI."""
from __future__ import annotations

from typing import Any, Dict


def build_plan(request: str, n_anomalies: int, llm) -> Dict[str, Any]:
    routing = "large_batch" if n_anomalies > 500 else "small_batch"
    deep_checks = True  # always on for PoC; planner may disable for huge batches
    tasks = [
        {"order": 1, "task": "Validate + enrich anomalies (metadata, growth, HCA, neighbours, quality)", "owner": "research", "tools": "lookup, clustering, quality"},
        {"order": 2, "task": "Compute B31G safe pressure, ERF, projection, risk score and triage class", "owner": "executor", "tools": "b31g, risk"},
        {"order": 3, "task": "Independently re-screen, compare vs executor + legacy, verdict AGREE/UPGRADE/DOWNGRADE", "owner": "critic", "tools": "full_screen_class, note_keywords"},
        {"order": 4, "task": "Loop-back to executor with critic constraints (max 2 iterations), else escalate severe", "owner": "orchestrator", "tools": "graph_router"},
        {"order": 5, "task": "Human approval gate for IMMEDIATE items", "owner": "human", "tools": "streamlit_gate"},
        {"order": 6, "task": "Generate work orders, summary report, notification payloads", "owner": "automation", "tools": "writers"},
    ]
    text = llm.render(f"[PLAN]\nrequest={request}\nn_anomalies={n_anomalies}\nrouting={routing}")
    return {"request": request, "tasks": tasks, "routing": routing, "deep_checks": deep_checks, "narrative": text}
