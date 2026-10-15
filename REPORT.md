# CorrosionGuard — Project Report

> Agentic AI triage of pipeline corrosion inspection findings.
> **All data synthetic** (seeded generator, seed 42). Formulas **simplified educational
> approximations — NOT for real integrity decisions.** Runs fully offline (Mock LLM).

## 1. Problem statement & domain justification

ILI (in-line inspection) tools report **thousands of metal-loss anomalies per pipeline run**.
Engineers manually review spreadsheets/PDFs, assign priority
(**Immediate / 60-day / 180-day / Monitor**) and schedule verification digs.
Anomalies that look minor in isolation are critical in context: high depth-growth rate,
proximity to welds/road crossings/water bodies, high-consequence areas (HCAs), interacting
(colocated) anomalies, or inspector free-text notes contradicting the numeric fields.
There is no independent second check, so missed criticals surface as leaks, ruptures, fines
and downtime.

## 2. Existing business challenge → proposed solution

| Challenge (manual process) | Solution (CorrosionGuard agents) |
|---|---|
| Slow manual spreadsheet review | Risk engine triages all ~300 anomalies in <1 s |
| Inconsistent judgment between engineers | Deterministic tools: B31G safe pressure, ERF, growth projection, weighted risk score |
| Context missed (growth, HCA, welds, crossings, interaction, notes) | Research agent enriches every record via lookup/clustering/keyword tools |
| No independent second check | Critic agent re-screens with independent rules, forces rework, escalates |
| Digs scheduled by hand | Work orders + engineer report + notification payloads auto-generated |
| Missed criticals found after incidents | Missed-critical detector vs legacy labels; human gate for Immediate items |

## 3. Agent roles, responsibilities, orchestration

- **Planner** — parses the run request, emits an ordered TaskPlan (task/owner/tools), picks
  routing (small vs large batch) and deep-check scope. Plan visible in UI.
- **Research** — tools: `pipeline_metadata`, `growth_rate` (prior vs current depth), `hca_lookup`
  (map confirmation + mismatch flags), `nearby_features` (weld <5 m, road, water),
  `find_interactions` (1.0 m chainage clustering), `validate_record` (missing/impossible/unit
  errors), `note_keywords` (severe-word scan).
- **Executor (Risk Engine)** — tools: simplified Modified B31G safe pressure, ERF = MAOP/safe
  pressure, 2-yr projected depth, transparent weighted risk score (likelihood×consequence with
  listed factors), numbers-only triage class. Every number traceable to a tool call.
- **Critic (independent validator)** — re-derives a screen class with the *full* context rules
  (never copies the executor), checks note-vs-number contradictions (`severe/sharp/undercut/
  leak/crack`), ERF ≥ 1.0, rapid growth, interaction/HCA context, and legacy-label comparison;
  emits AGREE / DOWNGRADE_RISK / UPGRADE_REQUIRED + missed-critical flags. Can reject results.
- **Business Automation** — work orders (priority, location, action, due date by class:
  Immediate +0 d, 60-day +60 d, 180-day +180 d, Monitor +365 d), engineer summary, simulated
  email/Slack payloads written to disk (never sent).
- **Orchestration (LangGraph)** — `Planner → Research → Executor → Critic → router`:
  UPGRADE_REQUIRED loops back with conservative constraints (depth/growth bumps, forced
  interaction), max 2 iterations; still-unresolved items escalate to the more severe class
  (`ESCALATED`); then a human approval gate for IMMEDIATE items, then automation. All handoffs
  are typed `AgentMessage` envelopes on an in-process bus with a full UI-visible trace.

## 4. Architecture explanation

See `docs/architecture.md` (Mermaid + rendered `docs/architecture.png`): user/UI, five agents,
tools package, data stores (ILI CSV, HCA map), A2A bus, Mock LLM behind a one-line provider
swap (`src/llm/provider.py`: `LLM_BACKEND = "mock"` → `"ollama"`), human gate, critic
feedback loop with the ≤2-iteration router, and decision points. MCP is future scope: the
`src/tools/` function boundary is the seam for exposing tools via an MCP server.

## 5. Implementation details

- **Mock LLM** (`src/llm/mock_model.py`): subclasses LangChain `BaseChatModel`; parses marker
  tags (`[PLAN]`, `[RISK_RATIONALE]`, `[CRITIC]`, `[SUMMARY]`, `[WORKORDER]`) plus `key=value`
  facts from the prompt and fills fixed templates — deterministic, offline, zero randomness.
  Agents call it only for human-readable rationales/summaries/objections; **never for numbers**.
- **State** (`src/graph/state.py`): TypedDict with request, plan, anomalies, enriched, risk
  results, verdicts, iteration count, objections, escalations, human decisions, outputs,
  A2A messages, metrics.
- **Validation**: pydantic schemas gate every agent I/O (`src/schemas/models.py`); pytest suite
  (23 tests) covers B31G hand-computed cases, ERF logic, growth projection, clustering,
  data-quality rules, critic upgrades, graph loop termination (iteration ≤ 2), and an end-to-end
  threshold test (Critic catches ≥50% of planted missed-criticals; full run <30 s). Seed 42.

## 6. Output validation & results (actual run, 300 anomalies, seed 42)

Data: true classes {IMMEDIATE 48, 60_DAY 75, 180_DAY 99, MONITOR 78}; legacy labels deliberately
degraded on **34 planted missed-criticals**; **15 dirty records** planted (missing/negative/unit errors).

| System | Critical recall (IMMEDIATE+60_DAY) | Precision | TP / FP / FN |
|---|---|---|---|
| (a) Legacy manual labels | 0.854 | 0.946 | 105 / 6 / 18 |
| (b) Executor only (numbers, no context) | 0.829 | 0.962 | 102 / 4 / 21 |
| (c) Executor + Critic (final) | **0.984** | 0.910 | 121 / 12 / 2 |

- False negatives: **18 → 2**; missed-criticals caught: **39** legacy under-calls corrected to
  critical classes (34 deliberately planted + noise rows); 2 unresolved items escalated.
- Executor-only scores *below* legacy: automation without context is insufficient — the Critic's
  context/notes re-screen is what recovers the missed defects. Precision dips slightly (0.946 →
  0.910): a deliberate conservative bias (dirty records quarantined, HCA/interaction upgrades).
- Runtime: **<1 s** for 300 anomalies (requirement: <30 s). Simulated time saved: manual review
  at the stated assumption of 20 min/anomaly ≈ 100 h → auto triage + targeted review ≈ 2 h
  (≈98% reduction; assumption explicit in UI).
- Confusion (true→final): `60_DAY→IMMEDIATE 9, 60_DAY→60_DAY 65, IMMEDIATE→IMMEDIATE 47,
  180_DAY→180_DAY 89, MONITOR→180_DAY 75, 180_DAY→IMMEDIATE 2, MONITOR→MONITOR 1,
  180_DAY→60_DAY 8, MONITOR→IMMEDIATE 2, IMMEDIATE→180_DAY 1, 60_DAY→180_DAY 1`.

## 7. Limitations

- Synthetic data: patterns are designed, not operator ILI; no vendor formats (POF/CSV dialects),
  no GIS, no inline tool uncertainty modelling.
- Simplified B31G/ERF/risk rules for education; **must not drive real dig/pressure decisions.**
- Mock LLM writes template prose only — no real language understanding; swap to Ollama for that.
- No learning loop from engineer feedback yet; thresholds are static.
- Single-machine Streamlit PoC; no auth, audit DB, or role-based approval workflow.

## 8. Future scope

Real LLM via Ollama (one-line swap, already interfaced); MCP tool server exposing `src/tools/`;
real ILI vendor parsers + GIS/HCA integration; RAG over integrity-management procedures
(ASME B31G/B31.8S, operator SOPs) grounding rationales; active learning from approval/reject
feedback to tune thresholds; scheduling/crew optimisation; hardened deployment with audit trail.
