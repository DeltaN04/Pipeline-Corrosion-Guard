"""Pydantic schemas for every agent input/output. Malformed outputs are rejected and logged."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

TriageClass = Literal["IMMEDIATE", "60_DAY", "180_DAY", "MONITOR"]
Verdict = Literal["AGREE", "DOWNGRADE_RISK", "UPGRADE_REQUIRED"]


class Anomaly(BaseModel):
    anomaly_id: str
    pipeline_id: str
    chainage_m: float
    clock_position: float = Field(ge=0, le=12)
    depth_pct: Optional[float] = None
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    wall_thickness_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    smys_mpa: Optional[float] = None
    maop_mpa: Optional[float] = None
    location_class: Optional[int] = Field(default=None, ge=1, le=4)
    hca: Optional[bool] = None
    prior_depth_pct: Optional[float] = None
    years_between: Optional[float] = None
    dist_weld_m: Optional[float] = None
    near_road: Optional[bool] = None
    near_water: Optional[bool] = None
    inspector_note: Optional[str] = ""
    legacy_manual_label: Optional[str] = None


class EnrichedAnomaly(Anomaly):
    growth_rate_pct_per_yr: Optional[float] = None
    interacting: bool = False
    interacting_with: List[str] = Field(default_factory=list)
    note_flags: List[str] = Field(default_factory=list)
    quality_flags: List[str] = Field(default_factory=list)
    hca_confirmed: Optional[bool] = None
    location_class_confirmed: Optional[int] = None


class RiskResult(BaseModel):
    anomaly_id: str
    safe_pressure_mpa: Optional[float] = None
    erf: Optional[float] = None
    depth_pct_used: Optional[float] = None
    projected_depth_pct_2yr: Optional[float] = None
    risk_score: float = Field(ge=0, le=100)
    risk_factors: List[str] = Field(default_factory=list)
    triage_class: TriageClass
    rationale: str = ""
    trace: Dict[str, Any] = Field(default_factory=dict)


class CriticVerdict(BaseModel):
    anomaly_id: str
    executor_class: TriageClass
    critic_screen_class: TriageClass
    legacy_label: Optional[str] = None
    verdict: Verdict
    reasons: List[str] = Field(default_factory=list)
    missed_critical: bool = False
    escalated: bool = False
    final_class: TriageClass

    @field_validator("missed_critical", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> bool:
        return bool(v)


class WorkOrder(BaseModel):
    work_order_id: str
    anomaly_id: str
    pipeline_id: str
    chainage_m: float
    priority: TriageClass
    recommended_action: str
    due_date: str
    location_detail: str = ""
    status: str = "PENDING_APPROVAL"


class TaskPlan(BaseModel):
    request: str
    tasks: List[Dict[str, str]]
    routing: str = "small_batch"
    deep_checks: bool = True


class AgentMessage(BaseModel):
    trace_id: str
    sender: str
    receiver: str
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
