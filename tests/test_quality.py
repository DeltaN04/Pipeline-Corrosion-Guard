from src.tools.quality import validate_record

BASE = {"depth_pct": 50.0, "length_mm": 100.0, "width_mm": 50.0, "wall_thickness_mm": 9.5,
        "diameter_mm": 610.0, "smys_mpa": 359.0, "maop_mpa": 6.9, "prior_depth_pct": 40.0}


def test_clean():
    assert validate_record(dict(BASE)) == []


def test_missing():
    r = dict(BASE, depth_pct=None)
    assert any("MISSING:depth_pct" in f for f in validate_record(r))


def test_negative_depth():
    assert any("negative_depth" in f for f in validate_record(dict(BASE, depth_pct=-5.0)))


def test_unit_error_depth():
    assert any("UNIT_ERROR" in f for f in validate_record(dict(BASE, depth_pct=850.0)))


def test_wall_unit_suspect():
    assert any("wall_mm" in f for f in validate_record(dict(BASE, wall_thickness_mm=200.0)))
