"""Simplified Modified B31G remaining-strength calculation.

EDUCATIONAL SIMPLIFICATION — NOT for real integrity decisions.
Implements the standard Folias-factor form:

    z = L^2 / (D * t)
    M = sqrt(1 + 0.6275*z - 0.003375*z^2)   if z <= 50
    M = 0.032*z + 3.3                        if z > 50
    Sf = 1.1 * SMYS  (flow stress)
    P_safe = (2*t*Sf/D) * (1 - 0.85*d) / (1 - 0.85*d/M)

where d = depth fraction (depth_pct/100). ERF = MAOP / P_safe.
ERF >= 1.0 means predicted failure at/below MAOP -> IMMEDIATE.
"""
from __future__ import annotations

import math
from typing import Optional


def folias_factor(length_mm: float, diameter_mm: float, wall_mm: float) -> float:
    z = (length_mm**2) / (diameter_mm * wall_mm)
    if z <= 50:
        return math.sqrt(max(1e-9, 1 + 0.6275 * z - 0.003375 * z**2))
    return 0.032 * z + 3.3


def safe_pressure_mpa(
    depth_pct: float,
    length_mm: float,
    wall_mm: float,
    diameter_mm: float,
    smys_mpa: float,
) -> Optional[float]:
    """Return safe (predicted failure) pressure in MPa, or None on bad input."""
    try:
        if any(v is None for v in (depth_pct, length_mm, wall_mm, diameter_mm, smys_mpa)):
            return None
        if wall_mm <= 0 or diameter_mm <= 0 or length_mm <= 0 or smys_mpa <= 0:
            return None
        d = depth_pct / 100.0
        if d < 0 or d >= 1.0:
            return None
        m = folias_factor(length_mm, diameter_mm, wall_mm)
        flow = 1.1 * smys_mpa
        p0 = 2 * wall_mm * flow / diameter_mm
        return p0 * (1 - 0.85 * d) / (1 - 0.85 * d / m)
    except (ZeroDivisionError, ValueError):
        return None


def erf(maop_mpa: Optional[float], safe_p: Optional[float]) -> Optional[float]:
    if maop_mpa is None or safe_p is None or safe_p <= 0:
        return None
    return maop_mpa / safe_p
