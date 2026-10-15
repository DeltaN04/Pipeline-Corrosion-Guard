"""Render docs/architecture.png with matplotlib (offline, no graphviz binary needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.patches as mp
import matplotlib.pyplot as plt


def box(ax, xy, w, h, text, fc="#EAF2FF", ec="#1F4E9C", fs=8, style="round"):
    x, y = xy
    ax.add_patch(mp.FancyBboxPatch((x, y), w, h, boxstyle=f"{style},pad=0.02",
                                   fc=fc, ec=ec, lw=1.5))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight="bold",
            color="#16305e", wrap=True)


def arrow(ax, a, b):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="->", color="#333", lw=1.4))


def main() -> None:
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")
    fig.suptitle("CorrosionGuard — Agentic Architecture (offline PoC)", fontsize=13, weight="bold")

    # Main pipeline (left -> right, top row loops down)
    box(ax, (0.3, 5.6), 1.7, 1.0, "User / UI\n(Streamlit)")
    box(ax, (2.4, 5.6), 1.7, 1.0, "Planner\ntask plan + routing")
    box(ax, (4.5, 5.6), 1.7, 1.0, "Research\nlookup·growth\nHCA·cluster·QA")
    box(ax, (6.6, 5.6), 1.7, 1.0, "Executor\nB31G·ERF·risk\ntriage")
    box(ax, (8.7, 5.6), 1.7, 1.0, "Critic\nre-screen\nAGREE/UPGRADE", fc="#FFF3E0", ec="#B26A00")
    box(ax, (10.8, 5.6), 1.7, 1.0, "Human gate\napprove\nIMMEDIATE", fc="#F3E8FF", ec="#6A1B9A")
    box(ax, (10.8, 3.4), 1.7, 1.0, "Automation\nWO·report\nnotify")
    box(ax, (8.7, 3.4), 1.7, 1.0, "Outputs\nCSV·MD·JSON", fc="#E8F5E9", ec="#2E7D32")
    # Side rails
    box(ax, (0.3, 3.4), 1.7, 1.0, "A2A bus\ntyped msgs\n+ trace", fc="#F5F5F5", ec="#616161")
    box(ax, (2.4, 3.4), 1.7, 1.0, "Tools\nb31g·risk\nlookup·cluster", fc="#F5F5F5", ec="#616161")
    box(ax, (4.5, 3.4), 1.7, 1.0, "Data stores\nILI CSV\nHCA map", fc="#F5F5F5", ec="#616161")
    box(ax, (6.6, 3.4), 2.0, 1.0, "Mock LLM\n(rule templates)\n↔ Ollama later", fc="#F5F5F5", ec="#616161")

    for a, b in [((2.0, 6.1), (2.4, 6.1)), ((4.1, 6.1), (4.5, 6.1)), ((6.2, 6.1), (6.6, 6.1)),
                 ((8.3, 6.1), (8.7, 6.1)), ((10.4, 6.1), (10.8, 6.1)), ((11.65, 5.6), (11.65, 4.4)),
                 ((10.8, 3.9), (10.4, 3.9))]:
        arrow(ax, a, b)
    # Critic loop-back (the key feedback edge)
    ax.annotate("", xy=(7.45, 5.6), xytext=(9.55, 5.45),
                arrowprops=dict(arrowstyle="->", color="#C62828", lw=2.0,
                                connectionstyle="arc3,rad=0.55"))
    ax.text(8.5, 4.85, "UPGRADE_REQUIRED → rework (≤2) else ESCALATE", fontsize=7.5,
            color="#C62828", ha="center", weight="bold")
    # Diamond decision note
    ax.text(8.5, 7.05, "conditional edge: critic verdict router", fontsize=8, style="italic",
            ha="center", color="#333")
    ax.text(6.5, 1.9, "Data flow: request → plan → enriched → risk → verdicts → approvals → work orders · "
            "every handoff via A2A envelope; LLM behind one-line provider swap",
            fontsize=7.5, ha="center", color="#333")
    ax.text(6.5, 1.2, "SYNTHETIC data · SIMPLIFIED formulas (educational only, not for real integrity decisions)",
            fontsize=7.5, ha="center", color="#C62828", weight="bold")
    out = Path(__file__).resolve().parent / "architecture.png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
