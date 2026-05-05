"""Centralized configuration for ThreatHeatMap.

Edit values here to switch formulas, adapters or license flags.
"""

from pathlib import Path

# --- Filesystem layout ---------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SECTORS_PATH = DATA_DIR / "sectors.json"
FIXTURES_DIR = DATA_DIR / "fixtures"
DEMO_ACTORS_PATH = FIXTURES_DIR / "actors_demo.json"
CACHE_DIR = DATA_DIR / "cache"
EXPORTS_DIR = DATA_DIR / "exports"
DLS_DIR = DATA_DIR / "dls"  # Phase 3 input directory

# --- Scoring -------------------------------------------------------------
ACTIVE_FORMULA = "geometric_mean_floored_v1"  # see scoring/formulas.py for choices

# --- Client / SecurityScore ---------------------------------------------
DEFAULT_CLIENT_ID = "default"
DEFAULT_SECURITY_SCORE = 50  # used when no per-client value is available

# --- Victims feed --------------------------------------------------------
# "fixture"      : Phase 1 demo data
# "local_dls"    : Phase 3 - LocalDLSAdapter
# "ransomware_live" : Phase 4 - subject to T&C compliance
ACTIVE_VICTIMS_ADAPTER = "fixture"

# --- ransomware.live licensing ------------------------------------------
# Allowed: "evaluation" | "authorized_commercial" | "disabled"
RANSOMWARE_LIVE_USAGE = "evaluation"

# --- MITRE ATT&CK TAXII (Phase 2) ---------------------------------------
MITRE_TAXII_ROOT = "https://attack-taxii.mitre.org/api/v21/"
MITRE_CACHE_TTL_HOURS = 24

# --- Flask --------------------------------------------------------------
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = True

# --- Time windows offered in the UI -------------------------------------
TIME_WINDOWS_MONTHS = [3, 6, 12]
DEFAULT_TIME_WINDOW_MONTHS = 6
