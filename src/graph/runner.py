"""Headless runner: run the full graph without Streamlit (smoke tests, metrics, report numbers)."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd


def df_to_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    recs = df.to_dict(orient="records")
    # Normalise NaN -> None so pydantic/tools behave.
    out = []
    for r in recs:
        d = {}
        for k, v in r.items():
            try:
                import math

                if isinstance(v, float) and math.isnan(v):
                    d[k] = None
                    continue
            except Exception:
                pass
            d[k] = v
        # coerce bool-ish columns
        for b in ("hca", "near_road", "near_water"):
            if d.get(b) is not None:
                d[b] = bool(d[b])
        out.append(d)
    return out


def run_triage(df: pd.DataFrame, request: str = "Triage run ILI-2026-03 for pipeline P-14",
               human_decisions: Dict[str, str] | None = None, verbose: bool = False) -> Dict[str, Any]:
    from src.graph.builder import build_graph

    graph = build_graph()
    state: Dict[str, Any] = {
        "request": request,
        "trace_id": uuid.uuid4().hex[:8],
        "anomalies": df_to_anomalies(df),
        "human_decisions": human_decisions or {},
    }
    t0 = time.time()
    final = graph.invoke(state)
    dt = time.time() - t0
    final["elapsed_s"] = round(dt, 2)
    if verbose:
        print(f"Done in {dt:.1f}s | iter={final.get('iteration')} verdicts={len(final.get('verdicts', []))}")
    return final


def default_csv() -> Path:
    here = Path(__file__).resolve()
    for cand in [here.parent / "data" / "ili_anomalies.csv", Path("data/ili_anomalies.csv"),
                 Path("corrosionguard/data/ili_anomalies.csv")]:
        if cand.exists():
            return cand
    return Path("data/ili_anomalies.csv")


if __name__ == "__main__":
    import sys

    p = Path(sys.argv[1]) if len(sys.argv) > 1 else default_csv()
    df = pd.read_csv(p)
    final = run_triage(df, verbose=True)
    print("metrics:", final.get("metrics"))
    print("outputs:", final.get("outputs"))
