"""Flask entry point for ThreatHeatMap.

Run:
    python app.py

Then open http://127.0.0.1:5000.
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, abort, jsonify, render_template, request

import config
from scoring import formulas, normalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("threat_heatmap")

app = Flask(__name__, static_folder="static", template_folder="templates")


# --- Fixture loading -----------------------------------------------------

_FIXTURE_CACHE: Dict[str, object] = {"path": None, "data": None}


def _load_fixture(force: bool = False) -> dict:
    path = str(config.DEMO_ACTORS_PATH)
    if force or _FIXTURE_CACHE.get("path") != path or _FIXTURE_CACHE.get("data") is None:
        with open(path, encoding="utf-8") as f:
            _FIXTURE_CACHE["data"] = json.load(f)
        _FIXTURE_CACHE["path"] = path
        LOGGER.info("Loaded fixture %s (%d actors)", path, len(_FIXTURE_CACHE["data"].get("actors", [])))
    return _FIXTURE_CACHE["data"]


# --- Helpers -------------------------------------------------------------

def _parse_since(since_str: Optional[str], window_months: Optional[int]) -> date:
    if since_str:
        try:
            return datetime.strptime(since_str, "%Y-%m-%d").date()
        except ValueError:
            abort(400, description=f"Invalid 'since' date: {since_str!r}. Expected YYYY-MM-DD.")
    months = window_months if window_months is not None else config.DEFAULT_TIME_WINDOW_MONTHS
    today = date.today()
    return today - timedelta(days=int(months) * 30)


def _parse_int(value: Optional[str], default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        abort(400, description=f"Invalid integer for {name!r}: {value!r}.")


def _parse_float(value: Optional[str], default: float, name: str) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        abort(400, description=f"Invalid number for {name!r}: {value!r}.")


def _filter_victims(actor: dict, since: date, sector_canonical: Optional[str]) -> Tuple[List[dict], List[dict]]:
    in_window = []
    for v in actor.get("victims", []):
        try:
            vd = datetime.strptime(v["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if vd >= since:
            in_window.append({**v, "_date": vd.isoformat()})
    in_sector = (
        [v for v in in_window if v.get("sector") == sector_canonical]
        if sector_canonical
        else []
    )
    return in_window, in_sector


def _resolve_security_score(actor: dict, client_id: str, override: Optional[float]) -> float:
    if override is not None:
        return float(override)
    by_client = actor.get("exposure_score_by_client", {})
    if client_id in by_client:
        return float(by_client[client_id])
    if config.DEFAULT_CLIENT_ID in by_client:
        return float(by_client[config.DEFAULT_CLIENT_ID])
    return float(config.DEFAULT_SECURITY_SCORE)


def _score_actor(actor: dict, sector_canonical: str, since: date,
                 client_id: str, security_score_override: Optional[float]) -> dict:
    in_window, in_sector = _filter_victims(actor, since, sector_canonical)
    p_sect = (len(in_sector) / len(in_window)) if in_window else 0.0
    p_ttp = float(actor.get("sector_ttp_affinity", {}).get(sector_canonical, 0.0))
    sec_score = _resolve_security_score(actor, client_id, security_score_override)

    y = formulas.compute_intent(p_sect, p_ttp, formula_id=config.ACTIVE_FORMULA)
    x = formulas.compute_opportunity(sec_score, p_ttp, formula_id=config.ACTIVE_FORMULA)

    return {
        "id": actor["id"],
        "name": actor["name"],
        "aliases": actor.get("aliases", []),
        "type": actor.get("type"),
        "country": actor.get("country"),
        "x": round(x, 2),
        "y": round(y, 2),
        "p_sect": round(p_sect, 4),
        "p_ttp": round(p_ttp, 4),
        "security_score": round(sec_score, 2),
        "victims_total_window": len(in_window),
        "victims_in_sector": len(in_sector),
        "top_ttps": actor.get("top_ttps", [])[:3],
    }


def _list_clients() -> List[dict]:
    return _load_fixture().get("clients", [])


# --- Routes --------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sectors")
def api_sectors():
    sectors = normalizer.canonical_sectors(config.SECTORS_PATH)
    raw = normalizer.load(config.SECTORS_PATH)
    return jsonify({
        "sectors": sectors,
        "reference": raw.get("reference"),
        "version": raw.get("version"),
    })


@app.route("/api/clients")
def api_clients():
    return jsonify({
        "clients": _list_clients(),
        "default_client_id": config.DEFAULT_CLIENT_ID,
        "default_security_score": config.DEFAULT_SECURITY_SCORE,
    })


@app.route("/api/config")
def api_config():
    return jsonify({
        "active_formula": config.ACTIVE_FORMULA,
        "active_victims_adapter": config.ACTIVE_VICTIMS_ADAPTER,
        "ransomware_live_usage": config.RANSOMWARE_LIVE_USAGE,
        "default_security_score": config.DEFAULT_SECURITY_SCORE,
        "default_client_id": config.DEFAULT_CLIENT_ID,
        "time_windows_months": config.TIME_WINDOWS_MONTHS,
        "default_time_window_months": config.DEFAULT_TIME_WINDOW_MONTHS,
        "available_formulas": formulas.list_formulas(),
    })


def _common_query_params():
    sector_arg = request.args.get("sector")
    if not sector_arg:
        abort(400, description="Missing required query parameter 'sector'.")
    sector_canonical = normalizer.normalize(sector_arg, config.SECTORS_PATH)
    if not sector_canonical:
        abort(400, description=f"Unknown sector {sector_arg!r}. See /api/sectors for the canonical list.")

    window_months = _parse_int(request.args.get("window_months"), config.DEFAULT_TIME_WINDOW_MONTHS, "window_months")
    since = _parse_since(request.args.get("since"), window_months)

    client_id = request.args.get("client") or config.DEFAULT_CLIENT_ID
    sec_score_arg = request.args.get("security_score")
    sec_override = _parse_float(sec_score_arg, None, "security_score") if sec_score_arg else None

    return sector_canonical, since, window_months, client_id, sec_override


@app.route("/api/actors")
def api_actors():
    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    scored = [
        _score_actor(a, sector, since, client_id, sec_override)
        for a in fixture.get("actors", [])
    ]
    return jsonify({
        "sector": sector,
        "since": since.isoformat(),
        "window_months": window_months,
        "client": client_id,
        "security_score_override": sec_override,
        "formula": config.ACTIVE_FORMULA,
        "actors": scored,
    })


@app.route("/api/actor/<actor_id>")
def api_actor_detail(actor_id):
    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    actor = next((a for a in fixture.get("actors", []) if a["id"] == actor_id), None)
    if actor is None:
        abort(404, description=f"Unknown actor id {actor_id!r}.")

    in_window, in_sector = _filter_victims(actor, since, sector)
    scored = _score_actor(actor, sector, since, client_id, sec_override)
    return jsonify({
        "actor": {
            **scored,
            "description": actor.get("description"),
            "aliases": actor.get("aliases", []),
            "all_top_ttps": actor.get("top_ttps", []),
            "sector_ttp_affinity": actor.get("sector_ttp_affinity", {}),
            "exposure_score_by_client": actor.get("exposure_score_by_client", {}),
            "victims_window": in_window,
            "victims_sector": in_sector,
        },
        "sector": sector,
        "since": since.isoformat(),
        "window_months": window_months,
        "client": client_id,
        "formula": config.ACTIVE_FORMULA,
    })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    _load_fixture(force=True)
    normalizer.reset_cache()
    return jsonify({
        "status": "ok",
        "message": "Reloaded fixture and sector cache.",
        "active_victims_adapter": config.ACTIVE_VICTIMS_ADAPTER,
    })


@app.route("/api/export")
def api_export():
    fmt = (request.args.get("format") or "json").lower()
    if fmt not in {"json", "png", "svg"}:
        abort(400, description="format must be one of: json, png, svg.")
    if fmt in {"png", "svg"}:
        # Image rendering is performed client-side via Plotly.downloadImage.
        return jsonify({
            "status": "client_side",
            "format": fmt,
            "message": f"PNG and SVG exports are produced client-side via Plotly.downloadImage. Trigger from the UI's Export menu.",
        }), 200

    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    scored = [
        _score_actor(a, sector, since, client_id, sec_override)
        for a in fixture.get("actors", [])
    ]
    payload = {
        "metadata": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "sector": sector,
            "since": since.isoformat(),
            "window_months": window_months,
            "client": client_id,
            "security_score_override": sec_override,
            "formula": config.ACTIVE_FORMULA,
            "active_victims_adapter": config.ACTIVE_VICTIMS_ADAPTER,
            "ransomware_live_usage": config.RANSOMWARE_LIVE_USAGE,
            "fixture_version": fixture.get("metadata", {}).get("version"),
        },
        "actors": [],
    }
    for a in fixture.get("actors", []):
        in_window, in_sector = _filter_victims(a, since, sector)
        scored_one = next((s for s in scored if s["id"] == a["id"]), None)
        payload["actors"].append({
            **(scored_one or {}),
            "description": a.get("description"),
            "all_top_ttps": a.get("top_ttps", []),
            "sector_ttp_affinity": a.get("sector_ttp_affinity", {}),
            "victims_window": in_window,
            "victims_sector": in_sector,
        })
    # Attribution clauses for any data sources requiring them.
    attributions = []
    if config.ACTIVE_VICTIMS_ADAPTER == "ransomware_live" and config.RANSOMWARE_LIVE_USAGE != "disabled":
        from connectors.ransomware_live import ATTRIBUTION_TEXT
        attributions.append(ATTRIBUTION_TEXT)
    if attributions:
        payload["metadata"]["attributions"] = attributions

    return jsonify(payload)


# --- Error handlers -----------------------------------------------------

@app.errorhandler(400)
def _bad_request(err):
    return jsonify({"error": "bad_request", "message": getattr(err, "description", str(err))}), 400


@app.errorhandler(404)
def _not_found(err):
    return jsonify({"error": "not_found", "message": getattr(err, "description", str(err))}), 404


# --- Bootstrap ----------------------------------------------------------

def _emit_license_notices():
    """Emit license banners for adapters that demand them."""
    if config.ACTIVE_VICTIMS_ADAPTER == "ransomware_live":
        from connectors.ransomware_live import RansomwareLiveAdapter
        # Instantiating the adapter prints the banner and validates the flag.
        RansomwareLiveAdapter(usage_flag=config.RANSOMWARE_LIVE_USAGE)


if __name__ == "__main__":
    _emit_license_notices()
    _load_fixture()
    normalizer.load(config.SECTORS_PATH)
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
