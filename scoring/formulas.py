"""Scoring formulas for the heat map.

Each formula is a dict with two callables and an optional metadata block:
    - intent(p_sect, p_ttp) -> float in [0, 100]
    - opportunity(security_score, p_ttp) -> float in [0, 100]
    - meta: {"floor_epsilon": float | None, "description": str}

Inputs:
    p_sect          : float in [0, 1]    - probability the actor targets the sector
    p_ttp           : float in [0, 1]    - sector-specific TTP relevance for the actor
    security_score  : float in [0, 100]  - external exposure score for (actor, client)

Add a new formula by adding an entry to FORMULAS and switching ACTIVE_FORMULA
in config.py. No caller code should need to change.
"""

import math

FLOOR_EPSILON_V1 = 0.05

FORMULAS = {
    "geometric_mean_v1": {
        "intent": lambda p_sect, p_ttp: math.sqrt(p_sect * p_ttp) * 100.0,
        "opportunity": lambda security_score, p_ttp: security_score * p_ttp,
        "meta": {
            "floor_epsilon": None,
            "description": "Pure geometric mean. Collapses to 0 as soon as either probability is 0.",
        },
    },
    "geometric_mean_floored_v1": {
        "intent": lambda p_sect, p_ttp, eps=FLOOR_EPSILON_V1: math.sqrt(max(p_sect, eps) * max(p_ttp, eps)) * 100.0,
        "opportunity": lambda security_score, p_ttp: security_score * p_ttp,
        "meta": {
            "floor_epsilon": FLOOR_EPSILON_V1,
            "description": (
                f"Geometric mean with a floor epsilon = {FLOOR_EPSILON_V1} on each "
                "probability. Avoids fully zeroing out actors that are temporarily "
                "silent but plausibly targeting the sector."
            ),
        },
    },
}

ACTIVE_FORMULA = "geometric_mean_floored_v1"


def _get_formula(formula_id):
    fid = formula_id or ACTIVE_FORMULA
    if fid not in FORMULAS:
        raise KeyError(
            f"Unknown formula '{fid}'. Available: {sorted(FORMULAS.keys())}"
        )
    return FORMULAS[fid]


def compute_intent(p_sect, p_ttp, formula_id=None):
    return _get_formula(formula_id)["intent"](float(p_sect), float(p_ttp))


def compute_opportunity(security_score, p_ttp, formula_id=None):
    return _get_formula(formula_id)["opportunity"](
        float(security_score), float(p_ttp)
    )


def list_formulas():
    return sorted(FORMULAS.keys())


def formula_meta(formula_id=None):
    return _get_formula(formula_id).get("meta", {})
