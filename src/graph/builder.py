"""LangGraph orchestration: Planner -> Research -> Executor -> Critic -> router.

Router: UPGRADE_REQUIRED/disagreement -> Executor (max 2 iterations, then escalate
to the more severe class marked ESCALATED) -> else finalize (human gate + automation).

Per-iteration tracking: objected, resolved, remaining.
Rework only re-executes objected anomalies.
"""
from __future__ import annotations

from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from src.agents import automation as auto_agent
from src.agents import critic as critic_agent
from src.agents import executor as exec_agent
from src.agents import planner as planner_agent
from src.agents import research as research_agent
from src.graph.a2a import MessageBus
from src.graph.state import CGState
from src.llm.provider import get_chat_model
from src.schemas.models import CriticVerdict, EnrichedAnomaly, RiskResult, TaskPlan, WorkOrder
from src.tools import risk as risk_tools

MAX_ITERS = 2
SEV = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}


def _validate_outputs(model_class, items: List[Dict[str, Any]], state: CGState, agent_name: str) -> List[Dict[str, Any]]:
    """Validate a list of outputs against a Pydantic model.
    
    On validation failure: log to state["validation_errors"], quarantine the record, continue.
    Returns validated items (with invalid ones replaced by quarantine records).
    """
    validated = []
    errors = list(state.get("validation_errors", []))
    for i, item in enumerate(items):
        try:
            validated_model = model_class(**item)
            validated.append(validated_model.model_dump())
        except ValidationError as e:
            error_info = {
                "agent": agent_name,
                "index": i,
                "anomaly_id": item.get("anomaly_id", f"unknown_{i}"),
                "errors": e.errors(),
            }
            errors.append(error_info)
            # Create quarantine record
            quarantine = item.copy()
            quarantine["_validation_quarantined"] = True
            quarantine["_validation_errors"] = e.errors()
            validated.append(quarantine)
    if errors != state.get("validation_errors", []):
        state["validation_errors"] = errors
    return validated


def _bus(state: CGState) -> MessageBus:
    b = MessageBus(trace_id=state.get("trace_id", "trace"))
    b.messages = list(state.get("messages", []))
    return b


def n_planner(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    n_anomalies = len(state.get("anomalies", []))
    dirty_estimate = sum(1 for a in state.get("anomalies", []) if any(
        v is None or (isinstance(v, float) and v != v) or (isinstance(v, (int, float)) and v < 0)
        for v in a.values()
    ))
    plan = planner_agent.build_plan(state.get("request", "Triage ILI run"), n_anomalies, dirty_estimate, llm)
    # Validate plan
    try:
        TaskPlan(**plan)
    except ValidationError as e:
        errors = list(state.get("validation_errors", []))
        errors.append({"agent": "planner", "index": 0, "anomaly_id": "plan", "errors": e.errors()})
        state["validation_errors"] = errors
    b = _bus(state)
    b.send("user", "planner", "TRIAGE_REQUEST", {"request": plan["request"]})
    b.send("planner", "research", "TASK_PLAN", {"tasks": plan["tasks"], "routing": plan["routing"]})
    return {"plan": plan, "iteration": 0, "messages": b.messages, "trace_id": b.trace_id,
            "rework_stats": {"history": []}}


def n_research(state: CGState) -> Dict[str, Any]:
    enriched = research_agent.enrich(state.get("anomalies", []))
    enriched_validated = _validate_outputs(EnrichedAnomaly, enriched, state, "research")
    b = _bus(state)
    b.send("research", "executor", "ENRICHED_BATCH",
           {"n": len(enriched_validated), "interacting": sum(1 for r in enriched_validated if r.get("interacting")),
            "dirty": sum(1 for r in enriched_validated if r.get("quality_flags"))})
    return {"enriched": enriched_validated, "messages": b.messages}


def n_executor(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    it = state.get("iteration", 0) or 0
    is_rework = it > 0

    # Preserve iteration-0 executor classes for ablation metrics.
    # Snapshot the first-pass classes before any rework/critic overwrite them.
    if is_rework:
        executor_class_initial = dict(state.get("executor_class_initial", {}))
    else:
        executor_class_initial = {}  # will be populated below after execute

    # On rework, only re-execute anomalies that the critic objected to
    if is_rework:
        objected_ids = {o["anomaly_id"] for o in state.get("critic_objections", []) or []}
        enriched_all = state.get("enriched", []) or []
        # Split into objected and non-objected
        to_reexecute = [r for r in enriched_all if r["anomaly_id"] in objected_ids]
        others = [r for r in enriched_all if r["anomaly_id"] not in objected_ids]

        # Build constraints from objections
        cons: Dict[str, Dict[str, Any]] = {}
        for o in state.get("critic_objections", []) or []:
            cons[o["anomaly_id"]] = o.get("constraints", {})

        # Re-execute only objected anomalies with conservative mode
        new_results = exec_agent.execute(to_reexecute, llm, cons, is_rework=True)

        # Merge with previous results for non-objected
        old_results = state.get("risk_results", []) or []
        old_by_id = {r["anomaly_id"]: r for r in old_results}
        merged_results = []
        for r in enriched_all:
            aid = r["anomaly_id"]
            if aid in objected_ids:
                # Find new result
                nr = next((nr for nr in new_results if nr["anomaly_id"] == aid), None)
                if nr:
                    merged_results.append(nr)
                else:
                    merged_results.append(old_by_id.get(aid, {}))
            else:
                merged_results.append(old_by_id.get(aid, {}))
        results = merged_results
    else:
        # First pass: execute all
        results = exec_agent.execute(state.get("enriched", []), llm, None, is_rework=False)

    results_validated = _validate_outputs(RiskResult, results, state, "executor")

    # After first-pass execute, snapshot executor classes for ablation
    if not is_rework and results_validated:
        executor_class_initial = {r["anomaly_id"]: r["triage_class"] for r in results_validated if "anomaly_id" in r}

    b = _bus(state)
    b.send("executor", "critic", "RISK_RESULTS",
           {"n": len(results_validated), "iteration": it,
            "immediate": sum(1 for r in results_validated if r["triage_class"] == "IMMEDIATE")})
    return {"risk_results": results_validated, "messages": b.messages,
            "executor_class_initial": executor_class_initial}


def n_critic(state: CGState) -> Dict[str, Any]:
    llm = get_chat_model()
    verdicts, objections = critic_agent.review(state.get("enriched", []), state.get("risk_results", []), llm)

    # Track which objections were resolved this iteration
    it = state.get("iteration", 0) or 0
    if it > 0:
        # Compare new executor class vs critic screen class for objected items
        objected_ids = {o["anomaly_id"] for o in state.get("critic_objections", []) or []}
        by_risk = {r["anomaly_id"]: r for r in state.get("risk_results", []) or []}
        resolved = 0
        resolved_ids = []
        for v in verdicts:
            if v["anomaly_id"] in objected_ids:
                ex_cls = v.get("executor_class")
                sc_cls = v.get("critic_screen_class")
                if ex_cls and sc_cls and SEV.get(ex_cls, 0) >= SEV.get(sc_cls, 0):
                    resolved += 1
                    resolved_ids.append(v["anomaly_id"])
        remaining = len(objected_ids) - resolved
    else:
        resolved = 0
        resolved_ids = []
        remaining = sum(1 for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED")

    # Record iteration stats
    rework_stats = dict(state.get("rework_stats", {}))
    history = rework_stats.get("history", [])
    # Track all objection IDs ever raised
    all_objection_ids = set(rework_stats.get("all_objection_ids", []))
    for o in objections:
        all_objection_ids.add(o["anomaly_id"])
    history.append({
        "iteration": it,
        "objected": sum(1 for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED"),
        "resolved": resolved,
        "resolved_ids": resolved_ids,
        "remaining": remaining,
    })
    rework_stats["history"] = history
    rework_stats["all_objection_ids"] = list(all_objection_ids)

    b = _bus(state)
    n_up = sum(1 for v in verdicts if v["verdict"] == "UPGRADE_REQUIRED")
    b.send("critic", "orchestrator", "CRITIC_VERDICTS",
           {"n_upgrades": n_up, "n_missed": sum(1 for v in verdicts if v.get("missed_critical")),
            "resolved_this_iter": resolved, "remaining": remaining})
    if n_up:
        b.send("critic", "executor", "OBJECTION",
               {"objections": [{"anomaly_id": o["anomaly_id"], "reasons": o["reasons"]} for o in objections[:5]],
                "note": f"{n_up} upgrade(s) demanded; showing first 5"})
    verdicts_validated = _validate_outputs(CriticVerdict, verdicts, state, "critic")
    return {"verdicts": verdicts_validated, "critic_objections": objections, "messages": b.messages,
            "rework_stats": rework_stats}


def router(state: CGState) -> str:
    verdicts = state.get("verdicts", []) or []
    it = state.get("iteration", 0) or 0
    need = any(v["verdict"] == "UPGRADE_REQUIRED" for v in verdicts)
    if need and it < MAX_ITERS:
        return "rework"
    return "finalize"


def n_rework(state: CGState) -> Dict[str, Any]:
    b = _bus(state)
    it = state.get("iteration", 0) or 0
    objected = sum(1 for v in state.get("verdicts", []) if v["verdict"] == "UPGRADE_REQUIRED")
    b.send("orchestrator", "executor", "REWORK",
           {"iteration": it + 1, "objected_anomalies": objected})
    return {"iteration": it + 1, "messages": b.messages}


def n_finalize(state: CGState) -> Dict[str, Any]:
    """Clean finalize: mark RESOLVED where executor >= critic screen, ESCALATE the rest."""
    verdicts = [dict(v) for v in state.get("verdicts", []) or []]
    by_risk = {r["anomaly_id"]: r for r in state.get("risk_results", []) or []}
    it = state.get("iteration", 0) or 0
    escalated: list[str] = []
    resolved_on_rework: list[str] = []

    # Iteration-0 executor classes (pre-Critic) for ablation — never overwritten now.
    executor_class_initial = dict(state.get("executor_class_initial", {}))
    # Post-rework executor classes for the "after rework" ablation row.
    executor_after_rework = {r["anomaly_id"]: r["triage_class"]
                             for r in (state.get("risk_results", []) or []) if "anomaly_id" in r}

    # Use tracked objection IDs from rework stats
    rework_stats = dict(state.get("rework_stats", {}))
    all_objection_ids = set(rework_stats.get("all_objection_ids", []))

    # For each anomaly that ever had an objection, check if it was resolved
    for aid in all_objection_ids:
        v = next((v for v in verdicts if v["anomaly_id"] == aid), None)
        if not v:
            continue
        ex_cls = by_risk.get(aid, {}).get("triage_class", v.get("executor_class"))
        sc_cls = v.get("critic_screen_class")
        if SEV.get(ex_cls, 0) >= SEV.get(sc_cls, 0):
            # Resolved on rework
            if v["verdict"] == "UPGRADE_REQUIRED":
                # Do NOT overwrite v["executor_class"] — keep iteration-0 value for ablation.
                v["final_class"] = ex_cls
                v["verdict"] = "AGREE"
                v["reasons"] = [f"converged on rework iteration {it}: executor adopted conservative assumptions"] + v["reasons"]
            resolved_on_rework.append(aid)
        else:
            # Escalate to more severe
            if v["verdict"] == "UPGRADE_REQUIRED":
                v["final_class"] = ex_cls if SEV[ex_cls] >= SEV[sc_cls] else sc_cls
                v["escalated"] = True
                v["reasons"] = [f"ESCALATED after {it} iterations: forced to more severe of executor={ex_cls}, critic={sc_cls}"] + v["reasons"]
                escalated.append(aid)

    # For verdicts that never had objections
    for v in verdicts:
        if v["anomaly_id"] not in all_objection_ids:
            if v["verdict"] in ("AGREE", "DOWNGRADE_RISK"):
                v["final_class"] = v["executor_class"]
            elif v["verdict"] == "UPGRADE_REQUIRED":
                # Shouldn't happen, but handle it
                ex_cls = by_risk.get(v["anomaly_id"], {}).get("triage_class", v["executor_class"])
                sc_cls = v["critic_screen_class"]
                if SEV.get(ex_cls, 0) >= SEV.get(sc_cls, 0):
                    v["final_class"] = ex_cls
                    v["verdict"] = "AGREE"
                    resolved_on_rework.append(v["anomaly_id"])
                else:
                    v["final_class"] = ex_cls if SEV[ex_cls] >= SEV[sc_cls] else sc_cls
                    v["escalated"] = True
                    v["reasons"] = [f"ESCALATED after {it} iterations: forced to more severe of executor={ex_cls}, critic={sc_cls}"] + v["reasons"]
                    escalated.append(v["anomaly_id"])

    rework_stats["resolved_on_rework"] = len(resolved_on_rework)
    rework_stats["escalated"] = len(escalated)

    # HONOR THE CRITIC: final_class is never below the Critic's screen class,
    # for every anomaly — including those marked "resolved on rework".
    for v in verdicts:
        ex_cls = by_risk.get(v["anomaly_id"], {}).get("triage_class", v.get("executor_class"))
        sc_cls = v.get("critic_screen_class", "MONITOR")
        v["final_class"] = ex_cls if SEV.get(ex_cls, 0) >= SEV.get(sc_cls, 0) else sc_cls

    llm = get_chat_model()
    by_enrich = {str(r.get("anomaly_id")): r for r in state.get("enriched", []) or []}
    approvals = dict(state.get("human_decisions", {}) or {})
    for v in verdicts:
        if v["final_class"] == "IMMEDIATE" and v["anomaly_id"] not in approvals:
            approvals[v["anomaly_id"]] = "AUTO_APPROVED_HEADLESS"
    outputs = auto_agent.build_outputs(
        state.get("enriched", []) or [], verdicts, state.get("risk_results", []) or [],
        (state.get("trace_id", "run") or "run"), "outputs", llm, approvals)

    ground_truth = state.get("ground_truth", {})
    metrics = _metrics(ground_truth, verdicts, by_enrich,
                       executor_class_initial=executor_class_initial,
                       executor_after_rework=executor_after_rework)
    metrics["rework_stats"] = rework_stats
    metrics["executor_class_initial_map"] = executor_class_initial
    metrics["executor_after_rework_map"] = executor_after_rework

    b = _bus(state)
    b.send("automation", "user", "RUN_COMPLETE", {"n_work_orders": outputs["n_work_orders"], "n_scheduled": outputs["n_scheduled"], "metrics": metrics})
    return {"verdicts": verdicts, "escalated_ids": escalated, "human_decisions": approvals,
            "outputs": outputs, "metrics": metrics, "messages": b.messages,
            "rework_stats": rework_stats}


def _metrics(
    ground_truth: Dict[str, str],
    verdicts,
    by_enrich,
    executor_class_initial: Dict[str, str] | None = None,
    executor_after_rework: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    from collections import Counter

    truth = ground_truth
    if not truth:
        return {}

    def critical(c: str) -> bool:
        return c in ("IMMEDIATE", "60_DAY")

    pred_maps = [
        ("legacy", {a: by_enrich.get(a, {}).get("legacy_manual_label") for a in truth}),
        ("executor_only", executor_class_initial or {}),
        ("executor_after_rework", executor_after_rework or {}),
        ("critic_screen", {v["anomaly_id"]: v.get("critic_screen_class", "MONITOR") for v in verdicts}),
        ("final", {v["anomaly_id"]: v["final_class"] for v in verdicts}),
    ]

    out: Dict[str, Any] = {}
    for name, pred_map in pred_maps:
        tp = sum(1 for a, t in truth.items() if critical(t) and critical(pred_map.get(a, "MONITOR")))
        fp = sum(1 for a, t in truth.items() if not critical(t) and critical(pred_map.get(a, "MONITOR")))
        fn = sum(1 for a, t in truth.items() if critical(t) and not critical(pred_map.get(a, "MONITOR")))
        out[name] = {"recall_critical": round(tp / max(1, tp + fn), 3),
                     "precision_critical": round(tp / max(1, tp + fp), 3), "tp": tp, "fp": fp, "fn": fn}
    out["confusion_final"] = {f"{k[0]}->{k[1]}": v for k, v in
                              Counter((truth[v["anomaly_id"]], v["final_class"]) for v in verdicts if v["anomaly_id"] in truth).items()}

    # Redefined: missed_catch = truth critical AND legacy below critical AND final critical
    # False alarm = legacy below critical AND final critical AND truth NOT critical
    missed_caught = 0
    false_alarms = 0
    for a, t in truth.items():
        legacy_label = by_enrich.get(a, {}).get("legacy_manual_label")
        final_class = next((v["final_class"] for v in verdicts if v["anomaly_id"] == a), "MONITOR")
        legacy_critical = critical(legacy_label) if legacy_label else False
        truth_critical = critical(t)
        final_critical = critical(final_class)
        if truth_critical and not legacy_critical and final_critical:
            missed_caught += 1
        elif not truth_critical and not legacy_critical and final_critical:
            false_alarms += 1

    out["missed_caught"] = missed_caught
    out["false_alarms"] = false_alarms
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