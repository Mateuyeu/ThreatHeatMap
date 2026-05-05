# Fixture rationale (Phase 1, patch v1.1)

This document explains the per-actor sector targeting and victim allocation
choices in `actors_demo.json`. Every figure here is **synthetic** — the goal
is statistical plausibility for technical validation, not ground truth.

## Anchors

- Reporting date assumed: **2026-05-04**.
- Time windows in the UI: 3 / 6 / 12 months. Victims are spread over ~21 months
  (oldest 2024-08-12, most recent 2026-04-30) so each window yields a
  different signal.
- Sectors follow `data/sectors.json` (NIS2-aligned canonical names).

## Cross-actor distribution targets met (window: last 6 months)

| Sector                  | Actors with P_sect ≥ 0.10 | Notes                                |
|-------------------------|---------------------------|--------------------------------------|
| Telecommunications      | 8 / 10                    | Required ≥ 8 / 10 by patch v1.1.     |
| Banking                 | 6 / 10                    | Required ≥ 6 / 10 by patch v1.1.     |
| Healthcare              | 6 / 10                    | Required ≥ 6 / 10.                   |
| Energy                  | 6 / 10                    | Required ≥ 6 / 10.                   |
| Manufacturing           | 6 / 10                    | Required ≥ 6 / 10.                   |
| Public Administration   | 6 / 10                    | Required ≥ 6 / 10.                   |
| Financial Market Infra  | 2 / 10                    | Niche sector, intentionally lower.   |
| Submarine Cable Ops     | 1 / 10                    | Strategic interest, very rare events.|

Total victims: 80 across 10 actors over ~21 months.

## Per-actor rationale

### Lazarus Group (G0032, DPRK)
- **Primary intent**: financial gain → banking, FMI, cryptocurrency platforms.
- **Telecom rationale**: secondary interest, historically targeted Korean
  telecom for SIGINT and lateral access; one telecom victim in window keeps
  the actor visible without overweighting.
- **Why no manufacturing / healthcare in window**: not aligned with the
  financial mandate; baseline `p_sect` left near zero so the fallback path
  doesn't artificially inflate them either.

### APT28 / Fancy Bear (G0007, Russia GRU)
- **Primary intent**: government, defense research, energy. Telecom occasional
  for SIGINT staging.
- **Banking / FMI absent**: APT28's mission set is geopolitical, not
  financial-extortion driven.

### APT41 (G0096, China)
- **Dual mandate**: state espionage + Winnti-style financial side. Both
  reflected: telecom (heavy), healthcare (espionage), manufacturing (IP
  theft), banking (Winnti).
- **Highest cadence in window** (4 victims in 6 mo) reflects their published
  operational tempo.

### APT29 / Cozy Bear (G0016, Russia SVR)
- **Primary intent**: government, research, ICT supply chain. Telecom via
  cloud/SaaS tenant compromise.
- **Energy added in window**: SVR has shown interest in energy-policy
  organizations (e.g. nuclear regulators); plausible secondary objective.

### Sandworm (G0034, Russia GRU)
- **Primary intent**: destructive ops on critical infrastructure → energy,
  telecom, water, public services. Submarine cable victim is the analytically
  most relevant signal for a subsea-cable-operator client.
- **Manufacturing in window**: industrial control overlap (aerospace).

### FIN7 (G0046, Russia, criminal)
- **Primary intent**: monetize via retail / hospitality / e-commerce. Recent
  shift into manufacturing supply chain and POS-vendor compromises (e.g.
  hospital POS) is reflected with one healthcare and one manufacturing victim
  in window.
- **No telecom in window**: telecom is not a credible FIN7 target. This is
  one of the two actors that legitimately fall below the telecom 8 / 10 bar.

### LockBit (S1063, RaaS)
- **Most opportunistic**: 6 victims in window across 6 sectors. Reflects
  RaaS affiliate diversity post-Operation Cronos (2024). Highest signal-to-
  noise for a "where do ransomware affiliates land?" question.
- **No formal MITRE Group ID**: linked to the MITRE software entry instead.

### Black Basta (G1043, Russia, criminal)
- **Primary intent**: manufacturing, healthcare, B2B. Telecom victims arrive
  via MSP / supply-chain compromise (Qakbot-era tooling), not direct.
- **Telecom victim in window** is intentionally framed as an MSP reseller to
  preserve plausibility.

### Cl0p (S0611, Russia, criminal)
- **Operational mode**: zero-day exploitation of MFT software (MOVEit,
  GoAnywhere, Cleo) → mass exploitation campaigns. Result: prolific across
  banking, FMI, public administration, food, manufacturing.
- **No telecom in window**: telecom is not a Cl0p MFT-dependent target. This
  is the other actor below the telecom 8 / 10 bar.
- **Type classification**: enum forces `cybercriminal`. Operationally an
  extortion-as-a-service brand; this is the closest available enum value
  and is documented here per the patch v1.1 spec.

### ALPHV / BlackCat (S1068, RaaS)
- **Primary intent**: healthcare, energy, transport. Used here as the
  historical proxy for the affiliate ecosystem (brand exited in 2024).
- **Maritime transport** and **submarine cable adjacency**: BlackCat
  affiliates hit shipping companies; this preserves the maritime / subsea
  signal for the relevant client profiles.

## Baseline `p_sect` semantics

Each actor's `sector_targeting[<sector>].p_sect` is a **long-term baseline**
used by the runtime only when the actor has zero victims in the selected
time window. It is never used to override the dynamic ratio when victims
exist in the window. Documented in `METHODOLOGY.md` (sub-pass B).

## Known biases

- Numbers are hand-picked, not estimated from any reference source.
- The set of 10 actors over-represents Russian-aligned threat groups, which
  reflects the empirical telecom-sector threat picture but is not a balanced
  global sample.
- Ransomware brand churn (LockBit successors, ALPHV exit) is approximated
  rather than modelled: each entry stands in for the affiliate ecosystem,
  not a single legal entity.
