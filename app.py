"""CorrosionGuard — Agentic AI triage of pipeline corrosion inspection findings.

Run:  pip install -r requirements.txt && streamlit run app.py
Offline: yes (MockChatModel; no network calls anywhere).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agents import automation as auto_agent  # noqa: E402
from src.graph import builder as G  # noqa: E402
from src.graph.a2a import AGENT_CARDS  # noqa: E402
from src.graph.runner import df_to_anomalies  # noqa: E402
from src.llm.provider import LLM_BACKEND, get_chat_model  # noqa: E402

st.set_page_config(page_title="CorrosionGuard", layout="wide",
                   page_icon="🛢️")

DATA_PATH = Path(__file__).resolve().parent / "data" / "ili_anomalies.csv"
SEV_ORDER = ["MONITOR", "180_DAY", "60_DAY", "IMMEDIATE"]

# ---------- session state ----------
for k, v in {"df": None, "result": None, "approvals": {}, "outputs": None, "run_label": "ILI-2026-03"}.items():
    st.session_state.setdefault(k, v)


def load_builtin() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


def severity_class_counts(verdicts, key):
    from collections import Counter

    return Counter(v[key] for v in verdicts)


# ---------- staged run with live trace ----------
def run_with_trace(anomalies, request: str):
    """Drive graph nodes step-by-step so the UI shows planning, tools, critic loop-back."""
    state: dict = {"request": request, "trace_id": __import__("uuid").uuid4().hex[:8],
                   "anomalies": anomalies, "human_decisions": {}}
    trace_log: list[str] = []
    with st.status("🤖 Agents working…", expanded=True) as status:
        st.write("**Planner:** drafting task plan…")
        s = G.n_planner(state); state.update(s)
        trace_log.append(f"plan:{state['plan']['routing']}")
        st.write(f"Plan ready — routing **{state['plan']['routing']}**, {len(state['plan']['tasks'])} tasks.")
        st.write("**Research:** metadata, growth, HCA, neighbours, quality…")
        s = G.n_research(state); state.update(s)
        n_int = sum(1 for r in state["enriched"] if r.get("interacting"))
        n_dirty = sum(1 for r in state["enriched"] if r.get("quality_flags"))
        st.write(f"Enriched {len(state['enriched'])} anomalies — {n_int} interacting, {n_dirty} data-quality flags.")
        st.write("**Executor:** B31G / ERF / risk triage…")
        s = G.n_executor(state); state.update(s)
        st.write("**Critic:** independent re-screen…")
        s = G.n_critic(state); state.update(s)
        n_up = sum(1 for v in state["verdicts"] if v["verdict"] == "UPGRADE_REQUIRED")
        st.write(f"Critic demands **{n_up} upgrade(s)**.")
        while G.router(state) == "rework":
            st.write(f"↩️ Loop-back to Executor with critic constraints (iteration {state.get('iteration', 0) + 1})…")
            s = G.n_rework(state); state.update(s)
            s = G.n_executor(state); state.update(s)
            s = G.n_critic(state); state.update(s)
            n_up = sum(1 for v in state["verdicts"] if v["verdict"] == "UPGRADE_REQUIRED")
            st.write(f"Re-screen: **{n_up} upgrade(s)** remaining.")
        if n_up:
            st.write(f"⚠️ Still unresolved after {state.get('iteration', 0)} iterations → **escalate to more severe class**.")
        st.write("**Automation:** work orders + report + notifications…")
        s = G.n_finalize(state); state.update(s)
        status.update(label="✅ Triage complete", state="complete")
    return state


# ================= Sidebar =================
st.sidebar.title("🛢️ CorrosionGuard")
st.sidebar.caption(f"LLM backend: **{LLM_BACKEND}** (mock, offline, deterministic)")
page = st.sidebar.radio("Navigate",
                        ["1 · Home / Problem", "2 · Data", "3 · Run Agents", "4 · Triage Results",
                         "5 · Critic Findings", "6 · Human Approval & Work Orders",
                         "7 · Validation & Metrics", "8 · Architecture"])

# ================= 1 HOME =================
if page.startswith("1"):
    st.title("CorrosionGuard — Agentic AI for pipeline corrosion triage")
    st.markdown("""
**Problem.** ILI tools report thousands of metal-loss anomalies per run. Engineers manually review
spreadsheets/PDFs, assign priority (Immediate / 60-day / 180-day / Monitor) and schedule digs.
Manual review is slow, inconsistent between engineers, blind to context (growth rate, weld proximity,
road/water crossings, high-consequence areas, interacting anomalies, inspector notes contradicting numbers),
and has no independent second check. Missed critical defects → leaks, ruptures, fines, downtime.

**Agentic answer.** Five agents on a LangGraph state machine triage every anomaly, then an **independent
Critic re-checks everything**, forces rework on disagreements, escalates what won't converge, and only then
asks a human to approve Immediate items before work orders are generated.

| Manual process today | CorrosionGuard |
|---|---|
| Spreadsheet review, engineer judgment varies | Deterministic tools (B31G/ERF/risk) + traceable numbers |
| Context in the engineer's head (or missed) | Research agent: growth, HCA, welds, crossings, interaction, notes |
| No second check | Critic agent with independent rules + loop-back + escalation |
| Digs scheduled by hand | Work orders, report, notifications auto-generated |
| Missed criticals found after incidents | Missed-critical detector vs legacy labels |
""")
    st.info("All data on this page is **synthetic** (seeded generator). Engineering formulas are **simplified educational "
            "approximations — NOT for real integrity decisions.**")

# ================= 2 DATA =================
elif page.startswith("2"):
    st.title("Data — synthetic ILI anomalies")
    up = st.file_uploader("Upload an ILI CSV (same columns as the built-in file), or use built-in synthetic data.",
                          type=["csv"])
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Load built-in synthetic data"):
            st.session_state.df = load_builtin()
    if up is not None:
        st.session_state.df = pd.read_csv(up)
        st.success(f"Uploaded {len(st.session_state.df)} rows.")
    df = st.session_state.df
    if df is None:
        st.warning("No data loaded yet. Click the button above.")
    else:
        st.write(f"**{len(df)} anomalies** · pipelines {sorted(df['pipeline_id'].unique())}")
        st.dataframe(df.head(50), use_container_width=True)
        st.subheader("Quality report (Research-agent rules)")
        from src.tools.quality import validate_record

        flags: dict[str, int] = {}
        dirty = 0
        for _, r in df.iterrows():
            f = validate_record(r.to_dict())
            if f:
                dirty += 1
            for x in f:
                flags[x.split(':')[0] + ':' + x.split(':')[1] if ':' in x else x] = \
                    flags.get(x.split(':')[0] + ':' + x.split(':')[1] if ':' in x else x, 0) + 1
        st.metric("Records with quality flags", dirty)
        if flags:
            st.bar_chart(pd.Series(flags).sort_values(ascending=False))
        if "true_class" in df.columns:
            st.caption("Ground-truth + legacy-label distributions (built-in file only)")
            st.bar_chart(pd.DataFrame({"true": df["true_class"].value_counts(),
                                       "legacy": df["legacy_manual_label"].value_counts()}))

# ================= 3 RUN =================
elif page.startswith("3"):
    st.title("Run Agents — live triage")
    if st.session_state.df is None:
        st.session_state.df = load_builtin()
    df = st.session_state.df
    pids = ["ALL"] + sorted(df["pipeline_id"].unique())
    sel = st.selectbox("Pipeline / run scope", pids)
    st.session_state.run_label = st.text_input("Run ID", st.session_state.run_label)
    if st.button("▶ Run Triage", type="primary"):
        sub = df if sel == "ALL" else df[df.pipeline_id == sel]
        req = f"Triage run {st.session_state.run_label} for pipeline {sel} ({len(sub)} anomalies)"
        state = run_with_trace(df_to_anomalies(sub), req)
        st.session_state.result = state
        st.session_state.approvals = {}
    res = st.session_state.result
    if res is None:
        st.info("Press **Run Triage** to start the multi-agent workflow.")
    else:
        st.success(f"Done — {len(res['verdicts'])} verdicts · {res.get('iteration', 0)} rework iteration(s) · "
                   f"{len(res.get('escalated_ids', []))} escalated.")
        with st.expander("📋 Planner — task plan", expanded=True):
            st.json(res["plan"])
            st.caption(get_chat_model().render(
                f"[PLAN]\nrequest={res['plan']['request']}\nn_anomalies={len(res['verdicts'])}\nrouting={res['plan']['routing']}"))
        with st.expander("🔎 Research — enrichment sample + tool calls"):
            st.dataframe(pd.DataFrame(res["enriched"]).head(10), use_container_width=True)
            st.caption("Tools per anomaly: pipeline_metadata · growth_rate · hca_lookup · nearby_features · "
                       "find_interactions (spacing 1.0 m) · validate_record · note_keywords")
        with st.expander("⚙️ Executor — risk results sample"):
            st.dataframe(pd.DataFrame(res["risk_results"]).head(10), use_container_width=True)
        with st.expander("🕵️ Critic — objections & loop iterations", expanded=True):
            objs = res.get("critic_objections", []) or []
            st.metric("Upgrade demands (final pass)", sum(1 for v in res["verdicts"] if v.get("verdict") == "UPGRADE_REQUIRED"))
            for v in [x for x in res["verdicts"] if x.get("verdict") == "UPGRADE_REQUIRED"][:8]:
                st.warning(f"**{v.get('anomaly_id', '?')}**: executor {v.get('executor_class', '?')} → critic {v.get('critic_screen_class', '?')}"
                           f"(legacy {v.get('legacy_label', '?')}) — {'; '.join(v.get('reasons', [])[:2])}")
            if res.get("escalated_ids"):
                st.error(f"Escalated (forced severe after max iterations): {res['escalated_ids'][:20]}")
        with st.expander("✉️ A2A message bus — full handoff trace"):
            st.dataframe(pd.DataFrame(res.get("messages", [])), use_container_width=True)

# ================= 4 RESULTS =================
elif page.startswith("4"):
    st.title("Triage Results")
    res = st.session_state.result
    if res is None:
        st.warning("Run the agents first (page 3).")
    else:
        enr = pd.DataFrame(res["enriched"]).set_index("anomaly_id")
        rsk = pd.DataFrame(res["risk_results"]).set_index("anomaly_id")
        ver = pd.DataFrame(res["verdicts"]).set_index("anomaly_id")
        tbl = enr.join(rsk, rsuffix="_r").join(ver, rsuffix="_v")
        fcls = st.multiselect("Filter by final class", SEV_ORDER, default=SEV_ORDER)
        min_risk = st.slider("Min risk score", 0, 100, 0)
        show = tbl[tbl.final_class.isin(fcls) & (tbl.risk_score >= min_risk)].reset_index()
        st.dataframe(show[["anomaly_id", "pipeline_id", "chainage_m", "depth_pct", "growth_rate_pct_per_yr",
                           "erf", "safe_pressure_mpa", "risk_score", "triage_class", "final_class",
                           "verdict", "legacy_label"]].sort_values("risk_score", ascending=False),
                     use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.histogram(show, x="final_class", category_orders={"final_class": SEV_ORDER},
                                         title="Final class distribution", color="final_class"), use_container_width=True)
            depth = pd.DataFrame(res["enriched"])
            st.plotly_chart(px.scatter(depth, x="depth_pct", y="growth_rate_pct_per_yr", color="hca",
                                       hover_data=["anomaly_id"], title="Depth vs growth rate"), use_container_width=True)
        with c2:
            st.plotly_chart(px.scatter(show, x="chainage_m", y="risk_score", color="final_class",
                                       hover_data=["anomaly_id", "pipeline_id"],
                                       title="Risk score vs chainage"), use_container_width=True)

# ================= 5 CRITIC =================
elif page.startswith("5"):
    st.title("Critic Findings — missed criticals caught")
    res = st.session_state.result
    if res is None:
        st.warning("Run the agents first (page 3).")
    else:
        caught = [v for v in res["verdicts"] if v.get("missed_critical")]
        st.metric("Missed-critical defects caught (legacy under-called, now critical)",
                  sum(1 for v in caught if v["final_class"] in ("IMMEDIATE", "60_DAY")))
        st.caption("Before = legacy manual label · After = Critic-guarded final class")
        if caught:
            df_c = pd.DataFrame(caught)
            st.dataframe(df_c[["anomaly_id", "legacy_label", "executor_class", "critic_screen_class",
                               "final_class", "verdict", "escalated"]].sort_values("anomaly_id"),
                         use_container_width=True)
            aid = st.selectbox("Explain one item", df_c["anomaly_id"].tolist())
            v = next(x for x in caught if x["anomaly_id"] == aid)
            st.markdown(f"**{aid}**: legacy `{v['legacy_label']}` → executor `{v['executor_class']}` → "
                        f"critic screen `{v['critic_screen_class']}` → final `{v['final_class']}`")
            for r in v["reasons"][:3]:
                st.write("• " + r)
        else:
            st.success("No missed criticals in this scope.")

# ================= 6 APPROVAL =================
elif page.startswith("6"):
    st.title("Human Approval & Work Orders")
    res = st.session_state.result
    if res is None:
        st.warning("Run the agents first (page 3).")
    else:
        imm = [v for v in res["verdicts"] if v["final_class"] == "IMMEDIATE"]
        st.subheader(f"Immediate items pending approval ({len(imm)})")
        for v in imm:
            key = f"appr_{v['anomaly_id']}"
            cur = st.session_state.approvals.get(v["anomaly_id"], "APPROVED")
            st.session_state.approvals[v["anomaly_id"]] = st.selectbox(
                f"{v['anomaly_id']} (legacy {v['legacy_label']}, ERF "
                f"{next(r['erf'] for r in res['risk_results'] if r['anomaly_id'] == v['anomaly_id'])})",
                ["APPROVED", "REJECTED"], index=0 if cur == "APPROVED" else 1, key=key)
        if st.button("Confirm approvals & regenerate work orders", type="primary"):
            llm = get_chat_model()
            out = auto_agent.build_outputs(res["enriched"], res["verdicts"], res["risk_results"],
                                           res.get("trace_id", "run"), Path("outputs"), llm,
                                           st.session_state.approvals)
            st.session_state.outputs = out
            res["outputs"] = out
            st.success(f"Generated {out.get('n_work_orders', 0)} work orders · {out.get('n_scheduled', 0)} scheduled for monitoring.")
        out = st.session_state.outputs or res.get("outputs")
        if out:
            wo = pd.read_csv(out["work_orders_csv"])
            st.dataframe(wo, use_container_width=True)
            st.download_button("Download work orders CSV", wo.to_csv(index=False),
                               file_name="work_orders.csv")
            if out.get("scheduled_monitoring_csv") and Path(out["scheduled_monitoring_csv"]).exists():
                sched = pd.read_csv(out["scheduled_monitoring_csv"])
                st.download_button("Download scheduled monitoring CSV", sched.to_csv(index=False),
                                   file_name="scheduled_monitoring.csv")
            with open(out["summary_md"]) as f:
                md = f.read()
            st.download_button("Download engineer summary (.md)", md, file_name="summary.md")
            with open(out["notifications_json"]) as f:
                nj = f.read()
            st.download_button("Download notification payloads (.json)", nj, file_name="notifications.json")
            st.caption("Notifications are simulated payloads written to disk — nothing is actually sent.")

# ================= 7 METRICS =================
elif page.startswith("7"):
    st.title("Validation & Metrics")
    res = st.session_state.result
    if res is None or not res.get("metrics"):
        st.warning("Run the agents first (page 3). Ground-truth metrics need the built-in synthetic file.")
    else:
        m = res["metrics"]
        # Guard against incomplete metrics
        required_keys = ["legacy", "executor", "final"]
        if not all(k in m for k in required_keys):
            st.warning("Metrics incomplete — run a full triage with ground truth data.")
            st.json(m)
        else:
            # Main recall/precision metrics
            cols = st.columns(3)
            for i, name in enumerate(["legacy", "executor", "final"]):
                d = m[name]
                cols[i].metric(f"{name} — critical recall", f"{d['recall_critical']:.3f}",
                               f"prec {d['precision_critical']:.3f} (tp {d['tp']}/fp {d['fp']}/fn {d['fn']})")
            
            # Bar chart
            import plotly.express as px
            import pandas as pd
            st.plotly_chart(px.bar(pd.DataFrame(
                [{"system": k, "recall": m[k]["recall_critical"], "precision": m[k]["precision_critical"]}
                 for k in ("legacy", "executor", "final")]).melt(id_vars="system"),
                x="system", y="value", color="variable", barmode="group",
                title="Critical-class (IMMEDIATE+60_DAY) recall/precision"), use_container_width=True)
            
            # Missed criticals
            st.info(f"Missed criticals caught by Critic guardrail: **{m['missed_caught']}** "
                    f"(legacy false negatives: {m['legacy']['fn']} → final: {m['final']['fn']}). "
                    "Executor-only (numbers without context/notes) scores *below* legacy — automation alone is "
                    "insufficient; the Critic's context re-screen is what recovers the missed defects.")
            
            # Rework stats
            if "rework_stats" in m and m["rework_stats"]:
                rs = m["rework_stats"]
                st.subheader("Rework Loop Statistics")
                if "history" in rs:
                    for h in rs["history"]:
                        st.write(f"**Iteration {h['iteration']}**: {h['objected']} objections, "
                                 f"{h['resolved']} resolved, {h['remaining']} remaining")
                c1, c2 = st.columns(2)
                c1.metric("Total resolved on rework", rs.get("resolved_on_rework", 0))
                c2.metric("Escalated after max iterations", rs.get("escalated", 0))
            
            # Validation errors
            val_errs = len(res.get("validation_errors", []))
            if val_errs > 0:
                st.error(f"Validation errors: {val_errs} records quarantined")
                with st.expander("Validation error details"):
                    for err in res["validation_errors"][:10]:
                        st.json(err)
            else:
                st.success(f"Validation: **0 errors** (pydantic schemas gated all agent outputs)")
            
            # Time saved
            n = len(res["verdicts"])
            manual_min_per = 20
            manual_h = n * manual_min_per / 60
            auto_h = 0.02 * n + len([v for v in res["verdicts"] if v["final_class"] == "IMMEDIATE"]) * 5 / 60
            st.success(f"Simulated time saved (assumption: manual review takes {manual_min_per} min/anomaly; "
                       f"auto triage + targeted review of flagged items only): {manual_h:.1f} h → {auto_h:.1f} h "
                       f"(≈{(1 - auto_h / manual_h) * 100:.0f}% reduction).")
            
            st.caption("Schema/tool-output validation: pydantic schemas gate every agent I/O; malformed outputs are "
                       "rejected and logged. Unit + e2e suite: `pytest tests/` (all green, deterministic seed 42).")
            
            # Confusion matrix
            with st.expander("Confusion matrix (true → final)"):
                st.json(m.get("confusion_final", {}))

# ================= 8 ARCH =================
elif page.startswith("8"):
    st.title("Architecture")
    st.info("The architecture diagram is maintained as a draw.io source. See **docs/ARCHITECTURE_EXPLAINED.md** for the complete component table, edge table, decision points, suggested draw.io layout, and a Mermaid flowchart you can paste into draw.io (Arrange → Insert → Advanced → Mermaid).")
    with st.expander("LangGraph flow"):
        st.code("Planner → Research → Executor → Critic → (UPGRADE? loop-back ≤2 : finalize) "
                "→ human gate (IMMEDIATE) → Business Automation → END", language="text")
    st.subheader("Agent Cards")
    for k, card in AGENT_CARDS.items():
        with st.expander(f"{card['name']} (`{k}`)"):
            st.json(card)
    st.caption("MCP is future scope: tools in src/tools/ are plain functions ready to be exposed via an MCP "
               "server; see docs/ARCHITECTURE_EXPLAINED.md.")
