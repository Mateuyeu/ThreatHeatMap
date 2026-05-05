"""Scatter <-> detail consistency tests.

These are the regression guard-rails for the bug we discussed in patch v1.1
(stale detail panel after a filter change). They lock in the contract that
/api/actors and /api/actor/<id> return identical scoring fields for the same
(sector, since, client, security_score) parameters.

They cover the whole fixture under several filter combinations.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as appmod  # noqa: E402

SCORE_FIELDS = (
    "x", "y", "p_sect", "p_ttp", "security_score",
    "p_sect_source", "security_score_source",
    "victims_total_window", "victims_in_sector",
)


@pytest.fixture(scope="module")
def client():
    appmod.app.config["TESTING"] = True
    with appmod.app.test_client() as c:
        yield c


@pytest.fixture(scope="module")
def fixture_data():
    return appmod._load_fixture()


def _q(sector, window_months, client_id="default", security_score=None):
    parts = [
        f"sector={sector}",
        f"window_months={window_months}",
        f"client={client_id}",
    ]
    if security_score is not None:
        parts.append(f"security_score={security_score}")
    return "&".join(parts)


@pytest.mark.parametrize("sector,window_months,client_id,security_score", [
    ("Telecommunications", 6, "default", None),
    ("Telecommunications", 12, "submarine_cable_op", None),
    ("Banking", 6, "default", None),
    ("Healthcare", 3, "telecom_eu", 80),
    ("Energy", 12, "default", 25),
    ("Public Administration", 6, "default", None),
])
def test_scatter_detail_consistency(client, fixture_data, sector, window_months, client_id, security_score):
    qs = _q(sector, window_months, client_id, security_score)
    actors_resp = client.get(f"/api/actors?{qs}")
    assert actors_resp.status_code == 200
    payload = actors_resp.get_json()

    for scored in payload["actors"]:
        actor_id = scored["id"]
        detail_resp = client.get(f"/api/actor/{actor_id}?{qs}")
        assert detail_resp.status_code == 200, f"detail call failed for {actor_id}"
        detail = detail_resp.get_json()["actor"]
        for field in SCORE_FIELDS:
            assert detail[field] == scored[field], (
                f"Mismatch on field {field!r} for {actor_id} "
                f"(sector={sector}, window_months={window_months}, "
                f"client={client_id}, security_score={security_score}): "
                f"scatter={scored[field]!r} detail={detail[field]!r}"
            )


def test_unknown_sector_returns_400(client):
    resp = client.get("/api/actors?sector=NotARealSector")
    assert resp.status_code == 400


def test_unknown_actor_returns_404(client):
    resp = client.get("/api/actor/not_a_real_actor?sector=Telecommunications&window_months=6")
    assert resp.status_code == 404


def test_alias_resolution(client):
    # 'Telco' is an alias of 'Telecommunications' in sectors.json
    resp = client.get("/api/actors?sector=Telco&window_months=6")
    assert resp.status_code == 200
    assert resp.get_json()["sector"] == "Telecommunications"
