# CorrosionGuard

Agentic AI that triages pipeline corrosion ILI findings by risk — and catches missed critical defects.
Offline PoC: **Streamlit + LangGraph + deterministic Mock LLM**. No paid APIs, no internet at runtime.

> **Synthetic data only.** Engineering formulas are **simplified educational approximations**,
> **NOT for real integrity decisions.**

## Setup & run

```bash
cd corrosionguard
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt  # or: uv pip install ...
.venv/bin/python data/generate_data.py        # regenerate synthetic data (seed 42)
.venv/bin/python -m pytest tests/ -q          # validation suite (23 tests)
.venv/bin/python -m streamlit run app.py      # launch UI  →  http://localhost:8501
```

One-command equivalent: `pip install -r requirements.txt && streamlit run app.py`

## 3-minute demo script

1. **Home** (30 s): problem statement + manual-vs-agentic table.
2. **Data** (20 s): *Load built-in synthetic data* → 300 anomalies, quality report (15 dirty records flagged).
3. **Run Agents** (60 s): scope `ALL`, **Run Triage** → watch Planner plan, Research enrichment
   (interacting/dirty counts), Executor triage, Critic upgrades, loop-back iterations, escalation, A2A trace.
4. **Triage Results** (20 s): sortable table + Plotly charts (class mix, risk vs chainage, depth vs growth).
5. **Critic Findings** (20 s): missed criticals caught, before/after legacy labels, per-item explanation.
6. **Human Approval** (20 s): approve/reject IMMEDIATEs → confirm → download work orders/report/notifications.
7. **Validation** (20 s): recall bars legacy 0.85 → executor 0.83 → final **0.98**; time-saved assumption stated.
8. **Architecture** (10 s): diagram + agent cards + LangGraph flow.

## Headless smoke test (no browser)

```bash
.venv/bin/python src/graph/runner.py data/ili_anomalies.csv
```

## Assumptions

- Manual review baseline: 20 min/anomaly (stated in UI + REPORT; adjust to your shop's number).
- Critical defect = final class IMMEDIATE or 60_DAY (for recall/precision).
- Simplified Modified B31G with flow stress 1.1×SMYS; interaction threshold 1.0 m chainage.
- Mock LLM output is template text — a stand-in for rationales, not engineering judgment.
- `LLM_BACKEND="mock"` in `src/llm/provider.py`; swap to `"ollama"` (+ `langchain-ollama`) for a real model.

## Project structure

```
corrosionguard/
  app.py  requirements.txt  README.md  REPORT.md  build_ppt.py  conftest.py
  data/  generate_data.py  ili_anomalies.csv
  src/agents/  planner, research, executor, critic, automation
  src/graph/  state, builder (LangGraph), runner (headless), a2a (bus + agent cards)
  src/tools/  b31g, risk, lookup, clustering, quality
  src/llm/  provider (one-line swap), mock_model (BaseChatModel)
  src/schemas/  pydantic models
  tests/  7 files, 23 tests
  docs/  architecture.md, architecture.png, generate_diagram.py
  outputs/  work orders, summaries, notifications (generated at runtime)
```
