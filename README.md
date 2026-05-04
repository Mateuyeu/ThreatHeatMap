# ThreatHeatMap

Local Flask tool that positions threat actors on a 2D heat map (Intent on Y,
Opportunity on X) for sectoral CTI reporting.

Status: **Phase 1** — skeleton + synthetic fixture (10 named actors, 42
simulated victim records). MITRE TAXII and victims-feed connectors are
scaffolded but not wired to live data.

## Run

```bash
pip install -r requirements.txt
python app.py
# http://127.0.0.1:5000
```

Tests: `python -m pytest tests/`

## Layout

```
app.py             Flask entry point and API routes
config.py          Central config (formula, adapters, license flags, paths)
scoring/           Interchangeable scoring formulas + sector normalizer
connectors/        Abstract VictimsAdapter + stubs (mitre, local_dls, ransomware_live)
data/sectors.json  NIS2 sector taxonomy with ENISA / ATT&CK aliases
data/fixtures/     Phase 1 synthetic data
templates/, static/  UI (vanilla JS + Plotly)
tests/             Unit tests for scoring/formulas.py
```

## Scoring

Active formula: `geometric_mean_v1` (see `scoring/formulas.py`).

- `Y = sqrt(P_sect * P_ttp) * 100`           — Intent (range 0–100)
- `X = SecurityScore * P_ttp`                — Opportunity (range 0–100)

Switch formula by changing `ACTIVE_FORMULA` in `config.py` and adding a new
entry to `FORMULAS`. Caller code in `app.py` does not change.

## Data sources & licensing

This tool is designed to integrate with the following sources. Each comes with
its own license obligations.

### MITRE ATT&CK STIX/TAXII (Phase 2)
TAXII endpoint `https://attack-taxii.mitre.org/api/v21/`.
Apache 2.0 license — attribution to MITRE required.

### Local DLS scraping (Phase 3 — `LocalDLSAdapter`)
Reads JSON/CSV files produced by the analyst's own scraping pipeline.
License obligations are inherited from each underlying source.

### ransomware.live (Phase 4 — `RansomwareLiveAdapter`)
The public ransomware.live API is licensed for **non-commercial use only**
(T&C section 2.1). Commercial / Pro use requires written authorization from
the data owner. The connector enforces a usage flag in `config.py`:

```python
RANSOMWARE_LIVE_USAGE = "evaluation"  # "evaluation" | "authorized_commercial" | "disabled"
```

- `"evaluation"` (default): allowed for technical evaluation; license banner
  printed at startup.
- `"authorized_commercial"`: must only be set after written authorization from
  the data owner.
- `"disabled"`: any call to the connector raises an explicit exception.

Exports (PNG, SVG, JSON) produced from this connector carry the attribution
clause `Source: Ransomware.live (https://www.ransomware.live)` per T&C
section 3.

The active victims feed is selected via `ACTIVE_VICTIMS_ADAPTER` in
`config.py`; switching to `LocalDLSAdapter` is a single-line change.

## Phase 1 disclosure

The actor and victim records under `data/fixtures/` are **synthetic** and
intended for technical validation only. Names are fictitious and must not be
used as ground truth in CTI reporting.
