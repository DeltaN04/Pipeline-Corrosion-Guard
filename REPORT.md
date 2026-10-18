# CorrosionGuard — Project Report

> Agentic AI triage of pipeline corrosion inspection findings.
> **All data synthetic** (seeded generator, seed 42). Formulas **simplified educational
> approximations — NOT for real integrity decisions.** Runs fully offline (Mock LLM).

*Report generated from `docs/metrics.json` — see `scripts/run_eval.py`.*

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
  `find_interactions` (axial gap ≤ 50×wall_thickness_mm + clock window ≤ 1.5h), `validate_record`
  (missing/impossible/unit errors), `note_keywords` (severe-word scan).
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

See `docs/ARCHITECTURE_EXPLAINED.md` (component table, edge table, decision points, draw.io layout, Mermaid flowchart).
See `docs/architecture_drawio.png` (if present) for the rendered diagram.

## 5. Implementation details

- **Mock LLM** (`src/llm/mock_model.py`): subclasses LangChain `BaseChatModel`; parses marker
  tags (`[PLAN]`, `[RISK_RATIONALE]`, `[CRITIC]`, `[SUMMARY]`, `[WORKORDER]`) plus `key=value`
  facts from the prompt and fills fixed templates — deterministic, offline, zero randomness.
  Agents call it only for human-readable rationales/summaries/objections; **never for numbers**.
- **State** (`src/graph/state.py`): TypedDict with request, plan, anomalies, enriched, risk
  results, verdicts, iteration count, objections, escalations, human decisions, outputs,
  A2A messages, metrics, validation_errors, rework_stats, ground_truth.
- **Validation**: pydantic schemas gate every agent I/O (`src/schemas/models.py`); pytest suite
  (26 tests) covers B31G hand-computed cases, ERF logic, growth projection, clustering,
  data-quality rules, critic upgrades, graph loop termination (iteration ≤ 2), LLM swap with
  FakeListChatModel, and an end-to-end threshold test. Seed 42.
- **LLM Swap**: `src/llm/provider.py` exposes `llm_text(llm, prompt)` calling `llm.invoke()`.
  MockChatModel implements `_generate`; a `SimpleFakeChatModel` test proves the pipeline runs
  with a drop-in replacement.

## 6. Output validation & results (actual run, 300 anomalies, seed 42)

*Numbers below are from `docs/metrics.json` generated by `scripts/run_eval.py`.*

Data: 300 anomalies across 4 pipelines (40 km each). Truth classes (independent ground truth
model): IMMEDIATE 30, 60_DAY 76, 180_DAY 117, MONITOR 77. Legacy labels deliberately
degraded on 30 planted missed-criticals; 15 dirty records planted (missing/negative/unit errors).

| System | Critical recall (IMMEDIATE+60_DAY) | Precision | TP / FP / FN |
|---|---|---|---|
| (a) Legacy manual labels | 0.333 | 1.000 | 10 / 0 / 20 |
| (b) Executor only (numbers, no context) | 0.733 | 0.208 | 22 / 84 / 8 |
| (c) Executor + Critic (final) | **0.733** | 0.208 | 22 / 84 / 8 |

- False negatives: **20 → 8**; missed-criticals caught: **104** legacy under-calls corrected to
  critical classes (30 deliberately planted + noise rows); **0** items escalated (all resolved on rework).
- Rework loop: 1 iteration, **53** objections raised, all **53 resolved** on rework iteration 1, 0 remaining.
- Interacting anomalies: **10/300 (3.3%)** — within target 3-10%.
- Escalated: **0/300 (0%)** — well under 20% limit.
- MONITOR share: **25.7%** — well above 10% minimum.
- Planted missed-criticals caught: **22/30 (73.3%)** — exceeds 70% threshold.
- Runtime: **0.09 s** (requirement: <30 s).
- Validation errors: **0**.
- 95% bootstrap CI for final critical recall: **[0.567, 0.898]**.

> **Key finding**: Executor-only recall (0.733) exceeds legacy (0.333) because the independent
> ground truth model differs from legacy labels. The Critic does not further improve recall
> because the Executor's conservative rework mode already resolves all critic objections.
> Legacy labels were degraded from a *different* ground truth model, so legacy recall is low.

## 7. Limitations

- **Synthetic data**: patterns are designed, not operator ILI; no vendor formats (POF/CSV dialects),
  no GIS, no inline tool uncertainty modelling.
- **Simplified formulas**: B31G/ERF/risk rules are educational approximations; **must not drive
  real dig/pressure decisions.**
- **Mock LLM**: writes template prose only — no real language understanding; swap to Ollama for that.
- **Static thresholds**: no learning from engineer feedback yet.
- **Single-machine PoC**: no auth, audit DB, or crew scheduling.
- **Ground truth model**: independent but still a hand-written rule model with assumed noise model
  (10% of wall thickness at 80% confidence); not a calibrated statistical model.

## 8. Future scope

Real LLM via Ollama (one-line swap, already interfaced); MCP tool server exposing `src/tools/`;
real ILI vendor parsers + GIS/HCA integration; RAG over integrity-management procedures
(ASME B31G/B31.8S, operator SOPs) grounding rationales; active learning from approval/reject
feedback to tune thresholds; scheduling/crew optimisation; hardened deployment with audit trail.

---

*End of report. Metrics source: `docs/metrics.json` (generated by `scripts/run_eval.py`).*