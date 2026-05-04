"""Sector normalization across heterogeneous sources.

Reads `data/sectors.json` once and exposes a canonical-name lookup keyed
on aliases (NIS2 wording, ENISA labels, ATT&CK x_mitre_industries entries,
ad-hoc strings). Comparison is lower-case, whitespace- and punctuation-
tolerant.
"""

import json
import re
import threading
from pathlib import Path

_LOCK = threading.Lock()
_CACHE = {"path": None, "alias_to_canonical": None, "canonical_set": None, "raw": None}


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _build_index(raw):
    alias_to_canonical = {}
    canonical_set = []
    for entry in raw.get("sectors", []):
        canonical = entry["name"]
        canonical_set.append(canonical)
        keys = {canonical, *entry.get("aliases", [])}
        for k in keys:
            alias_to_canonical[_slug(k)] = canonical
    return alias_to_canonical, canonical_set


def load(sectors_path):
    path = Path(sectors_path)
    with _LOCK:
        if _CACHE["path"] == str(path) and _CACHE["raw"] is not None:
            return _CACHE["raw"]
        raw = json.loads(path.read_text(encoding="utf-8"))
        alias_to_canonical, canonical_set = _build_index(raw)
        _CACHE.update(
            path=str(path),
            raw=raw,
            alias_to_canonical=alias_to_canonical,
            canonical_set=canonical_set,
        )
        return raw


def normalize(value, sectors_path):
    if value is None:
        return None
    load(sectors_path)
    return _CACHE["alias_to_canonical"].get(_slug(value))


def canonical_sectors(sectors_path):
    load(sectors_path)
    return list(_CACHE["canonical_set"])


def reset_cache():
    """Used by tests / refresh endpoint."""
    with _LOCK:
        _CACHE.update(path=None, raw=None, alias_to_canonical=None, canonical_set=None)
