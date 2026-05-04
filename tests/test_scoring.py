"""Unit tests for scoring/formulas.py."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring import formulas  # noqa: E402


# --- Helpers -------------------------------------------------------------

APPROX = 1e-9


# --- compute_intent (geometric_mean_v1) ---------------------------------

@pytest.mark.parametrize(
    "p_sect,p_ttp,expected",
    [
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 100.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.25, 0.25, 25.0),         # sqrt(0.0625) * 100
        (0.5,  0.5,  math.sqrt(0.25) * 100.0),
        (0.81, 0.49, math.sqrt(0.81 * 0.49) * 100.0),
    ],
)
def test_compute_intent_geometric_mean_v1(p_sect, p_ttp, expected):
    got = formulas.compute_intent(p_sect, p_ttp, formula_id="geometric_mean_v1")
    assert got == pytest.approx(expected, abs=APPROX)


def test_compute_intent_uses_active_formula_by_default():
    explicit = formulas.compute_intent(0.4, 0.6, formula_id=formulas.ACTIVE_FORMULA)
    implicit = formulas.compute_intent(0.4, 0.6)
    assert explicit == pytest.approx(implicit, abs=APPROX)


def test_compute_intent_bounds_geometric_mean_v1():
    # For p in [0,1] x [0,1], result must stay in [0, 100]
    for ps in (0.0, 0.1, 0.5, 0.9, 1.0):
        for pt in (0.0, 0.1, 0.5, 0.9, 1.0):
            y = formulas.compute_intent(ps, pt, formula_id="geometric_mean_v1")
            assert 0.0 <= y <= 100.0 + APPROX


# --- compute_opportunity (geometric_mean_v1) ----------------------------

@pytest.mark.parametrize(
    "sec,p_ttp,expected",
    [
        (0.0,  0.0, 0.0),
        (100.0, 1.0, 100.0),
        (100.0, 0.0, 0.0),
        (0.0,   1.0, 0.0),
        (50.0,  0.5, 25.0),
        (75.0,  0.4, 30.0),
    ],
)
def test_compute_opportunity_geometric_mean_v1(sec, p_ttp, expected):
    got = formulas.compute_opportunity(sec, p_ttp, formula_id="geometric_mean_v1")
    assert got == pytest.approx(expected, abs=APPROX)


def test_compute_opportunity_bounds_geometric_mean_v1():
    for sec in (0.0, 25.0, 50.0, 75.0, 100.0):
        for pt in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = formulas.compute_opportunity(sec, pt, formula_id="geometric_mean_v1")
            assert 0.0 <= x <= 100.0 + APPROX


# --- Formula registry ----------------------------------------------------

def test_active_formula_is_registered():
    assert formulas.ACTIVE_FORMULA in formulas.FORMULAS


def test_each_formula_has_intent_and_opportunity():
    for name, spec in formulas.FORMULAS.items():
        assert "intent" in spec, f"{name} missing 'intent'"
        assert "opportunity" in spec, f"{name} missing 'opportunity'"
        assert callable(spec["intent"])
        assert callable(spec["opportunity"])


def test_unknown_formula_raises():
    with pytest.raises(KeyError):
        formulas.compute_intent(0.5, 0.5, formula_id="not_a_real_formula")
    with pytest.raises(KeyError):
        formulas.compute_opportunity(50.0, 0.5, formula_id="not_a_real_formula")


def test_list_formulas_contains_active():
    listed = formulas.list_formulas()
    assert isinstance(listed, list)
    assert formulas.ACTIVE_FORMULA in listed


# --- String inputs (defensive) ------------------------------------------

def test_compute_intent_accepts_string_inputs():
    # Useful when values arrive from query params as strings
    got = formulas.compute_intent("0.5", "0.5")
    assert got == pytest.approx(50.0, abs=APPROX)


def test_compute_opportunity_accepts_string_inputs():
    got = formulas.compute_opportunity("50", "0.5")
    assert got == pytest.approx(25.0, abs=APPROX)
