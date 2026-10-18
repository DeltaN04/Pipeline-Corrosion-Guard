# CorrosionGuard — Project Report

> Agentic AI triage of pipeline corrosion inspection findings.
> **All data synthetic** (seeded generator). Formulas **simplified educational
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
- **Research** — tools: `pipeline_metadata`, `growth_rate`, `hca_lookup`, `nearby_features`,
  `find_interactions`, `validate_record`, `note_keywords`.
- **Executor (Risk Engine)** — B31G safe pressure, ERF, 2-yr projected depth, weighted risk
  score, numbers-only triage class. Every number traceable to a tool call.
- **Critic (independent validator)** — re-derives a screen class with full context rules
  (never copies the executor), note-vs-number contradictions, legacy-label comparison;
  AGREE / DOWNGRADE_RISK / UPGRADE_REQUIRED + missed-critical flags.
- **Business Automation** — work orders (IMMEDIATE + 60_DAY), scheduled monitoring list
  (180_DAY), engineer summary, simulated email/Slack payloads written to disk.
- **Orchestration (LangGraph)** — `Planner → Research → Executor → Critic → router`:
  UPGRADE_REQUIRED loops back with conservative constraints (max 2 iterations); unresolved
  items escalate to the more severe class (`ESCALATED`); human approval gate for IMMEDIATE.

## 4. Architecture explanation

See `docs/ARCHITECTURE_EXPLAINED.md` (component table, edge table, decision points, draw.io layout, Mermaid flowchart).

## 5. Implementation details

- **Mock LLM** (`src/llm/mock_model.py`): subclasses LangChain `BaseChatModel`; parses marker
  tags (`[PLAN]`, `[RISK_RATIONALE]`, `[CRITIC]`, `[SUMMARY]`, `[WORKORDER]`) plus `key=value`
  facts → fixed deterministic templates. Agents use it only for prose; **never for numbers**.
- **State** (`src/graph/state.py`): TypedDict with request, plan, anomalies, enriched, risk
  results, verdicts, iteration, objections, escalations, human decisions, outputs, A2A
  messages, metrics, validation_errors, rework_stats, ground_truth, ablation snapshots.
- **Validation**: pydantic schemas gate every agent I/O (`src/schemas/models.py`); failures
  logged to `validation_errors` and quarantined. 26 tests green.
- **LLM Swap**: `src/llm/provider.py` exposes `llm_text(llm, prompt)` calling `llm.invoke()`.
  `SimpleFakeChatModel` drop-in test proves a non-mock chat model runs the pipeline end to end.

## 6. Output validation & results (real numbers from docs/metrics.json)

Data: 300 anomalies per seed across 4 pipelines (40 km each). Truth from the independent
ground-truth model; legacy labels degraded on planted missed-criticals; ~5% dirty records.
**Tuning seed: 42. Held-out evaluation seeds: 7 and 99.**

| Seed | System | Recall (critical) | Precision | TP | FP | FN |
|------|--------|-------------------|-----------|----|----|----|
| 42 (tune) | Legacy manual labels | 0.333 | 1.000 | 10 | 0 | 20 |
| 42 (tune) | Executor only (no context) | 0.667 | 0.211 | 20 | 75 | 10 |
| 42 (tune) | Executor after rework | 0.667 | 0.215 | 20 | 73 | 10 |
| 42 (tune) | Final (Executor + Critic) | 0.667 | 0.215 | 20 | 73 | 10 |
| 7 (eval) | Legacy | 0.423 | 1.000 | 11 | 0 | 15 |
| 7 (eval) | Executor only | 0.692 | 0.176 | 18 | 84 | 8 |
| 7 (eval) | Final | 0.692 | 0.180 | 18 | 82 | 8 |
| 99 (eval) | Legacy | 0.364 | 1.000 | 12 | 0 | 21 |
| 99 (eval) | Executor only | 0.818 | 0.307 | 27 | 61 | 6 |
| 99 (eval) | Final | 0.818 | 0.318 | 27 | 58 | 6 |

- **missed_caught** (truth critical, legacy below critical, final critical): 13 / 8 / 16 (seeds 42/7/99).
- **false_alarms** (legacy below critical, final critical, truth NOT critical): 73 / 82 / 58.
- **Rework loop**: 1 iteration; objections raised at iteration 0 are all resolved at iteration 1.
- **Interacting share**: ~3–5%. **Escalated**: 0–3%. **Runtime**: <0.2 s per 300-anomaly run.
- **Precision target note**: the pre-set target (precision >= 0.40 with recall >= 0.70) was
  **not reachable by threshold tuning alone**. Root cause: ILI measurement noise (±10% of wall
  thickness) pushes genuinely shallow anomalies over the depth threshold, creating false alarms
  that no threshold adjustment can remove without also dropping recall. Reported honestly.

### Rework convergence caveat

The rework loop's perfect convergence (all objections resolved at iteration 1) comes from the
conservative Executor **sharing the Critic's rule family**: `executor_triage_conservative`
implements the same thresholds as the Critic's `full_screen_class`, so adopting the Critic's
constraints (depth_bump, growth_bump, force_interaction) deterministically raises the class to
match the Critic screen. A truly independent Critic (learned model, different formulation, or
physics-based finite-element check) is **future scope** and would make the loop a genuine
second opinion rather than a rule-family mirror.

## 7. Limitations

- **Synthetic data**: patterns are designed, not operator ILI; no vendor formats, no GIS.
- **Simplified formulas**: B31G/ERF/risk rules are educational approximations; **not for real decisions**.
- **Low precision / over-triage**: final critical precision is 0.18–0.32 (target was >= 0.40,
  not reached). Of the anomalies flagged critical by the pipeline, only ~20–30% are truly
  critical — 58–82 false alarms per 300-anomaly run. Root cause: ILI sizing noise pushes
  shallow anomalies over depth thresholds; threshold tuning cannot fix this without sacrificing
  recall. Flagging is deliberately conservative (better to over-inspect than miss a rupture),
  but a production system would need calibrated noise models or multi-signal confirmation.
- **Mock LLM**: template prose only — no real language understanding.
- **Rule-family mirror**: rework convergence is partly by design (see §6 caveat).
- **Static thresholds**: no learning from engineer feedback yet.
- **Single-machine PoC**: no auth, audit DB, or crew scheduling.

## 8. Future scope

Real LLM via Ollama (one-line swap); MCP tool server; real ILI vendor parsers + GIS; RAG over
ASME B31G/B31.8S + operator SOPs; **learned or physics-based independent Critic**; calibrated
noise models to reduce over-triage; active learning from approval feedback.

---

*End of report. Metrics source: `docs/metrics.json` (generated by `scripts/run_eval.py`).*