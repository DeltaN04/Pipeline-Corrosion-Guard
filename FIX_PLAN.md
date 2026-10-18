# CorrosionGuard Fix Plan

## Issue 1: Data Realism (~98% interacting)
**Files to touch:**
- `data/generate_data.py` - change chainage to 0-40000m, HCA windows in metres, forced clusters in metres
- `src/tools/clustering.py` - new interaction rule: axial gap <= 3*wall_thickness_mm AND clock diff <= CLOCK_WINDOW_DEG
- `src/tools/lookup.py` - hca_lookup works with metre chainage
- `src/agents/automation.py` - work-order location text uses metres
- `app.py` - risk-vs-chainage chart axis, tables display metres
- tests - update any chainage-related assertions

## Issue 2: Circular Ground Truth
**Files to touch:**
- `data/ground_truth.py` - NEW FILE with independent truth model (no risk.py import)
- `data/generate_data.py` - use ground_truth.py, add measurement noise, remove true_class from agent view
- `src/graph/runner.py` - strip truth columns before graph state, pass separately to metrics
- `tests/test_ground_truth_independence.py` - NEW test (AST-based import check)
- `src/graph/builder.py` - update metrics function for bootstrap CI, ablation row
- tests - update test_e2e.py with new thresholds

## Issue 3: Rework Loop Cannot Resolve
**Files to touch:**
- `src/tools/risk.py` - add executor_triage_conservative with context awareness
- `src/agents/executor.py` - apply constraints on rework, only re-execute objected anomalies
- `src/agents/critic.py` - track resolved/unresolved per anomaly
- `src/graph/builder.py` - clean finalize logic, per-iteration stats in state
- `src/agents/planner.py` - dynamic plan based on data (dirty count, batch size)
- `app.py` - show per-iteration stats in Critic panel
- tests - test for different plans, test rework resolution

## Issue 4: False Claims (schemas unused; Ollama swap crashes)
**Files to touch:**
- `src/llm/provider.py` - add llm_text() using invoke, deprecate .render
- All agent files - use llm_text() instead of .render
- `src/graph/builder.py` - validate every agent output with Pydantic models, quarantine on failure
- `src/schemas/models.py` - ensure all models are used
- `app.py` - show validation errors in Validation tab
- `tests/test_llm_swap.py` - NEW test with FakeListChatModel
- tests - add validation tests

## Issue 5: Output/Workflow Realism
**Files to touch:**
- `src/agents/automation.py` - work orders only IMMEDIATE/60_DAY; 180_DAY -> monitoring list; MONITOR -> nothing
- `src/graph/builder.py` - headless runs label AUTO_APPROVED_HEADLESS
- `app.py` - IMMEDIATE stays PENDING_APPROVAL until user confirms
- tests/test_e2e.py - tighter assertions

## Issue 6: Architecture Documentation
**Files to touch:**
- DELETE `docs/generate_diagram.py`
- DELETE `docs/architecture.png`
- CREATE `docs/ARCHITECTURE_EXPLAINED.md` with all 6 sections
- `build_ppt.py` - handle missing/present draw.io image

## Issue 7: Hygiene & Honest Docs
**Files to touch:**
- Clean `outputs/` - delete contents, add .gitkeep
- `.gitignore` - add outputs/
- Remove .DS_Store
- Clean `data/generate_data.py` - remove dead code (if False else, provisional truth pass)
- CREATE `scripts/run_eval.py` - runs pipeline, writes docs/metrics.json
- REPORT.md - results section from metrics.json, honest limitations
- `build_ppt.py` - read from metrics.json
- README.md - fix commands, mention new scripts, remove false claims