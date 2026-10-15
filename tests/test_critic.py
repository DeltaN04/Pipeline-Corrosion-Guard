"""Critic must upgrade executor under-calls with context/note red flags."""
from src.agents.critic import review
from src.llm.provider import get_chat_model

LLM = get_chat_model()


def _enr(aid, **kw):
    base = {"anomaly_id": aid, "pipeline_id": "P-14", "chainage_m": 10.0, "clock_position": 3.0,
            "depth_pct": 55.0, "length_mm": 100.0, "width_mm": 50.0, "wall_thickness_mm": 9.5,
            "diameter_mm": 610.0, "smys_mpa": 359.0, "maop_mpa": 6.9, "location_class": 2,
            "hca": False, "hca_confirmed": False, "near_road": False, "near_water": False,
            "near_weld": False, "interacting": False, "note_severe": False,
            "growth_rate_pct_per_yr": 1.0, "legacy_manual_label": "MONITOR", "quality_flags": []}
    base.update(kw)
    return base


def _risk(aid, cls, erf_v=0.7, depth=55.0):
    return {"anomaly_id": aid, "triage_class": cls, "erf": erf_v, "depth_pct_used": depth}


def test_critic_upgrades_note_contradiction():
    enr = [_enr("A-1", note_severe=True, depth_pct=55.0, legacy_manual_label="MONITOR")]
    verdicts, obj = review(enr, [_risk("A-1", "MONITOR")], LLM)
    assert verdicts[0]["verdict"] == "UPGRADE_REQUIRED"
    assert verdicts[0]["final_class"] == "IMMEDIATE"
    assert verdicts[0]["missed_critical"] is True
    assert len(obj) == 1


def test_critic_upgrades_deep_defect():
    enr = [_enr("A-2", depth_pct=85.0, legacy_manual_label="180_DAY")]
    verdicts, _ = review(enr, [_risk("A-2", "180_DAY", depth=85.0)], LLM)
    assert verdicts[0]["verdict"] == "UPGRADE_REQUIRED"


def test_critic_agrees_clean():
    enr = [_enr("A-3", depth_pct=20.0, growth_rate_pct_per_yr=0.5, legacy_manual_label="MONITOR")]
    verdicts, obj = review(enr, [_risk("A-3", "MONITOR", erf_v=0.3, depth=20.0)], LLM)
    assert verdicts[0]["verdict"] == "AGREE"
    assert obj == []
