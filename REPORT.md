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
  **Final triage always honors the Critic**: final severity = more severe of
  (post-rework Executor class, Critic screen class).

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
  logged to `validation_errors` and quarantined. 29 tests green.
- **LLM Swap**: `src/llm/provider.py` exposes `llm_text(llm, prompt)` calling `llm.invoke()`.
  `SimpleFakeChatModel` drop-in test proves a non-mock chat model runs the pipeline end to end.

## 6. Output validation & results (real numbers from docs/metrics.json)

Data: 300 anomalies per seed across 4 pipelines (40 km each). Truth from the independent
ground-truth model; legacy labels degraded on planted missed-criticals; ~5% dirty records.
**Tuning seed: 42. Held-out evaluation seeds: 7 and 99.**

### Critical-class (IMMEDIATE + 60_DAY) recall / precision

| Seed | Legacy | Executor only | Executor after rework | Critic screen | Final |
|------|--------|---------------|----------------------|---------------|-------|
| 42 (tune) | 0.333 / 1.000 | 0.667 / 0.211 | 0.733 / 0.208 | 0.733 / 0.208 | **0.733 / 0.208** |
| 7 (eval) | 0.423 / 1.000 | 0.692 / 0.176 | 0.731 / 0.178 | 0.731 / 0.178 | **0.731 / 0.178** |
| 99 (eval) | 0.364 / 1.000 | 0.818 / 0.307 | 0.879 / 0.282 | 0.879 / 0.282 | **0.879 / 0.282** |

Aggregate eval seeds 7+99: legacy recall 0.393; executor_only 0.755/0.241;
executor_after_rework = critic_screen = final: **recall 0.805, precision 0.230**.

### IMMEDIATE-only recall / precision (eval seeds 7+99 means)

| System | IMMEDIATE recall | IMMEDIATE precision |
|--------|------------------|---------------------|
| Legacy | 0.079 | 0.500 |
| Executor only | 0.675 | 0.589 |
| Executor after rework | 0.728 | 0.436 |
| Critic screen = Final | 0.728 | 0.436 |

### Classification accuracy (seed 42 example; per-seed values in metrics.json)

Exact-class accuracy ≈ 0.50–0.55; within-one-class accuracy ≈ 0.85–0.89 across systems.
Over-triage (predicted class more severe than truth): 111–136 per run.
Under-triage: 10–16 per run.

### Missed criticals and false alarms

- **missed_caught** (truth critical, legacy below critical, final critical): 15 / 9 / 18 (seeds 42/7/99).
- **false_alarms** (final critical, truth not critical): 84 / 88 / 74.
- **Adjacency of false alarms** (seed 42): 48 adjacent-class (truly 180_DAY flagged 60_DAY/IMMEDIATE,
  or truly MONITOR flagged 180_DAY), 36 two-plus classes off (mostly truly MONITOR flagged 60_DAY+).

### Measurement-noise experiment (same seeds, pipeline re-run with zero noise)

| Seed | Final precision (noisy) | Final precision (zero noise) | Delta |
|------|------------------------|------------------------------|-------|
| 42 | 0.208 | 0.216 | +0.008 |
| 7 | 0.178 | 0.182 | +0.004 |
| 99 | 0.282 | 0.284 | +0.002 |

**Measured conclusion:** ILI sizing noise is **NOT** the primary contributor to false alarms
(mean precision delta only +0.005). The false alarms are dominated by genuinely ambiguous
shallow anomalies with context flags (HCA/crossing/interaction) that the rules flag
conservatively. Over-triage is a deliberate conservative bias, not a noise artifact.

### Critic's measured contribution — stated truthfully

- **Critical recall:** the Critic screen alone (0.733–0.879) equals the final system on every
  seed — because final now always honors the Critic. The Critic is the *dominant* contributor
  to critical recall; the Executor-only ablation (0.667–0.818) is lower.
- **Rework adds nothing measurable on top of the Critic screen**: executor_after_rework and
  critic_screen rows are identical on all three seeds. The conservative Executor shares the
  Critic's rule family, so adopting the Critic's constraints deterministically reproduces the
  screen class — the "loop" converges by construction, not by independent reasoning.
- **What the Critic adds:** it is the recall floor (nothing ends below its screen); its
  independent screen is what forces UPGRADE_REQUIRED objections in the first place. But its
  precision (0.18–0.28) is inherited by the final system verbatim.

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
- **Low precision / over-triage**: final critical precision is 0.18–0.28 across seeds.
  The zero-noise experiment shows this is **not** primarily an ILI-sizing-noise artifact —
  false alarms are genuinely ambiguous shallow/context-flagged anomalies that the rules treat
  conservatively. ~75% of flagged items are not truly critical (over-triage 111–136 per run),
  and 48/84 of seed-42 false alarms are adjacent-class (off by one severity level).
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