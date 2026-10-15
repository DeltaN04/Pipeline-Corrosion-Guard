"""Synthetic ILI anomaly generator (seeded, reproducible). SYNTHETIC DATA ONLY.

Ground truth (true_class) comes from full engineering+context rules (src/tools/risk.py).
Legacy manual labels are then deliberately degraded on ~8-12% of criticals to simulate
missed critical defects, and ~5% dirty records are planted for the Research Agent.

Formulas are simplified educational approximations, NOT for real integrity decisions.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.tools.b31g import erf, safe_pressure_mpa
from src.tools.lookup import SEVERE_KEYWORDS
from src.tools.risk import full_screen_class

SEED = 42
N_TOTAL = 300

PIPELINES = {
    "P-14": {"diameter_mm": 610.0, "wall_mm": 9.5, "smys_mpa": 359.0, "maop_mpa": 6.9, "hca": (8.0, 14.0), "km": (0, 40)},
    "P-21": {"diameter_mm": 457.0, "wall_mm": 8.0, "smys_mpa": 414.0, "maop_mpa": 7.5, "hca": (20.0, 26.0), "km": (0, 40)},
    "P-07": {"diameter_mm": 762.0, "wall_mm": 12.7, "smys_mpa": 317.0, "maop_mpa": 5.2, "hca": (2.0, 6.0), "km": (0, 40)},
    "P-33": {"diameter_mm": 323.0, "wall_mm": 6.4, "smys_mpa": 448.0, "maop_mpa": 8.0, "hca": (30.0, 38.0), "km": (0, 40)},
}
SEV_ORDER = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}
INV = {v: k for k, v in SEV_ORDER.items()}

NOTES_CLEAN = [
    "General wall loss, smooth profile.",
    "Moderate pitting cluster, no sharp edges.",
    "External corrosion patch, blunt morphology.",
    "Internal wall loss, general.",
    "Minor pitting, monitor.",
]
NOTES_SEVERE = [
    "Severe sharp undercut at weld toe, active.",
    "Sharp crack-like indication, deep with leak stain nearby.",
    "Severe gouge with undercut edges, active corrosion.",
    "Deep sharp anomaly, severe profile per analyst.",
]


def _downgrade(label: str, steps: int) -> str:
    return INV[max(0, SEV_ORDER[label] - steps)]


def generate(seed: int = SEED, n_total: int = N_TOTAL) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rnd = random.Random(seed)
    pids = list(PIPELINES.keys())
    rows = []
    per = n_total // len(pids)
    i = 0
    for pid in pids:
        meta = PIPELINES[pid]
        for k in range(per):
            i += 1
            aid = f"A-{i:04d}"
            chainage = round(float(rng.uniform(*meta["km"]) * 1000) / 1000, 3)  # km-ish metres 0..40
            clock = round(float(rng.uniform(0, 12)), 1)
            # Depth distribution: mostly shallow, tail of deep defects
            u = rng.random()
            if u < 0.55:
                depth = float(rng.normal(25, 10))
            elif u < 0.8:
                depth = float(rng.normal(50, 8))
            elif u < 0.93:
                depth = float(rng.normal(65, 7))
            else:
                depth = float(rng.normal(80, 6))
            depth = float(np.clip(depth, 5, 95))
            length = float(np.clip(rng.normal(120, 70), 20, 450))
            width = float(np.clip(rng.normal(60, 30), 10, 250))
            loc = int(rng.choice([1, 2, 2, 3, 1, 4], p=[0.35, 0.25, 0.15, 0.1, 0.1, 0.05]) if False else rng.choice([1, 1, 2, 2, 3, 1, 4]))
            lo, hi = meta["hca"]
            hca = bool(lo <= chainage <= hi) or bool(rng.random() < 0.08)
            years = float(rng.choice([3.0, 4.0, 5.0]))
            growth = float(np.clip(rng.normal(1.5, 1.8), -0.5, 7.0))
            if rng.random() < 0.12:  # rapid growers
                growth = float(rng.uniform(3.5, 6.5))
            prior = round(max(2.0, depth - growth * years + float(rng.normal(0, 1.5))), 1)
            dist_weld = round(float(rng.exponential(12)), 1)
            near_road = bool(rng.random() < 0.15)
            near_water = bool(rng.random() < 0.12)
            note = rnd.choice(NOTES_CLEAN)
            rows.append(
                dict(
                    anomaly_id=aid, pipeline_id=pid, chainage_m=chainage, clock_position=clock,
                    depth_pct=round(depth, 1), length_mm=round(length, 1), width_mm=round(width, 1),
                    wall_thickness_mm=meta["wall_mm"], diameter_mm=meta["diameter_mm"],
                    smys_mpa=meta["smys_mpa"], maop_mpa=meta["maop_mpa"], location_class=loc,
                    hca=hca, prior_depth_pct=prior, years_between=years,
                    dist_weld_m=dist_weld, near_road=near_road, near_water=near_water,
                    inspector_note=note,
                )
            )
    df = pd.DataFrame(rows)
    # Force some spatial clusters so interaction detection has material.
    for cx_pid, cx_ch in [("P-14", 10.2), ("P-21", 22.5), ("P-07", 4.0)]:
        cand = df[df.pipeline_id == cx_pid].head(4)
        for j, idx in enumerate(cand.index):
            df.loc[idx, "chainage_m"] = round(cx_ch + j * 0.4, 3)
            df.loc[idx, "depth_pct"] = max(df.loc[idx, "depth_pct"], 55 + j * 3)
    # Compute provisional ground truth (interaction TBD after clustering; recompute below).
    df["_interim_growth"] = (df.depth_pct - df.prior_depth_pct) / df.years_between
    # Temporary interaction via same rounding trick for ground truth only.
    df["_cl"] = (df.chainage_m).round(0)
    df["_interacting"] = df.duplicated(subset=["pipeline_id", "_cl"], keep=False)
    true_classes = []
    for _, r in df.iterrows():
        sp = safe_pressure_mpa(r.depth_pct, r.length_mm, r.wall_mm if "wall_mm" in r else r.wall_thickness_mm,
                               r.diameter_mm, r.smys_mpa)
        e = erf(r.maop_mpa, sp)
        g = (r.depth_pct - r.prior_depth_pct) / r.years_between
        proj = min(100.0, r.depth_pct + g * 2.0)
        sev_flags = any(k in str(r.inspector_note).lower() for k in SEVERE_KEYWORDS)
        cls, _ = full_screen_class(r.depth_pct, e, g, proj, bool(r.hca), bool(r.near_road),
                                   bool(r.near_water), bool(r.dist_weld_m < 5), bool(r["_interacting"]), sev_flags)
        true_classes.append(cls)
    df["true_class"] = true_classes
    # Plant missed criticals: downgrade legacy on ~10% of IMMEDIATE/60_DAY.
    df["is_planted_miss"] = False
    crit_idx = df[df.true_class.isin(["IMMEDIATE", "60_DAY"])].index.tolist()
    rnd.shuffle(crit_idx)
    n_miss = max(8, int(round(len(df) * 0.10)))
    # Ensure at least 8 and at most 12% of total.
    n_miss = min(n_miss, int(len(df) * 0.12), len(crit_idx))
    for idx in crit_idx[:n_miss]:
        tc = df.loc[idx, "true_class"]
        df.loc[idx, "is_planted_miss"] = True
        mechanism = rnd.choice(["growth_hca", "note_contradiction", "interaction", "data_entry"])
        if mechanism == "note_contradiction":
            # Keep numeric depth moderate but write a severe note (legacy reviewer trusted the number).
            df.loc[idx, "inspector_note"] = rnd.choice(NOTES_SEVERE)
            if df.loc[idx, "depth_pct"] > 62:
                df.loc[idx, "depth_pct"] = round(float(rnd.uniform(48, 60)), 1)
        elif mechanism == "data_entry" and df.loc[idx, "depth_pct"] >= 50:
            df.loc[idx, "depth_pct"] = round(float(df.loc[idx, "depth_pct"]) - rnd.uniform(12, 20), 1)
        elif mechanism == "growth_hca":
            df.loc[idx, "hca"] = True
            # steepen growth by lowering prior depth
            df.loc[idx, "prior_depth_pct"] = round(max(2.0, float(df.loc[idx, "depth_pct"]) - rnd.uniform(4.5, 6.5) * float(df.loc[idx, "years_between"])), 1)
        df.loc[idx, "legacy_manual_label"] = _downgrade(tc, rnd.choice([1, 1, 2]))
    # Non-missed rows: legacy mostly equals truth with small noise.
    for idx in df.index:
        if "legacy_manual_label" not in df.columns or pd.isna(df.loc[idx, "legacy_manual_label"] if "legacy_manual_label" in df.columns else None):
            tc = df.loc[idx, "true_class"]
            if rnd.random() < 0.05:
                df.loc[idx, "legacy_manual_label"] = _downgrade(tc, 1) if SEV_ORDER[tc] > 0 else tc
            else:
                df.loc[idx, "legacy_manual_label"] = tc
    # Recompute true_class AFTER planted edits (so truth reflects final numbers).
    retrues = []
    for _, r in df.iterrows():
        sp = safe_pressure_mpa(r.depth_pct, r.length_mm, r.wall_thickness_mm, r.diameter_mm, r.smys_mpa)
        e = erf(r.maop_mpa, sp)
        g = (r.depth_pct - r.prior_depth_pct) / r.years_between
        proj = min(100.0, r.depth_pct + g * 2.0)
        sev_flags = any(k in str(r.inspector_note).lower() for k in SEVERE_KEYWORDS)
        cls, _ = full_screen_class(r.depth_pct, e, g, proj, bool(r.hca), bool(r.near_road),
                                   bool(r.near_water), bool(r.dist_weld_m < 5), False, sev_flags)
        retrues.append(cls)
    # Keep interaction out of generator truth (conservative) but planted interaction rows:
    # mark rows near cluster centres as interacting-context criticals via depth bump already applied.
    df["true_class"] = retrues
    # Fix planted-miss flags: keep only rows where legacy < true after recompute; top-up if short.
    sev = lambda c: SEV_ORDER[c]
    df["is_planted_miss"] = df.apply(lambda r: bool(sev(r["legacy_manual_label"]) < sev(r["true_class"])), axis=1)
    short = max(0, 24 - int(df["is_planted_miss"].sum()))
    if short:
        cand = df[(~df["is_planted_miss"]) & df.true_class.isin(["IMMEDIATE", "60_DAY"])].index.tolist()
        rnd.shuffle(cand)
        for idx in cand[:short]:
            df.loc[idx, "legacy_manual_label"] = _downgrade(df.loc[idx, "true_class"], 1)
            df.loc[idx, "is_planted_miss"] = True
    # Plant ~5% dirty records.
    df["is_dirty"] = False
    all_idx = df.index.tolist()
    rnd.shuffle(all_idx)
    for idx in all_idx[: max(1, int(len(df) * 0.05))]:
        df.loc[idx, "is_dirty"] = True
        mode = rnd.choice(["missing_prior", "neg_depth", "unit_depth", "missing_length"])
        if mode == "missing_prior":
            df.loc[idx, "prior_depth_pct"] = np.nan
        elif mode == "neg_depth":
            df.loc[idx, "depth_pct"] = -5.0
        elif mode == "unit_depth":
            df.loc[idx, "depth_pct"] = 850.0  # mm entered as %
        elif mode == "missing_length":
            df.loc[idx, "length_mm"] = np.nan
    df = df.drop(columns=["_interim_growth", "_cl", "_interacting"])
    return df.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_TOTAL)
    ap.add_argument("--out", default=str(Path(__file__).parent / "ili_anomalies.csv"))
    args = ap.parse_args()
    df = generate(seed=args.seed, n_total=args.n)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out} | missed={int(df.is_planted_miss.sum())} dirty={int(df.is_dirty.sum())}")
    print(df["true_class"].value_counts().to_dict())
    print("legacy:", df["legacy_manual_label"].value_counts().to_dict())


if __name__ == "__main__":
    main()
