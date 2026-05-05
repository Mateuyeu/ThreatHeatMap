"""Single source of truth for actor scoring.

`compute_score()` is the only function that turns a raw actor record + query
context (sector, time window, client, security override) into the (X, Y)
position rendered on the heat map. Both /api/actors and /api/actor/<id> go
through it, and the UI's detail panel must consume the same values.

P_sect computation rules (sub-pass A, per agreed methodology):
    - Default: P_sect = victims_in_sector / total_victims_in_window
      (dynamic, depends on the selected time window).
    - Fallback: if total_victims_in_window == 0 for the actor, use
      `sector_targeting[<sector>].p_sect` baseline from the fixture.
      The baseline avoids visually erasing actors that are momentarily
      silent but plausibly intent on the sector.
    - The fallback flag is exposed so callers can surface it in the UI.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from . import formulas


def _parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def filter_victims(actor: dict, since: date, sector: Optional[str]) -> Tuple[List[dict], List[dict]]:
    in_window = []
    for v in actor.get("victims", []):
        try:
            vd = _parse_date(v.get("date"))
        except (TypeError, ValueError):
            continue
        if vd >= since:
            in_window.append({**v, "_date": vd.isoformat()})
    in_sector = (
        [v for v in in_window if v.get("sector") == sector]
        if sector
        else []
    )
    return in_window, in_sector


def _baseline_p_sect(actor: dict, sector: str) -> float:
    targeting = actor.get("sector_targeting") or {}
    entry = targeting.get(sector) or {}
    try:
        return float(entry.get("p_sect", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _p_ttp(actor: dict, sector: str) -> float:
    targeting = actor.get("sector_targeting") or {}
    entry = targeting.get(sector) or {}
    try:
        return float(entry.get("p_ttp", 0.0))
    except (TypeError, ValueError):
        return 0.0


def resolve_security_score(actor: dict, client_id: str, override: Optional[float],
                           default_security_score: float) -> Tuple[float, str]:
    if override is not None:
        return float(override), "ui_override"
    overrides = actor.get("security_score_overrides_by_client") or {}
    if client_id in overrides:
        return float(overrides[client_id]), f"client_override:{client_id}"
    actor_default = actor.get("default_security_score")
    if actor_default is not None:
        return float(actor_default), "actor_default"
    return float(default_security_score), "global_default"


def compute_score(actor: dict,
                  sector: str,
                  since: date,
                  client_id: str,
                  security_score_override: Optional[float],
                  default_security_score: float,
                  formula_id: Optional[str] = None) -> Dict:
    """Single source of truth used by every endpoint and the consistency tests.

    Returns a dict with x, y, p_sect, p_ttp, security_score, victim counts,
    and provenance flags (p_sect_source, security_score_source).
    """
    in_window, in_sector = filter_victims(actor, since, sector)
    total_in_window = len(in_window)
    in_sector_count = len(in_sector)

    if total_in_window > 0:
        p_sect = in_sector_count / total_in_window
        p_sect_source = "victims_ratio"
    else:
        p_sect = _baseline_p_sect(actor, sector)
        p_sect_source = "baseline_fallback"

    p_ttp = _p_ttp(actor, sector)
    security_score, security_score_source = resolve_security_score(
        actor, client_id, security_score_override, default_security_score
    )

    y = formulas.compute_intent(p_sect, p_ttp, formula_id=formula_id)
    x = formulas.compute_opportunity(security_score, p_ttp, formula_id=formula_id)

    return {
        "x": round(float(x), 2),
        "y": round(float(y), 2),
        "p_sect": round(float(p_sect), 4),
        "p_ttp": round(float(p_ttp), 4),
        "security_score": round(float(security_score), 2),
        "victims_total_window": total_in_window,
        "victims_in_sector": in_sector_count,
        "p_sect_source": p_sect_source,
        "security_score_source": security_score_source,
        "victims_window": in_window,
        "victims_sector": in_sector,
    }
