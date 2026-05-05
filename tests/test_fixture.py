"""Validate the live fixture against data/schema/actor_schema.json.

The schema is the contract that future MITRE / DLS connectors will produce
against. Any drift between schema and fixture must trigger a test failure
here, not a silent runtime surprise.
"""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

SCHEMA_PATH = ROOT / "data" / "schema" / "actor_schema.json"


@pytest.fixture(scope="module")
def schema():
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validator(schema):
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


@pytest.fixture(scope="module")
def fixture_data():
    with config.DEMO_ACTORS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def canonical_sectors():
    with config.SECTORS_PATH.open(encoding="utf-8") as f:
        return {s["name"] for s in json.load(f)["sectors"]}


def test_schema_is_valid_draft07(schema):
    Draft7Validator.check_schema(schema)


def test_every_actor_validates_against_schema(validator, fixture_data):
    errors = []
    for actor in fixture_data["actors"]:
        for err in validator.iter_errors(actor):
            errors.append(f"actor[{actor.get('id', '?')}]: {err.message} at /{'/'.join(map(str, err.path))}")
    assert not errors, "\n".join(errors)


def test_actor_ids_are_unique(fixture_data):
    ids = [a["id"] for a in fixture_data["actors"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_sector_targeting_keys_use_canonical_sectors(fixture_data, canonical_sectors):
    issues = []
    for a in fixture_data["actors"]:
        for sector in a.get("sector_targeting", {}):
            if sector not in canonical_sectors:
                issues.append(f"actor[{a['id']}] uses non-canonical sector {sector!r}")
    assert not issues, "\n".join(issues)


def test_victim_sectors_use_canonical_sectors(fixture_data, canonical_sectors):
    issues = []
    for a in fixture_data["actors"]:
        for v in a.get("victims", []):
            if v["sector"] not in canonical_sectors:
                issues.append(f"actor[{a['id']}] victim {v['name']!r} -> sector {v['sector']!r}")
    assert not issues, "\n".join(issues)


def test_security_score_override_clients_match_clients_block(fixture_data):
    declared = {c["id"] for c in fixture_data.get("clients", [])}
    issues = []
    for a in fixture_data["actors"]:
        for client_id in (a.get("security_score_overrides_by_client") or {}):
            if client_id not in declared:
                issues.append(f"actor[{a['id']}] override for unknown client_id {client_id!r}")
    assert not issues, "\n".join(issues)


def test_mitre_url_present_when_mitre_id_present(fixture_data):
    for a in fixture_data["actors"]:
        if a.get("mitre_id"):
            assert a.get("mitre_url"), (
                f"actor[{a['id']}] has mitre_id={a['mitre_id']} but no mitre_url"
            )
