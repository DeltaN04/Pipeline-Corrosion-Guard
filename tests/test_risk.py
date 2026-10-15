from src.tools.risk import executor_triage, full_screen_class, project_depth, risk_score


def test_projection():
    assert project_depth(50.0, 3.0, 2.0) == 56.0
    assert project_depth(99.0, 5.0, 2.0) == 100.0  # capped
    assert project_depth(50.0, None) is None


def test_executor_thresholds():
    assert executor_triage(85, 0.5, 1.0, 60) == "IMMEDIATE"
    assert executor_triage(50, 1.05, 1.0, 60) == "IMMEDIATE"  # ERF>=1
    assert executor_triage(65, 0.5, 1.0, 60) == "60_DAY"
    assert executor_triage(45, 0.5, 1.0, 50) == "180_DAY"
    assert executor_triage(20, 0.3, 0.5, 25) == "MONITOR"


def test_full_screen_note_contradiction():
    cls, reasons = full_screen_class(55, 0.7, 1.0, 57, note_severe=True)
    assert cls == "IMMEDIATE"
    assert any("contradict" in r for r in reasons)


def test_full_screen_interaction_context():
    cls, _ = full_screen_class(55, 0.7, 1.0, 57, interacting=True)
    assert cls == "60_DAY"


def test_risk_score_traceable():
    s, factors = risk_score(85, 1.1, 5.0, hca=True, location_class=4, interacting=True, note_severe=True)
    assert 0 <= s <= 100
    assert "HCA" in factors and "ERF>=1.0" in factors
