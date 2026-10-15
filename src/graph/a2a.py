"""A2A message bus + Agent Cards."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


class MessageBus:
    """Lightweight in-process A2A bus. Every inter-agent handoff goes through send()."""

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or uuid.uuid4().hex[:8]
        self.messages: List[Dict[str, Any]] = []

    def send(self, sender: str, receiver: str, intent: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        msg = {
            "trace_id": self.trace_id,
            "sender": sender,
            "receiver": receiver,
            "intent": intent,
            "payload": payload or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.messages.append(msg)
        return msg

    def history(self) -> List[Dict[str, Any]]:
        return list(self.messages)


AGENT_CARDS = {
    "planner": {
        "name": "Planner Agent",
        "capabilities": ["parse run request", "produce ordered task plan", "select routing small/large batch", "toggle deep checks"],
        "inputs": ["user request string", "anomaly count"],
        "outputs": ["TaskPlan (ordered tasks, owner, tools)", "routing decision"],
        "tools": ["mock_llm.plan"],
    },
    "research": {
        "name": "Research Agent",
        "capabilities": ["pipeline metadata lookup", "growth-rate computation", "HCA/location confirmation", "nearby-feature lookup", "interaction clustering", "data-quality validation", "inspector-note keyword scan"],
        "inputs": ["raw anomaly rows"],
        "outputs": ["enriched records (growth, interaction, flags, quality)"],
        "tools": ["lookup.pipeline_metadata", "lookup.growth_rate", "lookup.hca_lookup", "lookup.nearby_features", "clustering.find_interactions", "quality.validate_record"],
    },
    "executor": {
        "name": "Executor Agent (Risk Engine)",
        "capabilities": ["B31G safe-pressure calc", "ERF calc", "growth projection", "weighted risk score", "numbers-only triage"],
        "inputs": ["enriched records (+ optional critic constraints on rework)"],
        "outputs": ["RiskResult per anomaly with tool trace"],
        "tools": ["b31g.safe_pressure_mpa", "b31g.erf", "risk.project_depth", "risk.risk_score", "risk.executor_triage", "mock_llm.rationale"],
    },
    "critic": {
        "name": "Critic Agent (Independent Validator)",
        "capabilities": ["independent rule-based re-screen", "note-vs-number contradiction check", "legacy-label comparison", "AGREE/DOWNGRADE/UPGRADE verdicts", "missed-critical flagging", "escalation"],
        "inputs": ["enriched records", "executor RiskResults", "legacy labels"],
        "outputs": ["CriticVerdict per anomaly incl. final_class"],
        "tools": ["risk.full_screen_class", "lookup.note_keywords", "mock_llm.critic_objection"],
    },
    "automation": {
        "name": "Business Automation Agent",
        "capabilities": ["work-order generation", "due-date by class", "engineer summary report", "simulated notification payloads to disk"],
        "inputs": ["final classes + human approvals"],
        "outputs": ["work orders CSV", "summary .md", "notifications log"],
        "tools": ["report writers", "mock_llm.summary"],
    },
}
