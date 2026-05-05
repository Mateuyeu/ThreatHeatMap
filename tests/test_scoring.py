"""Unit tests for scoring/formulas.py and scoring/scorer.py."""

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scoring import formulas  # noqa: E402
from scoring.scorer import compute_score  # noqa: E402


APPROX = 1e-9


# --- compute_intent (geometric_mean_v1) ---------------------------------

@pytest.mark.parametrize(
    "p_sect,p_ttp,expected",
    [
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 100.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.25, 0.25, 25.0),
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


# --- compute_intent (geometric_mean_floored_v1) -------------------------

def test_floored_formula_is_active_default():
    assert formulas.ACTIVE_FORMULA == "geometric_mean_floored_v1"


def test_floor_epsilon_value():
    meta = formulas.formula_meta("geometric_mean_floored_v1")
    assert meta["floor_epsilon"] == pytest.approx(0.05, abs=APPROX)


def test_floored_intent_zero_zero_uses_floor():
    # sqrt(0.05 * 0.05) * 100 = 0.05 * 100 = 5.0
    got = formulas.compute_intent(0.0, 0.0, formula_id="geometric_mean_floored_v1")
    assert got == pytest.approx(5.0, abs=APPROX)


@pytest.mark.parametrize(
    "p_sect,p_ttp",
    [
        (0.0, 0.0), (0.0, 0.5), (0.5, 0.0),
        (0.05, 0.05), (0.05, 0.5), (0.5, 0.05),
    ],
)
def test_floored_intent_never_below_floor_score(p_sect, p_ttp):
    eps = 0.05
    got = formulas.compute_intent(p_sect, p_ttp, formula_id="geometric_mean_floored_v1")
    floor_value = math.sqrt(eps * eps) * 100.0
    assert got >= floor_value - APPROX


def test_floored_intent_matches_unfloored_when_above_eps():
    # If both inputs are >= 0.05 strictly, floor has no effect.
    got_floored = formulas.compute_intent(0.5, 0.5, formula_id="geometric_mean_floored_v1")
    got_v1 = formulas.compute_intent(0.5, 0.5, formula_id="geometric_mean_v1")
    assert got_floored == pytest.approx(got_v1, abs=APPROX)


def test_floored_intent_at_unit_inputs():
    got = formulas.compute_intent(1.0, 1.0, formula_id="geometric_mean_floored_v1")
    assert got == pytest.approx(100.0, abs=APPROX)


# --- Bounds (degenerate cases) ------------------------------------------

@pytest.mark.parametrize("formula_id", ["geometric_mean_v1", "geometric_mean_floored_v1"])
def test_intent_within_bounds(formula_id):
    for ps in (0.0, 0.1, 0.5, 0.9, 1.0):
        for pt in (0.0, 0.1, 0.5, 0.9, 1.0):
            y = formulas.compute_intent(ps, pt, formula_id=formula_id)
            assert 0.0 <= y <= 100.0 + APPROX


@pytest.mark.parametrize("formula_id", ["geometric_mean_v1", "geometric_mean_floored_v1"])
def test_opportunity_within_bounds(formula_id):
    for sec in (0.0, 25.0, 50.0, 75.0, 100.0):
        for pt in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = formulas.compute_opportunity(sec, pt, formula_id=formula_id)
            assert 0.0 <= x <= 100.0 + APPROX


def test_opportunity_at_unit_inputs():
    assert formulas.compute_opportunity(100.0, 1.0) == pytest.approx(100.0, abs=APPROX)


def test_opportunity_at_unit_p_ttp_returns_security_score():
    # Property: when P_ttp = 1.0, opportunity == SecurityScore.
    for sec in (0.0, 25.0, 50.0, 75.0, 100.0):
        assert formulas.compute_opportunity(sec, 1.0) == pytest.approx(sec, abs=APPROX)


def test_intent_at_unit_inputs_all_formulas():
    for fid in formulas.list_formulas():
        assert formulas.compute_intent(1.0, 1.0, formula_id=fid) == pytest.approx(100.0, abs=APPROX)


# --- Random sweep -------------------------------------------------------

def test_random_sweep_outputs_in_bounds():
    import random
    random.seed(20260504)
    for _ in range(100):
        ps = random.random()
        pt = random.random()
        sec = random.random() * 100.0
        for fid in formulas.list_formulas():
            y = formulas.compute_intent(ps, pt, formula_id=fid)
            x = formulas.compute_opportunity(sec, pt, formula_id=fid)
            assert 0.0 <= y <= 100.0 + APPROX
            assert 0.0 <= x <= 100.0 + APPROX


# --- Formula registry ---------------------------------------------------

def test_active_formula_is_registered():
    assert formulas.ACTIVE_FORMULA in formulas.FORMULAS


def test_each_formula_has_intent_opportunity_and_meta():
    for name, spec in formulas.FORMULAS.items():
        assert "intent" in spec, f"{name} missing 'intent'"
        assert "opportunity" in spec, f"{name} missing 'opportunity'"
        assert "meta" in spec, f"{name} missing 'meta'"
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
    assert "geometric_mean_v1" in listed
    assert "geometric_mean_floored_v1" in listed


def test_compute_intent_accepts_string_inputs():
    got = formulas.compute_intent("0.5", "0.5", formula_id="geometric_mean_v1")
    assert got == pytest.approx(50.0, abs=APPROX)


# --- compute_score (single source of truth) -----------------------------

TODAY = date(2026, 5, 4)


def _actor():
    return {
        "id": "test_actor",
        "name": "Test Actor",
        "default_security_score": 60,
        "security_score_overrides_by_client": {"telecom_eu": 70},
        "sector_targeting": {
            "Telecommunications": {"p_sect": 0.20, "p_ttp": 0.50},
            "Banking":            {"p_sect": 0.30, "p_ttp": 0.70},
        },
        "victims": [
            {"name": "V1", "sector": "Banking",            "date": "2026-04-01"},
            {"name": "V2", "sector": "Telecommunications", "date": "2026-03-01"},
            {"name": "V3", "sector": "Banking",            "date": "2026-02-01"},
        ],
    }


def test_compute_score_uses_victim_ratio_when_victims_in_window():
    since = TODAY - timedelta(days=180)  # 6 months
    res = compute_score(
        _actor(), "Telecommunications", since, "default", None, 50,
        formula_id="geometric_mean_v1",
    )
    # 1 telecom out of 3 in-window victims -> P_sect = 1/3
    assert res["p_sect_source"] == "victims_ratio"
    assert res["p_sect"] == pytest.approx(1 / 3, abs=1e-4)
    assert res["p_ttp"] == pytest.approx(0.50, abs=APPROX)
    # Y = sqrt(1/3 * 0.5) * 100
    assert res["y"] == pytest.approx(math.sqrt(1 / 3 * 0.5) * 100.0, abs=0.01)


def test_compute_score_fallback_when_no_victims_in_window():
    # Window in the far future -> no victims -> baseline p_sect kicks in
    since = date(2030, 1, 1)
    res = compute_score(
        _actor(), "Telecommunications", since, "default", None, 50,
        formula_id="geometric_mean_v1",
    )
    assert res["p_sect_source"] == "baseline_fallback"
    assert res["p_sect"] == pytest.approx(0.20, abs=APPROX)


def test_compute_score_security_score_resolution_order():
    actor = _actor()
    since = TODAY - timedelta(days=180)
    # ui_override wins over everything
    r1 = compute_score(actor, "Banking", since, "telecom_eu", 99.0, 50)
    assert r1["security_score"] == pytest.approx(99.0)
    assert r1["security_score_source"] == "ui_override"
    # client override picks up when no UI override
    r2 = compute_score(actor, "Banking", since, "telecom_eu", None, 50)
    assert r2["security_score"] == pytest.approx(70.0)
    assert r2["security_score_source"] == "client_override:telecom_eu"
    # actor default when no client override
    r3 = compute_score(actor, "Banking", since, "default", None, 50)
    assert r3["security_score"] == pytest.approx(60.0)
    assert r3["security_score_source"] == "actor_default"
    # global default when actor has none
    actor_no_default = {**actor}
    actor_no_default.pop("default_security_score")
    actor_no_default["security_score_overrides_by_client"] = {}
    r4 = compute_score(actor_no_default, "Banking", since, "default", None, 50)
    assert r4["security_score"] == pytest.approx(50.0)
    assert r4["security_score_source"] == "global_default"


def test_compute_score_returns_within_bounds():
    actor = _actor()
    since = TODAY - timedelta(days=180)
    for fid in formulas.list_formulas():
        for sector in ("Banking", "Telecommunications", "Healthcare"):
            res = compute_score(actor, sector, since, "default", None, 50, formula_id=fid)
            assert 0.0 <= res["x"] <= 100.0 + APPROX
            assert 0.0 <= res["y"] <= 100.0 + APPROX


def test_compute_score_unknown_sector_returns_zero_targeting():
    # Unknown sector -> p_ttp=0, p_sect baseline=0 (no entry); under floored
    # formula y == sqrt(eps*eps)*100 == 5.0
    since = TODAY - timedelta(days=3650)  # very large window so victims included
    res = compute_score(_actor(), "Healthcare", since, "default", None, 50,
                        formula_id="geometric_mean_floored_v1")
    assert res["p_ttp"] == pytest.approx(0.0, abs=APPROX)
    assert res["y"] == pytest.approx(5.0, abs=0.01)
