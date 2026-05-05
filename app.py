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
from scoring.scorer import compute_score, filter_victims

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


def _parse_float(value: Optional[str], default: Optional[float], name: str) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        abort(400, description=f"Invalid number for {name!r}: {value!r}.")


def _public_score(actor: dict, scored: dict) -> dict:
    """Render compute_score() output for API consumers (drop verbose fields)."""
    return {
        "id": actor["id"],
        "name": actor["name"],
        "aliases": actor.get("aliases", []),
        "type": actor.get("type"),
        "country": actor.get("country"),
        "mitre_id": actor.get("mitre_id"),
        "mitre_url": actor.get("mitre_url"),
        "x": scored["x"],
        "y": scored["y"],
        "p_sect": scored["p_sect"],
        "p_ttp": scored["p_ttp"],
        "security_score": scored["security_score"],
        "p_sect_source": scored["p_sect_source"],
        "security_score_source": scored["security_score_source"],
        "victims_total_window": scored["victims_total_window"],
        "victims_in_sector": scored["victims_in_sector"],
        "victims_total_all_time": len(actor.get("victims", [])),
        "top_ttps": actor.get("ttps", [])[:3],
    }


def _list_clients() -> List[dict]:
    return _load_fixture().get("clients", [])


def _ttp_usage_map() -> Dict[str, int]:
    """Map of ttp_id -> number of distinct actors using it (exact-id match,
    intra-actor dedup). Used to compute the "Shared with N actors" counter
    in the detail panel (sub-pass C.2 option (beta))."""
    counts: Dict[str, int] = {}
    for a in _load_fixture().get("actors", []):
        ids = {t["id"] for t in a.get("ttps", []) if "id" in t}
        for ttp_id in ids:
            counts[ttp_id] = counts.get(ttp_id, 0) + 1
    return counts


# --- Routes --------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/methodology")
def methodology():
    """Serve METHODOLOGY.md verbatim as text/plain.

    Per C.3 spec the analyst opens the methodology note in a new tab from the
    UI footer. We do not render Markdown server-side in Phase 1; raw text is
    legible enough and keeps the dependency surface flat.
    """
    path = config.BASE_DIR / "METHODOLOGY.md"
    if not path.exists():
        abort(404, description="METHODOLOGY.md not found.")
    return path.read_text(encoding="utf-8"), 200, {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
    }


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
    meta = formulas.formula_meta(config.ACTIVE_FORMULA)
    return jsonify({
        "active_formula": config.ACTIVE_FORMULA,
        "active_formula_meta": meta,
        "active_victims_adapter": config.ACTIVE_VICTIMS_ADAPTER,
        "ransomware_live_usage": config.RANSOMWARE_LIVE_USAGE,
        "default_security_score": config.DEFAULT_SECURITY_SCORE,
        "default_client_id": config.DEFAULT_CLIENT_ID,
        "time_windows_months": config.TIME_WINDOWS_MONTHS,
        "default_time_window_months": config.DEFAULT_TIME_WINDOW_MONTHS,
        "available_formulas": formulas.list_formulas(),
        "quadrant_threshold_x": config.QUADRANT_THRESHOLD_X,
        "quadrant_threshold_y": config.QUADRANT_THRESHOLD_Y,
        "marker_size_min": config.MARKER_SIZE_MIN,
        "marker_size_max": config.MARKER_SIZE_MAX,
        "marker_size_fallback": config.MARKER_SIZE_FALLBACK,
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
    sec_override = _parse_float(request.args.get("security_score"), None, "security_score")

    return sector_canonical, since, window_months, client_id, sec_override


def _score_one(actor: dict, sector: str, since: date, client_id: str,
               sec_override: Optional[float]) -> dict:
    return compute_score(
        actor=actor,
        sector=sector,
        since=since,
        client_id=client_id,
        security_score_override=sec_override,
        default_security_score=config.DEFAULT_SECURITY_SCORE,
        formula_id=config.ACTIVE_FORMULA,
    )


@app.route("/api/actors")
def api_actors():
    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    public = []
    for a in fixture.get("actors", []):
        scored = _score_one(a, sector, since, client_id, sec_override)
        public.append(_public_score(a, scored))
    return jsonify({
        "sector": sector,
        "since": since.isoformat(),
        "until": date.today().isoformat(),
        "window_months": window_months,
        "client": client_id,
        "security_score_override": sec_override,
        "formula": config.ACTIVE_FORMULA,
        "formula_meta": formulas.formula_meta(config.ACTIVE_FORMULA),
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "actors": public,
    })


@app.route("/api/actor/<actor_id>")
def api_actor_detail(actor_id):
    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    actor = next((a for a in fixture.get("actors", []) if a["id"] == actor_id), None)
    if actor is None:
        abort(404, description=f"Unknown actor id {actor_id!r}.")

    scored = _score_one(actor, sector, since, client_id, sec_override)
    public = _public_score(actor, scored)

    # Augment ttps with the "Shared with N actors" counter (option (beta):
    # exact-id match, intra-actor dedup, self-excluded).
    usage = _ttp_usage_map()
    augmented_ttps = []
    for t in actor.get("ttps", []):
        ttp_id = t.get("id")
        shared_with = max(0, usage.get(ttp_id, 0) - 1) if ttp_id else 0
        augmented_ttps.append({**t, "shared_with": shared_with})

    return jsonify({
        "actor": {
            **public,
            "description": actor.get("description"),
            "all_top_ttps": augmented_ttps,
            "sector_targeting": actor.get("sector_targeting", {}),
            "default_security_score": actor.get("default_security_score"),
            "security_score_overrides_by_client": actor.get("security_score_overrides_by_client", {}),
            "victims_window": scored["victims_window"],
            "victims_sector": scored["victims_sector"],
        },
        "sector": sector,
        "since": since.isoformat(),
        "until": date.today().isoformat(),
        "window_months": window_months,
        "client": client_id,
        "formula": config.ACTIVE_FORMULA,
        "formula_meta": formulas.formula_meta(config.ACTIVE_FORMULA),
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
        return jsonify({
            "status": "client_side",
            "format": fmt,
            "message": "PNG and SVG exports are produced client-side via Plotly.downloadImage. Trigger from the UI's Export menu.",
        }), 200

    sector, since, window_months, client_id, sec_override = _common_query_params()
    fixture = _load_fixture()
    payload_actors = []
    for a in fixture.get("actors", []):
        scored = _score_one(a, sector, since, client_id, sec_override)
        payload_actors.append({
            **_public_score(a, scored),
            "description": a.get("description"),
            "all_top_ttps": a.get("ttps", []),
            "sector_targeting": a.get("sector_targeting", {}),
            "victims_window": scored["victims_window"],
            "victims_sector": scored["victims_sector"],
        })
    payload = {
        "metadata": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "sector": sector,
            "since": since.isoformat(),
            "until": date.today().isoformat(),
            "window_months": window_months,
            "client": client_id,
            "security_score_override": sec_override,
            "formula": config.ACTIVE_FORMULA,
            "formula_meta": formulas.formula_meta(config.ACTIVE_FORMULA),
            "active_victims_adapter": config.ACTIVE_VICTIMS_ADAPTER,
            "ransomware_live_usage": config.RANSOMWARE_LIVE_USAGE,
            "fixture_version": fixture.get("metadata", {}).get("version"),
        },
        "actors": payload_actors,
    }
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
    if config.ACTIVE_VICTIMS_ADAPTER == "ransomware_live":
        from connectors.ransomware_live import RansomwareLiveAdapter
        RansomwareLiveAdapter(usage_flag=config.RANSOMWARE_LIVE_USAGE)


if __name__ == "__main__":
    _emit_license_notices()
    _load_fixture()
    normalizer.load(config.SECTORS_PATH)
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
