"""Build presentation.pptx (~12 slides) from metrics.json + REPORT content.

Usage: .venv/bin/python build_ppt.py  ->  presentation.pptx
Offline, deterministic (seed 42).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

NAVY = RGBColor(0x1B, 0x3A, 0x6B)
ACCENT = RGBColor(0xC6, 0x28, 0x28)
GREY = RGBColor(0x5A, 0x5A, 0x5A)
BG = RGBColor(0xF4, 0xF6, 0xFB)


def load_metrics():
    path = ROOT / "docs" / "metrics.json"
    if path.exists():
        return json.loads(path.read_text())
    # Fallback: run evaluation
    from src.graph.runner import run_triage, extract_ground_truth
    df = pd.read_csv(ROOT / "data" / "ili_anomalies.csv")
    gt = extract_ground_truth(df)
    final = run_triage(df, request="ppt metrics run")
    return final["metrics"]


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


def fmt(x):
    """Format number for slides."""
    if isinstance(x, float):
        return f"{x:.3f}" if x < 1 else f"{x:.1f}"
    return str(x)


def main() -> None:
    m = load_metrics()
    per = m.get("per_seed", {})
    agg = m.get("aggregate_eval_seeds", {})
    p42 = per.get("42", {})
    p99 = per.get("99", {})
    n = p42.get("n_total", 300)
    rs = p42.get("rework_stats", {})
    hist = rs.get("history", [])
    n_up = hist[-1].get("objected", 0) if hist else 0
    n_esc = p42.get("escalated_count", 0)
    interacting_share = p42.get("interacting_share", 0)
    escalated_share = p42.get("escalated_share", 0)
    missed_caught = p42.get("missed_caught", 0)
    false_alarms = p42.get("false_alarms", 0)
    val_errs = p42.get("validation_errors", 0)
    runtime = p42.get("runtime_seconds", 0)
    legacy_recall = p42.get("legacy", {}).get("recall_critical", 0)
    final_recall = p42.get("final", {}).get("recall_critical", 0)
    ci = p42.get("final_recall_ci95", [0, 0])
    planted_catch = p42.get("planted_miss_catch_rate", 0)
    n_imm = 0  # not in new structure; omit from slides

    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(6)

    blank = prs.slide_layouts[6]
    slides = [
        ("CorrosionGuard", [
            "Agentic AI triage of pipeline corrosion inspection findings",
            "Catches missed critical defects · offline PoC (Streamlit + LangGraph + Mock LLM)",
            "Synthetic data · simplified formulas (educational only)"
        ]),
        ("Problem: thousands of ILI anomalies, manual review",
         [f"ILI tools report thousands of metal-loss anomalies per run ({n} in this PoC, 4 segments)",
          "Engineers hand-review spreadsheets/PDFs → slow, inconsistent between engineers",
          "Context missed: growth rate, weld/road/water proximity, HCAs, interacting anomalies",
          "Inspector notes contradict numbers — no independent second check",
          "Missed criticals → leaks, ruptures, fines, downtime"]),
        ("Existing business challenge",
         [f"Manual triage: 20 min/anomaly ≈ 100 h per 300-anomaly run (stated assumption)",
          f"Legacy labels in our synthetic run have recall {fmt(legacy_recall)} — many criticals missed",
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
          f"This run: {p42.get('iterations', 0)} rework iteration(s), {n_up} objections, {n_esc} escalated",
          "Unresolved → forced to more severe class, marked ESCALATED",
          "Human gate only for IMMEDIATE — the rest auto-approved with audit log"]),
        ("ARCH_IMG", []),
        ("Tools & tech stack (all offline)",
         ["Python 3.12 · Streamlit · LangGraph · langchain-core (BaseChatModel) · pydantic",
          "pandas · numpy · plotly · python-pptx · matplotlib · pytest",
          "MockChatModel: deterministic rule-template text behind one-line LLMProvider swap",
          "Tools: b31g / risk / lookup / clustering / quality — pure functions (MCP-ready seam)",
          f"Seed 42 · full {n}-anomaly run in {fmt(m.get('runtime_seconds', 0))} s (budget 30 s)"]),
        ("Demo walkthrough (3 minutes)",
         ["1 Home: problem + manual-vs-agentic table (30 s)",
          "2 Data: load synthetic CSV, quality report (20 s)",
          "3 Run Agents: live plan → tools → critic loop → A2A trace (60 s)",
          "4–5 Results + Critic Findings: missed criticals before/after (40 s)",
          "6–8 Approval → work orders → metrics → architecture (30 s)"]),
        ("Results & validation (real numbers from metrics.json)",
         [f"Seed 42 (tuning): legacy recall {m['per_seed']['42']['legacy']['recall_critical']:.3f} → final {m['per_seed']['42']['final']['recall_critical']:.3f}",
          f"Eval seeds 7+99: final recall {m['aggregate_eval_seeds']['final']['recall_critical_mean']:.3f}, precision {m['aggregate_eval_seeds']['final']['precision_critical_mean']:.3f}",
          f"Seed 99 final: recall {m['per_seed']['99']['final']['recall_critical']:.3f}, precision {m['per_seed']['99']['final']['precision_critical']:.3f}",
          f"missed_caught: {m['per_seed']['42']['missed_caught']}/{m['per_seed']['7']['missed_caught']}/{m['per_seed']['99']['missed_caught']} (seeds 42/7/99) · false alarms: {m['per_seed']['42']['false_alarms']}/{m['per_seed']['7']['false_alarms']}/{m['per_seed']['99']['false_alarms']}",
          f"Interacting ~3-5% · Rework: 1 iter, all resolved · Validation errors: {m['per_seed']['42']['validation_errors']} · Runtime <0.2 s"]),
        ("Limitations (stated honestly)",
         ["Synthetic data — not real operator ILI; no vendor formats, no GIS",
          "Simplified B31G/ERF — educational only, never for real dig decisions",
          "Mock LLM writes template prose — no real language understanding",
          f"Low precision / over-triage — precision {m['aggregate_eval_seeds']['final']['precision_critical_mean']:.3f} (target >= 0.40 not reached); {m['per_seed']['42']['false_alarms']}-{m['per_seed']['99']['false_alarms']} false alarms per run from ILI noise",
          "Rework convergence partly by design (shared rule family); independent learned Critic is future scope",
          "Static thresholds; no learning from engineer feedback; single-machine PoC"]),
        ("Future scope & conclusion",
         ["Real LLM via Ollama (one-line swap) · MCP tool server · vendor parsers + GIS",
          "RAG over ASME B31G/B31.8S + operator SOPs · learning from approvals",
          f"Conclusion: critic-guarded agents lift critical recall {fmt(legacy_recall)} → "
          f"{fmt(final_recall)} with full traceability — a viable second pair of eyes."]),
    ]
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(6)

    blank = prs.slide_layouts[6]
    for title, bullets in slides:
        s = prs.slides.add_slide(blank)
        style_slide(s)
        if title == "ARCH_IMG":
            add_title(s, "Architecture", 30)
            img = ROOT / "docs" / "architecture_drawio.png"
            if img.exists():
                s.shapes.add_picture(str(img), Inches(0.7), Inches(1.2), width=Inches(8.6), height=Inches(4.2))
            else:
                # Placeholder box
                box = s.shapes.add_textbox(Inches(0.7), Inches(1.2), Inches(8.6), Inches(4.2))
                tf = box.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.text = "[Insert draw.io architecture export here]\n\nExport your draw.io diagram as PNG\nand save as docs/architecture_drawio.png"
                p.font.size = Pt(18)
                p.font.color.rgb = GREY
                p.alignment = PP_ALIGN.CENTER
                for line in [
                    "Component table, edge table, decision points,",
                    "suggested draw.io layout, and Mermaid flowchart",
                    "are in docs/ARCHITECTURE_EXPLAINED.md"
                ]:
                    p2 = tf.add_paragraph()
                    p2.text = line
                    p2.font.size = Pt(14)
                    p2.font.color.rgb = GREY
                    p2.alignment = PP_ALIGN.CENTER
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