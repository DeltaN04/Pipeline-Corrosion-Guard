"""LangGraph orchestration: Planner -> Research -> Executor -> Critic -> router.

Router: UPGRADE_REQUIRED/disagreement -> Executor (max 2 iterations, then escalate
to the more severe class marked ESCALATED) -> else finalize (human gate + automation).
"""
from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.agents import automation as auto_agent
from src.agents import critic as critic_agent
from src.agents import executor as exec_agent
from src.agents import planner as planner_agent
from src.agents import research as research_agent
from src.graph.a2a import MessageBus
from src.graph.state import CGState
from src.llm.provider import get_chat_model
from src.tools import risk as risk_tools

MAX_ITERS = 2
SEV = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}


def _bus(state: CGState) -> MessageBus:
    b = MessageBus(trace_id=state.get("trace_id", "trace"))
    b.messages = list(state.get("messages", []))
    return b


def n_planner(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    plan = planner_agent.build_plan(state.get("request", "Triage ILI run"), len(state.get("anomalies", [])), llm)
    b = _bus(state)
    b.send("user", "planner", "TRIAGE_REQUEST", {"request": plan["request"]})
    b.send("planner", "research", "TASK_PLAN", {"tasks": plan["tasks"], "routing": plan["routing"]})
    return {"plan": plan, "iteration": 0, "messages": b.messages, "trace_id": b.trace_id}


def n_research(state: CGState) -> Dict[str, Any]:
    enriched = research_agent.enrich(state.get("anomalies", []))
    b = _bus(state)
    b.send("research", "executor", "ENRICHED_BATCH",
           {"n": len(enriched), "interacting": sum(1 for r in enriched if r.get("interacting")),
            "dirty": sum(1 for r in enriched if r.get("quality_flags"))})
    return {"enriched": enriched, "messages": b.messages}


def n_executor(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    cons: Dict[str, Dict[str, Any]] = {}
    for o in state.get("critic_objections", []) or []:
        cons[o["anomaly_id"]] = o.get("constraints", {})
    results = exec_agent.execute(state.get("enriched", []), llm, cons if state.get("iteration", 0) > 0 else None)
    b = _bus(state)
    b.send("executor", "critic", "RISK_RESULTS",
           {"n": len(results), "iteration": state.get("iteration", 0),
            "immediate": sum(1 for r in results if r["triage_class"] == "IMMEDIATE")})
    return {"risk_results": results, "messages": b.messages}


def n_critic(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    verdicts, objections = critic_agent.review(state.get("enriched", []), state.get("risk_results", []), llm)
    b = _bus(state)
    n_up = sum(1 for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED")
    b.send("critic", "orchestrator", "CRITIC_VERDICTS",
           {"n_upgrades": n_up, "n_missed": sum(1 for v in verdicts if v.get("missed_critical"))})
    if n_up:
        b.send("critic", "executor", "OBJECTION",
               {"objections": [{"anomaly_id": o["anomaly_id"], "reasons": o["reasons"]} for o in objections[:5]],
                "note": f"{n_up} upgrade(s) demanded; showing first 5"})
    return {"verdicts": verdicts, "critic_objections": objections, "messages": b.messages}


def router(state: CGState) -> str:
    verdicts = state.get("verdicts", []) or []
    it = state.get("iteration", 0) or 0
    need = any(v["verdict"] == "UPGRADE_REQUIRED" for v in verdicts)
    if need and it < MAX_ITERS:
        return "rework"
    return "finalize"


def n_rework(state: CGState) -> Dict[str, Any]:
    b = _bus(state)
    b.send("orchestrator", "executor", "REWORK",
           {"iteration": state.get("iteration", 0) + 1, "constraints": len(state.get("critic_objections", []) or [])})
    return {"iteration": state.get("iteration", 0) + 1, "messages": b.messages}


def n_finalize(state: CGState) -> Dict[str, Any]:
    """Apply escalation for still-unresolved upgrades, then run automation (auto-approve headless)."""
    verdicts = [dict(v) for v in state.get("verdicts", []) or []]
    by_risk = {r["anomaly_id"]: r for r in state.get("risk_results", []) or []}
    it = state.get("iteration", 0) or 0
    escalated: list[str] = list(state.get("escalated_ids", []) or [])
    still = [v for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED"]
    if still and it >= MAX_ITERS:
        # Force the more severe option and mark ESCALATED.
        for v in verdicts:
            if v["verdict"] == "UPGRADE_REQUIRED":
                ex, sc = v["executor_class"], v["critic_screen_class"]
                v["final_class"] = ex if SEV[ex] >= SEV[sc] else sc
                v["escalated"] = True
                v["reasons"] = [f"ESCALATED after {it} iterations: forced to more severe of executor={ex}, critic={sc}"] + v["reasons"]
                escalated.append(v["anomaly_id"])
    elif still:
        # Converged rework path: executor re-ran with constraints; accept critic screen where it demanded upgrade.
        for v in verdicts:
            if v["verdict"] == "UPGRADE_REQUIRED":
                ex_risk = by_risk.get(v["anomaly_id"], {})
                # Re-executor output already reflects constraints; if it now matches/agrees severity, take it.
                new_cls = ex_risk.get("triage_class", v["executor_class"])
                v["executor_class"] = new_cls
                if SEV[new_cls] >= SEV[v["critic_screen_class"]]:
                    v["final_class"] = new_cls
                    v["verdict"] = "AGREE"
                    v["reasons"] = ["rework converged: executor adopted conservative assumptions"] + v["reasons"]
                else:
                    v["final_class"] = v["critic_screen_class"]
                    v["escalated"] = True
                    v["reasons"] = ["ESCALATED: executor still below critic screen; forced severe"] + v["reasons"]
                    escalated.append(v["anomaly_id"])
    llm = get_chat_model()
    by_enrich = {str(r.get("anomaly_id")): r for r in state.get("enriched", []) or []}
    # Headless default: approve all IMMEDIATE (UI gate overrides per-item).
    approvals = dict(state.get("human_decisions", {}) or {})
    for v in verdicts:
        if v["final_class"] == "IMMEDIATE" and v["anomaly_id"] not in approvals:
            approvals[v["anomaly_id"]] = "APPROVED"
    outputs = auto_agent.build_outputs(
        state.get("enriched", []) or [], verdicts, state.get("risk_results", []) or [],
        (state.get("trace_id", "run") or "run"), "outputs", llm, approvals)
    # Metrics vs ground truth carried on enriched rows (true_class column when present).
    metrics = _metrics(state.get("enriched", []) or [], verdicts, by_enrich)
    b = _bus(state)
    b.send("automation", "user", "RUN_COMPLETE", {"n_orders": outputs["n_orders"], "metrics": metrics})
    return {"verdicts": verdicts, "escalated_ids": escalated, "human_decisions": approvals,
            "outputs": outputs, "metrics": metrics, "messages": b.messages}


def _metrics(enriched, verdicts, by_enrich) -> Dict[str, Any]:
    from collections import Counter

    truth = {str(r.get("anomaly_id")): r.get("true_class") for r in enriched if r.get("true_class")}
    if not truth:
        return {}

    def critical(c: str) -> bool:
        return c in ("IMMEDIATE", "60_DAY")

    out: Dict[str, Any] = {}
    for name, pred_map in (
        ("legacy", {a: (by_enrich.get(a, {}).get("legacy_manual_label")) for a in truth}),
        ("executor", {v["anomaly_id"]: v["executor_class"] for v in verdicts}),
        ("final", {v["anomaly_id"]: v["final_class"] for v in verdicts}),
    ):
        tp = sum(1 for a, t in truth.items() if critical(t) and critical(pred_map.get(a, "MONITOR")))
        fp = sum(1 for a, t in truth.items() if not critical(t) and critical(pred_map.get(a, "MONITOR")))
        fn = sum(1 for a, t in truth.items() if critical(t) and not critical(pred_map.get(a, "MONITOR")))
        out[name] = {"recall_critical": round(tp / max(1, tp + fn), 3),
                     "precision_critical": round(tp / max(1, tp + fp), 3), "tp": tp, "fp": fp, "fn": fn}
    out["confusion_final"] = {f"{k[0]}->{k[1]}": v for k, v in
                              Counter((truth[v["anomaly_id"]], v["final_class"]) for v in verdicts if v["anomaly_id"] in truth).items()}
    out["missed_caught"] = sum(1 for v in verdicts if v.get("missed_critical") and critical(v["final_class"]))
    out["n_total"] = len(truth)
    return out


def build_graph():
    g = StateGraph(CGState)
    g.add_node("planner", n_planner)
    g.add_node("research", n_research)
    g.add_node("executor", n_executor)
    g.add_node("critic", n_critic)
    g.add_node("rework", n_rework)
    g.add_node("finalize", n_finalize)
    g.set_entry_point("planner")
    g.add_edge("planner", "research")
    g.add_edge("research", "executor")
    g.add_edge("executor", "critic")
    g.add_conditional_edges("critic", router, {"rework": "rework", "finalize": "finalize"})
    g.add_edge("rework", "executor")
    g.add_edge("finalize", END)
    return g.compile()
