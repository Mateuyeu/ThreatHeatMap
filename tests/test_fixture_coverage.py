"""Lock in the per-sector distribution constraints from patch v1.1.

Computed against the live fixture (no schema validation here yet — that ships
in sub-pass B). If the fixture is regenerated, these tests must still pass.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as appmod  # noqa: E402
from scoring.scorer import compute_score  # noqa: E402

TODAY = date(2026, 5, 4)
SIX_MONTHS = TODAY - timedelta(days=180)


@pytest.fixture(scope="module")
def fixture_data():
    return appmod._load_fixture()


def _p_sects(fixture, sector, since):
    return [
        compute_score(a, sector, since, "default", None, 50)["p_sect"]
        for a in fixture["actors"]
    ]


def test_at_least_50_total_victims(fixture_data):
    total = sum(len(a.get("victims", [])) for a in fixture_data["actors"])
    assert total >= 50, f"only {total} victims in fixture"


def test_victim_dates_span_18_to_24_months(fixture_data):
    dates = []
    for a in fixture_data["actors"]:
        for v in a.get("victims", []):
            dates.append(datetime.strptime(v["date"], "%Y-%m-%d").date())
    span_days = (max(dates) - min(dates)).days
    assert 18 * 30 <= span_days <= 24 * 30 + 31, (
        f"victim date span is {span_days} days, expected 540..751"
    )


def test_telecom_6mo_at_least_8_actors_with_p_sect_above_threshold(fixture_data):
    above = [p for p in _p_sects(fixture_data, "Telecommunications", SIX_MONTHS) if p >= 0.10]
    assert len(above) >= 8, f"only {len(above)} actors with P_sect >= 0.10 on Telecommunications 6mo"


@pytest.mark.parametrize("sector", [
    "Banking", "Healthcare", "Energy", "Manufacturing", "Public Administration",
])
def test_main_sectors_6mo_at_least_6_actors_with_p_sect(fixture_data, sector):
    above = [p for p in _p_sects(fixture_data, sector, SIX_MONTHS) if p >= 0.10]
    assert len(above) >= 6, f"only {len(above)} actors with P_sect >= 0.10 on {sector} 6mo"


def test_actor_type_enum_values_only(fixture_data):
    allowed = {"state-sponsored", "ransomware", "hacktivist", "cybercriminal", "unknown"}
    for a in fixture_data["actors"]:
        assert a["type"] in allowed, f"actor {a['id']} has invalid type {a['type']!r}"


def test_actor_ids_are_url_safe_slugs(fixture_data):
    import re
    pat = re.compile(r"^[a-z0-9_]+$")
    for a in fixture_data["actors"]:
        assert pat.match(a["id"]), f"actor id {a['id']!r} is not a URL-safe slug"


def test_sector_targeting_values_in_unit_interval(fixture_data):
    for a in fixture_data["actors"]:
        for sector, entry in a.get("sector_targeting", {}).items():
            for k in ("p_sect", "p_ttp"):
                v = entry.get(k)
                assert v is None or 0.0 <= v <= 1.0, (
                    f"actor {a['id']} sector {sector} field {k} = {v!r} out of [0,1]"
                )


def test_default_security_score_in_zero_hundred(fixture_data):
    for a in fixture_data["actors"]:
        sec = a.get("default_security_score")
        assert sec is None or 0 <= sec <= 100
        for client_id, val in (a.get("security_score_overrides_by_client") or {}).items():
            assert 0 <= val <= 100, (
                f"actor {a['id']} override for {client_id} = {val} out of [0,100]"
            )
