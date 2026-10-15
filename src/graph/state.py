"""Shared LangGraph state (TypedDict)."""
from __future__ import annotations

from typing import Any, Dict, List

from typing_extensions import TypedDict


class CGState(TypedDict, total=False):
    request: str
    trace_id: str
    anomalies: List[Dict[str, Any]]  # raw rows
    plan: Dict[str, Any]
    enriched: List[Dict[str, Any]]
    risk_results: List[Dict[str, Any]]
    verdicts: List[Dict[str, Any]]
    iteration: int
    critic_objections: List[Dict[str, Any]]
    escalated_ids: List[str]
    human_decisions: Dict[str, str]
    outputs: Dict[str, Any]
    messages: List[Dict[str, Any]]
    metrics: Dict[str, Any]
