"""Independent ground truth model — NO imports from src.tools.risk.

This module computes a hidden TRUE state per anomaly and derives truth_class
using a different formulation than the Critic:
- B31G safe pressure / ERF on the TRUE depth (not observed)
- Estimated time-to-failure (TTF) in years at the TRUE growth rate
- Mapping: IMMEDIATE if ERF_true >= 1.0 or TTF < 1 yr;
         60_DAY if TTF < 2 yrs or ERF_true >= 0.85;
         180_DAY if TTF < 5 yrs or ERF_true >= 0.6 or true_depth >= 40 in HCA/crossing;
         else MONITOR.

The observed columns agents see = true values + measurement noise (ILI sizing tolerance).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

# Local B31G implementation (independent of src.tools.b31g)
def _folias_factor(length_mm: float, diameter_mm: float, wall_mm: float) -> float:
    z = (length_mm**2) / (diameter_mm * wall_mm)
    if z <= 50:
        return math.sqrt(max(1e-9, 1 + 0.6275 * z - 0.003375 * z**2))
    return 0.032 * z + 3.3


def _safe_pressure_mpa(
    depth_pct: float,
    length_mm: float,
    wall_mm: float,
    diameter_mm: float,
    smys_mpa: float,
) -> Optional[float]:
    try:
        if any(v is None for v in (depth_pct, length_mm, wall_mm, diameter_mm, smys_mpa)):
            return None
        if wall_mm <= 0 or diameter_mm <= 0 or length_mm <= 0 or smys_mpa <= 0:
            return None
        d = depth_pct / 100.0
        if d < 0 or d >= 1.0:
            return None
        m = _folias_factor(length_mm, diameter_mm, wall_mm)
        flow = 1.1 * smys_mpa
        p0 = 2 * wall_mm * flow / diameter_mm
        return p0 * (1 - 0.85 * d) / (1 - 0.85 * d / m)
    except (ZeroDivisionError, ValueError):
        return None


def _erf(maop_mpa: Optional[float], safe_p: Optional[float]) -> Optional[float]:
    if maop_mpa is None or safe_p is None or safe_p <= 0:
        return None
    return maop_mpa / safe_p


# Truth-class mapping (different from Critic's full_screen_class)
def _truth_class(
    true_depth_pct: float,
    true_growth_pct_per_yr: float,
    true_erf: float,
    true_hca: bool,
    true_near_road: bool,
    true_near_water: bool,
    true_near_weld: bool,
) -> str:
    # Time to failure (years until ERF reaches 1.0 at current growth)
    # ERF grows as depth increases; approximate linear ERF growth rate
    ttf = float("inf")
    if true_growth_pct_per_yr > 0 and true_erf < 1.0:
        # Depth needed for ERF=1.0: solve for depth where safe_pressure = MAOP
        # Approximate: ERF ~ depth_factor, so years to ERF=1 ~ (1.0 - erf) / erf_growth_rate
        # We'll use a simple depth-based TTF: years until depth reaches 80% (failure threshold)
        depth_to_fail = 80.0
        ttf = max(0.0, (depth_to_fail - true_depth_pct) / true_growth_pct_per_yr)

    if true_erf >= 1.0 or ttf < 1.0:
        return "IMMEDIATE"
    if ttf < 2.0 or true_erf >= 0.85:
        return "60_DAY"
    # Context-aware 180_DAY
    context_flag = true_hca or true_near_road or true_near_water or true_near_weld
    if ttf < 5.0 or true_erf >= 0.6 or (true_depth_pct >= 40.0 and context_flag):
        return "180_DAY"
    return "MONITOR"


# ILI measurement noise model (based on typical ILI sizing tolerances)
# Depth: ~10% of wall thickness at 80% confidence (ASME B31G typical spec)
# Growth: derived from two noisy depth readings
def add_measurement_noise(
    df: pd.DataFrame,
    rng: np.random.Generator,
    depth_noise_pct_of_wall: float = 0.10,
    confidence: float = 0.80,
) -> pd.DataFrame:
    """Add Gaussian noise to true values to produce observed ILI columns.
    
    Depth noise: N(0, sigma) where sigma = depth_noise_pct_of_wall * wall_thickness_mm / 1.28
    (1.28 is the z-score for 80% confidence interval)
    """
    df = df.copy()
    for idx, row in df.iterrows():
        wall = row["wall_thickness_mm"]
        true_depth = row["true_depth_pct"]
        true_prior = row["true_prior_depth_pct"]
        true_growth = row["true_growth_pct_per_yr"]
        years = row["years_between"]

        # Depth noise (percentage points)
        sigma_depth = depth_noise_pct_of_wall * wall / 1.28  # ~10% of wall at 80% CI
        obs_depth = true_depth + rng.normal(0, sigma_depth)
        obs_prior = true_prior + rng.normal(0, sigma_depth)

        # Clip to valid range
        obs_depth = float(np.clip(obs_depth, 0.0, 99.0))
        obs_prior = float(np.clip(obs_prior, 0.0, 99.0))

        # Observed growth from the two noisy readings
        obs_growth = (obs_depth - obs_prior) / years if years > 0 else 0.0

        df.at[idx, "depth_pct"] = round(obs_depth, 1)
        df.at[idx, "prior_depth_pct"] = round(obs_prior, 1)
        df.at[idx, "growth_rate_pct_per_yr"] = round(obs_growth, 2)

    return df


def compute_true_state(
    df: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Generate true (hidden) state for each anomaly and derive truth_class.
    
    Returns dataframe with true_* columns and truth_class.
    """
    df = df.copy()
    true_depths = []
    true_priors = []
    true_growths = []
    true_erfs = []
    truth_classes = []

    for _, row in df.iterrows():
        # True depth: sample from a realistic distribution (similar to observed but without noise)
        # We'll use the observed depth as the true depth for simplicity in generation,
        # but in a real system these would be latent variables.
        # Here we generate true state first, then add noise to get observed.
        pass

    # This function will be called from generate_data.py where true state is generated first
    return df


def generate_true_anomalies(
    seed: int = 42,
    n_total: int = 300,
) -> pd.DataFrame:
    """Generate anomalies with TRUE state (hidden) and observed (noisy) columns.
    
    This is the main entry point for data generation.
    """
    rng = np.random.default_rng(seed)
    rnd = random.Random(seed)

    PIPELINES = {
        "P-14": {"diameter_mm": 610.0, "wall_mm": 9.5, "smys_mpa": 359.0, "maop_mpa": 6.9, "hca_segments": [(8000.0, 14000.0)], "length_m": 40000.0},
        "P-21": {"diameter_mm": 457.0, "wall_mm": 8.0, "smys_mpa": 414.0, "maop_mpa": 7.5, "hca_segments": [(20000.0, 26000.0)], "length_m": 40000.0},
        "P-07": {"diameter_mm": 762.0, "wall_mm": 12.7, "smys_mpa": 317.0, "maop_mpa": 5.2, "hca_segments": [(2000.0, 6000.0)], "length_m": 40000.0},
        "P-33": {"diameter_mm": 323.0, "wall_mm": 6.4, "smys_mpa": 448.0, "maop_mpa": 8.0, "hca_segments": [(30000.0, 38000.0)], "length_m": 40000.0},
    }

    SEVERE_KEYWORDS = ["severe", "sharp", "undercut", "leak", "crack", "deep", "active", "gouge"]

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

    SEV_ORDER = {"MONITOR": 0, "180_DAY": 1, "60_DAY": 2, "IMMEDIATE": 3}
    INV = {v: k for k, v in SEV_ORDER.items()}

    def _downgrade(label: str, steps: int) -> str:
        return INV[max(0, SEV_ORDER[label] - steps)]

    pids = list(PIPELINES.keys())
    rows = []
    per = n_total // len(pids)
    i = 0

    for pid in pids:
        meta = PIPELINES[pid]
        wall = meta["wall_mm"]
        diam = meta["diameter_mm"]
        smys = meta["smys_mpa"]
        maop = meta["maop_mpa"]
        hca_segments = meta["hca_segments"]
        length_m = meta["length_m"]

        for k in range(per):
            i += 1
            aid = f"A-{i:04d}"
            # Chainage in METRES (0-40000)
            chainage = float(rng.uniform(0, length_m))
            clock = round(float(rng.uniform(0, 12)), 1)

            # True depth distribution (mostly shallow, tail of deep)
            u = rng.random()
            if u < 0.55:
                true_depth = float(rng.normal(25, 10))
            elif u < 0.8:
                true_depth = float(rng.normal(50, 8))
            elif u < 0.93:
                true_depth = float(rng.normal(65, 7))
            else:
                true_depth = float(rng.normal(80, 6))
            true_depth = float(np.clip(true_depth, 5, 95))

            length_mm = float(np.clip(rng.normal(120, 70), 20, 450))
            width_mm = float(np.clip(rng.normal(60, 30), 10, 250))
            loc = int(rng.choice([1, 2, 3, 4], p=[0.4, 0.3, 0.2, 0.1]))

            # True HCA from segments
            true_hca = any(lo <= chainage <= hi for lo, hi in hca_segments) or bool(rng.random() < 0.08)
            years = float(rng.choice([3.0, 4.0, 5.0]))

            # True growth rate
            true_growth = float(np.clip(rng.normal(1.5, 1.8), -0.5, 7.0))
            if rng.random() < 0.12:
                true_growth = float(rng.uniform(3.5, 6.5))

            # True prior depth
            true_prior = round(max(2.0, true_depth - true_growth * years + float(rng.normal(0, 1.5))), 1)

            dist_weld = round(float(rng.exponential(12)), 1)
            true_near_road = bool(rng.random() < 0.15)
            true_near_water = bool(rng.random() < 0.12)
            true_near_weld = dist_weld < 5.0

            # True ERF and truth class
            true_safe_p = _safe_pressure_mpa(true_depth, length_mm, wall, diam, smys)
            true_erf = _erf(maop, true_safe_p)
            truth_cls = _truth_class(true_depth, true_growth, true_erf, true_hca, true_near_road, true_near_water, true_near_weld)

            note = rnd.choice(NOTES_CLEAN)

            rows.append(dict(
                anomaly_id=aid, pipeline_id=pid, chainage_m=round(chainage, 1), clock_position=clock,
                # Observed columns (to be filled after noise)
                depth_pct=None, length_mm=round(length_mm, 1), width_mm=round(width_mm, 1),
                wall_thickness_mm=wall, diameter_mm=diam,
                smys_mpa=smys, maop_mpa=maop, location_class=loc,
                hca=true_hca, prior_depth_pct=None, years_between=years,
                dist_weld_m=dist_weld, near_road=true_near_road, near_water=true_near_water,
                inspector_note=note,
                # True state (hidden)
                true_depth_pct=round(true_depth, 1),
                true_prior_depth_pct=round(true_prior, 1),
                true_growth_pct_per_yr=round(true_growth, 2),
                true_erf=round(true_erf, 3) if true_erf else None,
                truth_class=truth_cls,
            ))

    df = pd.DataFrame(rows)

    # Force some genuine spatial clusters (interaction material)
    # Cluster centres in METRES - spacing 0.4m, same clock position for interaction
    cluster_clock = 3.0  # Same clock position for all cluster members
    for cx_pid, cx_ch in [("P-14", 10200.0), ("P-21", 22500.0), ("P-07", 4000.0)]:
        cand = df[df.pipeline_id == cx_pid].head(4)
        for j, idx in enumerate(cand.index):
            df.loc[idx, "chainage_m"] = round(cx_ch + j * 0.4, 1)
            df.loc[idx, "clock_position"] = cluster_clock
            df.loc[idx, "true_depth_pct"] = max(df.loc[idx, "true_depth_pct"], 55 + j * 3)

    # Now add measurement noise to get observed columns
    df = add_measurement_noise(df, rng)

    # Recompute observed ERF and growth from noisy depths (for agent view)
    for idx, row in df.iterrows():
        wall = row["wall_thickness_mm"]
        diam = row["diameter_mm"]
        smys = row["smys_mpa"]
        maop = row["maop_mpa"]
        obs_depth = row["depth_pct"]
        obs_prior = row["prior_depth_pct"]
        years = row["years_between"]
        obs_growth = (obs_depth - obs_prior) / years if years > 0 else 0.0
        obs_safe_p = _safe_pressure_mpa(obs_depth, row["length_mm"], wall, diam, smys)
        obs_erf = _erf(maop, obs_safe_p)
        df.at[idx, "growth_rate_pct_per_yr"] = round(obs_growth, 2)

    # Plant missed criticals (~10% of IMMEDIATE/60_DAY truth)
    df["is_planted_miss"] = False
    crit_idx = df[df.truth_class.isin(["IMMEDIATE", "60_DAY"])].index.tolist()
    rnd.shuffle(crit_idx)
    n_miss = max(8, int(round(len(df) * 0.10)))
    n_miss = min(n_miss, int(len(df) * 0.12), len(crit_idx))

    for idx in crit_idx[:n_miss]:
        df.loc[idx, "is_planted_miss"] = True
        mechanism = rnd.choice(["growth_hca", "note_contradiction", "interaction", "data_entry"])
        if mechanism == "note_contradiction":
            df.loc[idx, "inspector_note"] = rnd.choice(NOTES_SEVERE)
            if df.loc[idx, "depth_pct"] > 62:
                df.loc[idx, "depth_pct"] = round(float(rnd.uniform(48, 60)), 1)
        elif mechanism == "data_entry" and df.loc[idx, "depth_pct"] >= 50:
            df.loc[idx, "depth_pct"] = round(float(df.loc[idx, "depth_pct"]) - rnd.uniform(12, 20), 1)
        elif mechanism == "growth_hca":
            df.loc[idx, "hca"] = True
            df.loc[idx, "prior_depth_pct"] = round(max(2.0, float(df.loc[idx, "depth_pct"]) - rnd.uniform(4.5, 6.5) * float(df.loc[idx, "years_between"])), 1)

    # Legacy labels: mostly match truth_class (on TRUE state) with human lapses
    df["legacy_manual_label"] = df["truth_class"]
    for idx in df.index:
        if rnd.random() < 0.05:
            tc = df.loc[idx, "truth_class"]
            df.loc[idx, "legacy_manual_label"] = _downgrade(tc, 1) if SEV_ORDER[tc] > 0 else tc

    # For planted misses, ensure legacy is downgraded from TRUTH
    for idx in df[df["is_planted_miss"]].index:
        tc = df.loc[idx, "truth_class"]
        df.loc[idx, "legacy_manual_label"] = _downgrade(tc, rnd.choice([1, 1, 2]))

    # Plant ~5% dirty records
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
            df.loc[idx, "depth_pct"] = 850.0
        elif mode == "missing_length":
            df.loc[idx, "length_mm"] = np.nan

    return df.reset_index(drop=True)


import random
import pandas as pd

if __name__ == "__main__":
    df = generate_true_anomalies(seed=42, n_total=300)
    print(f"Generated {len(df)} anomalies")
    print("Truth class distribution:", df["truth_class"].value_counts().to_dict())
    print("Legacy distribution:", df["legacy_manual_label"].value_counts().to_dict())
    print("Planted misses:", int(df["is_planted_miss"].sum()))
    print("Dirty records:", int(df["is_dirty"].sum()))