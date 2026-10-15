"""B31G hand-computed verification cases (see module docstring for formula)."""
import math

from src.tools.b31g import erf, folias_factor, safe_pressure_mpa


def test_folias_short():
    # L=100, D=500, t=10 -> z=2.0 -> M=sqrt(1+0.6275*2-0.003375*4)
    assert folias_factor(100, 500, 10) == math.sqrt(1 + 0.6275 * 2.0 - 0.003375 * 4.0)


def test_safe_pressure_hand_computed():
    # t=10, D=500, SMYS=350, L=100, depth=50% -> ~12.366 MPa (hand calc in test docstring)
    p = safe_pressure_mpa(50.0, 100.0, 10.0, 500.0, 350.0)
    assert p is not None and abs(p - 12.366) < 0.02


def test_safe_pressure_long_defect():
    # L=400, D=300, t=6, SMYS=400, depth=30% -> z=88.9>50 branch -> ~13.679 MPa
    p = safe_pressure_mpa(30.0, 400.0, 6.0, 300.0, 400.0)
    assert p is not None and abs(p - 13.679) < 0.02


def test_monotonic_depth():
    a = safe_pressure_mpa(30.0, 100.0, 10.0, 500.0, 350.0)
    b = safe_pressure_mpa(70.0, 100.0, 10.0, 500.0, 350.0)
    assert a is not None and b is not None and a > b


def test_erf_logic():
    assert erf(7.0, 14.0) == 0.5
    assert erf(7.0, 7.0) == 1.0
    assert erf(7.0, None) is None
    assert erf(7.0, 0) is None
    assert erf(None, 10.0) is None


def test_bad_inputs_none():
    assert safe_pressure_mpa(None, 100, 10, 500, 350) is None
    assert safe_pressure_mpa(50, 100, -1, 500, 350) is None
    assert safe_pressure_mpa(150, 100, 10, 500, 350) is None
