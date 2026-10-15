"""Build presentation.pptx (~12 slides) from REPORT content + real run metrics.

Usage: .venv/bin/python build_ppt.py  ->  presentation.pptx
Offline, deterministic (seed 42). Re-runs the headless graph (~1 s) for live numbers.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x1B, 0x3A, 0x6B)
ACCENT = RGBColor(0xC6, 0x28, 0x28)
GREY = RGBColor(0x5A, 0x5A, 0x5A)
BG = RGBColor(0xF4, 0xF6, 0xFB)


def get_metrics():
    from src.graph.runner import run_triage

    df = pd.read_csv(ROOT / "data" / "ili_anomalies.csv")
    final = run_triage(df, request="ppt metrics run")
    return df, final


def style_slide(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG


def add_title(slide, text, size=30):
    box = slide.shapes.add_textbox(Inches(0.5), Inches(0.15), Inches(9), Inches(0.9))
    p = box.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = True
    p.font.color.rgb = NAVY


def add_body(slide, bullets, top=1.2, size=15):
    box = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(9), Inches(4.5))
    tf = box.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b
        p.level = 0
        p.font.size = Pt(size)
        p.font.color.rgb = GREY
        p.space_after = Pt(6)


def main() -> None:
    df, final = get_metrics()
    m = final["metrics"]
    n = len(df)
    n_imm = sum(1 for v in final["verdicts"] if v["final_class"] == "IMMEDIATE")
    n_up = sum(1 for v in final["verdicts"] if v["verdict"] == "UPGRADE_REQUIRED")
    n_esc = len(final.get("escalated_ids", []))

    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(6)

    blank = prs.slide_layouts[6]
    slides = [
        ("CorrosionGuard", ["Agentic AI triage of pipeline corrosion inspection findings",
                            "Catches missed critical defects · offline PoC (Streamlit + LangGraph + Mock LLM)",
                            "Synthetic data · simplified formulas (educational only)"]),
        ("Problem: thousands of ILI anomalies, manual review",
         [f"ILI tools report thousands of metal-loss anomalies per run ({n} in this PoC, 4 segments)",
          "Engineers hand-review spreadsheets/PDFs → slow, inconsistent between engineers",
          "Context missed: growth rate, weld/road/water proximity, HCAs, interacting anomalies",
          "Inspector notes contradict numbers — no independent second check",
          "Missed criticals → leaks, ruptures, fines, downtime"]),
        ("Existing business challenge",
         ["Manual triage: 20 min/anomaly ≈ 100 h per 300-anomaly run (stated assumption)",
          "Legacy labels in our synthetic run miss 18/123 criticals (recall 0.854)",
          "~10% planted missed criticals: moderate depth + high growth + HCA/interaction",
          "~5% dirty records (missing/negative/unit errors) slip through manual review",
          "No audit trail of why an anomaly got its priority"]),
        ("Proposed solution: 5 agents + critic loop + human gate",
         ["Planner → Research → Executor → Critic → (rework ≤2 / escalate) → human gate → Automation",
          "Every number from a tool call (B31G, ERF, growth, risk score) — fully traceable",
          "Critic independently re-screens; rejects and forces rework on disagreement",
          "Human approves Immediate items; work orders/report/notifications auto-generated",
          "A2A typed message bus: every handoff logged and visible"]),
        ("Agent roles & responsibilities",
         ["Planner: task plan, routing (small/large batch), deep-check scope",
          "Research: metadata, growth, HCA, welds/crossings, interaction clustering, data quality",
          "Executor (Risk Engine): safe pressure, ERF, projection, risk score, triage class",
          "Critic: independent rules, note contradictions, legacy comparison, AGREE/UPGRADE/DOWNGRADE",
          "Automation: work orders + due dates, engineer summary, simulated notifications"]),
        ("Orchestration workflow (LangGraph)",
         ["Shared typed state: plan, enriched, risk, verdicts, iterations, approvals, outputs, trace",
          "Conditional edge on critic verdict: UPGRADE_REQUIRED → Executor with constraints",
          f"This run: {final.get('iteration', 0)} rework iteration(s), {n_up} final upgrade(s), {n_esc} escalated",
          "Unresolved → forced to more severe class, marked ESCALATED",
          "Human gate only for IMMEDIATE — the rest auto-approved with audit log"]),
        ("ARCH_IMG", []),
        ("Tools & tech stack (all offline)",
         ["Python 3.12 · Streamlit · LangGraph · langchain-core (BaseChatModel) · pydantic",
          "pandas · numpy · plotly · python-pptx · matplotlib · pytest",
          "MockChatModel: deterministic rule-template text behind one-line LLMProvider swap",
          "Tools: b31g / risk / lookup / clustering / quality — pure functions (MCP-ready seam)",
          "Seed 42 · full 300-anomaly run in <1 s (budget 30 s)"]),
        ("Demo walkthrough (3 minutes)",
         ["1 Home: problem + manual-vs-agentic table (30 s)",
          "2 Data: load synthetic CSV, quality report (20 s)",
          "3 Run Agents: live plan → tools → critic loop → A2A trace (60 s)",
          "4–5 Results + Critic Findings: missed criticals before/after (40 s)",
          "6–8 Approval → work orders → metrics → architecture (30 s)"]),
        ("Results & validation (real numbers, seed 42)",
         [f"Legacy manual recall (critical): {m['legacy']['recall_critical']} (FN {m['legacy']['fn']})",
          f"Executor-only recall: {m['executor']['recall_critical']} — automation alone is NOT enough",
          f"Executor + Critic recall: {m['final']['recall_critical']} (FN {m['legacy']['fn']} → {m['final']['fn']})",
          f"Missed criticals caught: {m['missed_caught']} · Immediate items: {n_imm}",
          "23/23 pytest green · deterministic · <1 s runtime"]),
        ("Limitations (stated honestly)",
         ["Synthetic data — not real operator ILI; no vendor formats, no GIS",
          "Simplified B31G/ERF — educational only, never for real dig decisions",
          "Mock LLM writes template prose — no real language understanding",
          "Static thresholds; no learning from engineer feedback yet",
          "Single-machine PoC: no auth, audit DB, or crew scheduling"]),
        ("Future scope & conclusion",
         ["Real LLM via Ollama (one-line swap) · MCP tool server · vendor parsers + GIS",
          "RAG over ASME B31G/B31.8S + operator SOPs · learning from approvals",
          f"Conclusion: critic-guarded agents lift critical recall {m['legacy']['recall_critical']} → "
          f"{m['final']['recall_critical']} with full traceability — a viable second pair of eyes."]),
    ]
    for title, bullets in slides:
        s = prs.slides.add_slide(blank)
        style_slide(s)
        if title == "ARCH_IMG":
            add_title(s, "Architecture", 30)
            img = ROOT / "docs" / "architecture.png"
            if img.exists():
                s.shapes.add_picture(str(img), Inches(0.7), Inches(1.2), width=Inches(8.6), height=Inches(4.2))
            continue
        add_title(s, title, 30 if len(title) < 40 else 26)
        add_body(s, bullets, size=14 if len(bullets) > 4 else 15)
        if title == "CorrosionGuard":
            box = s.shapes.add_textbox(Inches(0.5), Inches(4.6), Inches(9), Inches(0.6))
            p = box.text_frame.paragraphs[0]
            p.text = "pip install -r requirements.txt && streamlit run app.py"
            p.font.size = Pt(13)
            p.font.color.rgb = ACCENT
    out = ROOT / "presentation.pptx"
    prs.save(out)
    print(f"Wrote {out} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
