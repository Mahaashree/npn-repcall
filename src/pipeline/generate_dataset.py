#!/usr/bin/env python3
"""
generate_dataset.py
===================
Synthesize a pharmaceutical CRM + HCP prescriber dataset inspired by the
FDA TIRF REMS / Insys Authorized Prescriptions public archive structure.

Data Provenance:
  STRUCTURE  → FDA TIRF REMS / Insys Authorized Rx Public Archive
               (JHU OIDA / UCSF Industry Documents: 1_sort_dedup_igcase.csv)
               Column schema: Prscrbr_NPI, Physician_Name, Specialty, City,
               State, Brand_Name, Tot_Clms, Tot_30day_Fills, Tot_Drug_Cst.
  CONTENT    → 100% Fully Synthetic. No real patient or physician data used.
  CRM LAYER  → 100% Exogenous synthetic. Target_Calls assigned from territory
               volume deciles and specialty capacity ratings only.
               ZERO circular dependence on baseline Rx volume.

Output: raw_crm_cms_dataset.parquet
"""

from __future__ import annotations
import logging
import pathlib
import time

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
REP_MASTER_PATH = BASE_DIR / 'data' / 'rep_master.csv'
OUT_PARQUET = BASE_DIR / 'raw_crm_cms_dataset.parquet'

# ── Reproducibility ───────────────────────────────────────────────────────────
SEED = 2024
rng  = np.random.default_rng(SEED)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
N_HCP_INITIAL = 820  # before suppression filter; ~650 expected after Tot_Clms ≥ 11

# Specialties weighted toward TIRF-context high-prescribers
SPECIALTIES: list[str] = [
    'Pain Management', 'Oncology', 'Palliative Care', 'Neurology',
    'Anesthesiology', 'Internal Medicine', 'Family Practice',
    'Orthopedics', 'Emergency Medicine', 'Psychiatry',
]
SPEC_PROBS: list[float] = [0.26, 0.18, 0.14, 0.10, 0.10, 0.09, 0.06, 0.04, 0.02, 0.01]

# TIRF brand portfolio
BRAND_NAMES: list[str] = ['Subsys', 'Abstral', 'Actiq', 'Fentora', 'Lazanda']
BRAND_PROBS: list[float] = [0.35, 0.25, 0.18, 0.14, 0.08]

# Geographic locations (city, state) — synthetic assignments
LOCATIONS: list[tuple[str, str]] = [
    ('Los Angeles', 'CA'), ('Houston', 'TX'),  ('Miami',        'FL'),
    ('New York',    'NY'), ('Chicago',  'IL'),  ('Philadelphia', 'PA'),
    ('Columbus',    'OH'), ('Detroit',  'MI'),  ('Atlanta',      'GA'),
    ('Charlotte',   'NC'), ('Phoenix',  'AZ'),  ('Seattle',      'WA'),
    ('Denver',      'CO'), ('Boston',   'MA'),  ('Las Vegas',    'NV'),
    ('Portland',    'OR'), ('Nashville','TN'),  ('Baltimore',    'MD'),
    ('Austin',      'TX'), ('Jacksonville','FL'),
]

# Sales force: 12 reps across 6 territories (2 reps per territory)
REPS: list[str]        = [f'REP-{i:03d}' for i in range(101, 113)]
TERRITORIES: list[str] = [f'TERR-{i:02d}' for i in range(1, 7)]
REP_TO_TERR: dict[str, str] = {REPS[i]: TERRITORIES[i // 2] for i in range(12)}

# ── Exogenous latent variables (NOT derived from Rx baseline) ─────────────────
# Rep quality: domain experts' subjective rating — uncorrelated with Rx volume
REP_QUALITY: dict[str, float] = {
    rep: float(rng.beta(4.0, 2.0)) for rep in REPS
}

# Territory volume decile: administrative assignment (6–10 scale)
TERR_VOLUME: dict[str, int] = {
    t: int(rng.integers(6, 11)) for t in TERRITORIES
}

# Specialty → target-call capacity multiplier (pure domain knowledge table)
SPEC_CAPACITY: dict[str, float] = {
    'Pain Management': 1.40, 'Oncology': 1.30, 'Palliative Care': 1.25,
    'Neurology':       1.10, 'Anesthesiology':  1.20,
    'Internal Medicine': 0.90, 'Family Practice': 0.80,
    'Orthopedics':     0.95, 'Emergency Medicine': 0.70, 'Psychiatry': 0.80,
}

# Target call ranges (low/high) by HCP Tier
TIER_TARGET_RANGE: dict[int, tuple[int, int]] = {1: (9, 14), 2: (5, 9), 3: (2, 5)}

# ── Name pools (synthetic, no real identities) ────────────────────────────────
_FIRST = [
    'James','John','Robert','Michael','William','David','Richard','Joseph',
    'Thomas','Charles','Mary','Patricia','Jennifer','Linda','Barbara','Elizabeth',
    'Susan','Jessica','Sarah','Karen','Lisa','Nancy','Betty','Margaret','Sandra',
    'Ashley','Dorothy','Kimberly','Emily','Donna','Michelle','Carol','Amanda',
    'Melissa','Deborah','Laura','Rebecca','Stephanie','Sharon','Kathleen',
]
_LAST = [
    'Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis',
    'Rodriguez','Martinez','Hernandez','Lopez','Gonzalez','Wilson','Anderson',
    'Thomas','Taylor','Moore','Jackson','Martin','Lee','Perez','Thompson',
    'White','Harris','Sanchez','Clark','Ramirez','Lewis','Robinson','Walker',
    'Young','Allen','King','Wright','Scott','Torres','Nguyen','Hill','Flores',
    'Green','Adams','Nelson','Baker','Hall','Rivera','Campbell','Mitchell','Carter',
]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def make_npi(idx: int) -> str:
    """Generate a plausible 10-digit synthetic NPI (1001xxxxxx)."""
    return str(1_001_000_001 + idx)


def make_physician_name() -> str:
    """Synthesize 'Dr. FirstName LastName' — no real identity."""
    first = rng.choice(_FIRST)
    last  = rng.choice(_LAST)
    return f'Dr. {first} {last}'


def assign_tier(specialty: str, territory: str) -> int:
    """
    Assign HCP Tier 1/2/3 purely from:
      - Territory volume decile (exogenous administrative score)
      - Specialty capacity multiplier (domain knowledge table)
    Crucially: zero dependence on baseline Rx volume (Tot_30day_Fills / Tot_Clms).
    """
    vol_score = TERR_VOLUME[territory]           # 6–10, administrative
    spec_cap  = SPEC_CAPACITY[specialty]         # domain constant
    raw       = vol_score * spec_cap + float(rng.normal(0.0, 0.8))
    if raw >= 13.0:
        return 1
    elif raw >= 10.0:
        return 2
    else:
        return 3


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATION
# ═══════════════════════════════════════════════════════════════════════════════
def generate() -> pd.DataFrame:
    t0 = time.perf_counter()
    log.info('Generating %d synthetic HCP records (seed=%d)…', N_HCP_INITIAL, SEED)

    # Assign reps with equal load (~68 HCPs per rep)
    hcp_reps = np.tile(REPS, N_HCP_INITIAL // len(REPS) + 1)[:N_HCP_INITIAL]
    rng.shuffle(hcp_reps)

    rows: list[dict] = []
    for idx in range(N_HCP_INITIAL):
        rep       = str(hcp_reps[idx])
        territory = REP_TO_TERR[rep]
        specialty = str(rng.choice(SPECIALTIES, p=SPEC_PROBS))
        brand     = str(rng.choice(BRAND_NAMES, p=BRAND_PROBS))
        city, st  = LOCATIONS[int(rng.integers(len(LOCATIONS)))]

        # ── Baseline Rx: INDEPENDENT of CRM layer ────────────────────────────
        # Negative binomial with mean≈18, σ≈6 — realistic claim distribution
        # Some records will have Tot_Clms < 11 (will be filtered by small-cell rule)
        tot_clms        = int(rng.negative_binomial(n=15, p=0.45))
        tot_30day_fills = float(max(0.0, rng.gamma(shape=6.0, scale=2.5)))
        tot_drug_cst    = float(max(0.0, tot_30day_fills * float(rng.uniform(850.0, 2600.0))))

        # ── CRM Detailing Layer: EXOGENOUS allocation ─────────────────────────
        hcp_tier     = assign_tier(specialty, territory)
        lo, hi       = TIER_TARGET_RANGE[hcp_tier]
        target_calls = int(rng.integers(lo, hi + 1))

        # Rep visit compliance (beta-distributed, not driven by Rx volume)
        comp_factor  = float(rng.beta(7.0, 3.0))       # peak ~0.70–0.90
        actual_calls = max(0, int(round(target_calls * comp_factor)))

        # Samples dropped per campaign period (bounded above by actual calls + 2)
        samples_dropped = int(rng.integers(0, max(2, actual_calls + 2)))
        samples_dropped = min(samples_dropped, actual_calls + 2)

        # ── Causal Rx Lift Model ──────────────────────────────────────────────
        # Rx_Lift_Pct = 0.5 + 2.4·RepQuality·ln(1+ActualCalls)
        #             + 1.2·√SamplesDropped + N(0, 0.8)
        # Bounded strictly [-3.0, +18.0]
        rq      = REP_QUALITY[rep]
        noise   = float(rng.normal(0.0, 0.8))
        rx_lift = (
            0.5
            + 2.4 * rq * float(np.log1p(actual_calls))
            + 1.2 * float(np.sqrt(samples_dropped))
            + noise
        )
        rx_lift = float(np.clip(rx_lift, -3.0, 18.0))

        post_fills = float(max(0.0, tot_30day_fills * (1.0 + rx_lift / 100.0)))

        rows.append({
            'Prscrbr_NPI':         make_npi(idx),
            'Physician_Name':      make_physician_name(),
            'Specialty':           specialty,
            'City':                city,
            'State':               st,
            'Brand_Name':          brand,
            'Sales_Rep':           rep,
            'Territory':           territory,
            'HCP_Tier':            hcp_tier,
            'Target_Calls':        target_calls,
            'Actual_Calls':        actual_calls,
            'Samples_Dropped':     samples_dropped,
            'Tot_Clms':            tot_clms,
            'Tot_30day_Fills':     round(tot_30day_fills, 4),
            'Tot_Drug_Cst':        round(tot_drug_cst, 2),
            'Rx_Lift_Pct':         round(rx_lift, 4),
            'Post_Campaign_Fills': round(post_fills, 4),
        })

    df = pd.DataFrame(rows)
    elapsed = time.perf_counter() - t0

    log.info('Generated %d raw HCP records in %.4fs.', len(df), elapsed)
    log.info('Column dtypes:\n%s', df.dtypes.to_string())
    log.info(
        'Rx_Lift_Pct summary:\n%s',
        df['Rx_Lift_Pct'].describe().round(4).to_string(),
    )
    log.info(
        'HCP_Tier distribution:\n%s',
        df['HCP_Tier'].value_counts().sort_index().to_string(),
    )
    log.info(
        'Records with Tot_Clms < 11 (will be suppressed): %d (%.1f%%)',
        (df['Tot_Clms'] < 11).sum(),
        (df['Tot_Clms'] < 11).mean() * 100,
    )
    return df


def main() -> None:
    df  = generate()
    df.to_parquet(OUT_PARQUET, index=False)
    log.info('✅ Exported %s  (%d rows × %d cols)', OUT_PARQUET, len(df), len(df.columns))


if __name__ == '__main__':
    main()
