from __future__ import annotations
import logging
import pathlib
import time

import numpy as np
import pandas as pd

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
REP_MASTER_PATH = BASE_DIR / 'data' / 'rep_master.csv'
OUT_PARQUET = BASE_DIR / 'raw_crm_cms_dataset.parquet'

SEED = 2024
rng  = np.random.default_rng(SEED)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

N_HCP_INITIAL = 820

SPECIALTIES: list[str] = [
    'Pain Management', 'Oncology', 'Palliative Care', 'Neurology',
    'Anesthesiology', 'Internal Medicine', 'Family Practice',
    'Orthopedics', 'Emergency Medicine', 'Psychiatry',
]
SPEC_PROBS: list[float] = [0.26, 0.18, 0.14, 0.10, 0.10, 0.09, 0.06, 0.04, 0.02, 0.01]

BRAND_NAMES: list[str] = ['Subsys', 'Abstral', 'Actiq', 'Fentora', 'Lazanda']
BRAND_PROBS: list[float] = [0.35, 0.25, 0.18, 0.14, 0.08]

LOCATIONS: list[tuple[str, str]] = [
    ('Los Angeles', 'CA'), ('Houston', 'TX'),  ('Miami',        'FL'),
    ('New York',    'NY'), ('Chicago',  'IL'),  ('Philadelphia', 'PA'),
    ('Columbus',    'OH'), ('Detroit',  'MI'),  ('Atlanta',      'GA'),
    ('Charlotte',   'NC'), ('Phoenix',  'AZ'),  ('Seattle',      'WA'),
    ('Denver',      'CO'), ('Boston',   'MA'),  ('Las Vegas',    'NV'),
    ('Portland',    'OR'), ('Nashville','TN'),  ('Baltimore',    'MD'),
    ('Austin',      'TX'), ('Jacksonville','FL'),
]

REPS_HYBRID: list[str] = [f'REP-H{i:03d}' for i in range(101, 389)]
TERRITORIES_HYBRID: list[str] = [f'TERR-H{i:02d}' for i in range(1, 13)]
REP_TO_TERR_HYBRID: dict[str, str] = {REPS_HYBRID[i]: TERRITORIES_HYBRID[i % len(TERRITORIES_HYBRID)] for i in range(len(REPS_HYBRID))}

REPS_SYNTH: list[str] = [f'REP-S{i:03d}' for i in range(501, 851)]
TERRITORIES_SYNTH: list[str] = [f'TERR-S{i:02d}' for i in range(1, 15)]
REP_TO_TERR_SYNTH: dict[str, str] = {REPS_SYNTH[i]: TERRITORIES_SYNTH[i % len(TERRITORIES_SYNTH)] for i in range(len(REPS_SYNTH))}

_FIRST_HYBRID = ['Helen', 'Harold', 'Howard', 'Hannah', 'Henry', 'Holly', 'Heather', 'Harvey', 'Harrison', 'Hope', 'Hugh', 'Hilary', 'Hector', 'Hazel', 'Homer', 'Hayden', 'Hunter', 'Hilda', 'Holden', 'Hattie']
_LAST_HYBRID = ['Vance', 'Finch', 'Sterling', 'Hayes', 'Monroe', 'Bishop', 'Sinclair', 'Conway', 'Mercer', 'Gallagher', 'Kensington', 'Thornton', 'Blackwood', 'Whitman', 'Carrington', 'Preston', 'Vanderbilt', 'Ellington', 'Barrington', 'Montgomery']
REP_NAMES_HYBRID: dict[str, str] = {
    rep: f"{_FIRST_HYBRID[i % len(_FIRST_HYBRID)]} {_LAST_HYBRID[(i // len(_FIRST_HYBRID)) % len(_LAST_HYBRID)]}"
    for i, rep in enumerate(REPS_HYBRID)
}

_FIRST_SYNTH = ['Samuel', 'Sophia', 'Sean', 'Sarah', 'Simon', 'Stella', 'Scott', 'Serena', 'Seth', 'Sadie', 'Silas', 'Sienna', 'Spencer', 'Selena', 'Stephen', 'Sasha', 'Stanley', 'Summer', 'Solomon', 'Sloan']
_LAST_SYNTH = ['Brooks', 'Patel', 'Chen', 'Kapoor', 'Nakamura', "O'Connor", 'Novak', 'Dubois', 'Kowalski', 'Larsson', 'Rossi', 'Santos', 'Tanaka', 'Muller', 'Gomez', 'Vargas', 'Alvarez', 'Kim', 'Zhang', 'Nielsen']
REP_NAMES_SYNTH: dict[str, str] = {
    rep: f"{_FIRST_SYNTH[i % len(_FIRST_SYNTH)]} {_LAST_SYNTH[(i // len(_FIRST_SYNTH)) % len(_LAST_SYNTH)]}"
    for i, rep in enumerate(REPS_SYNTH)
}

SPEC_CAPACITY: dict[str, float] = {
    'Pain Management': 1.40, 'Oncology': 1.30, 'Palliative Care': 1.25,
    'Neurology':       1.10, 'Anesthesiology':  1.20,
    'Internal Medicine': 0.90, 'Family Practice': 0.80,
    'Orthopedics':     0.95, 'Emergency Medicine': 0.70, 'Psychiatry': 0.80,
}

TIER_TARGET_RANGE: dict[int, tuple[int, int]] = {1: (9, 14), 2: (5, 9), 3: (2, 5)}

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


def make_npi(idx: int, prefix: int = 1_001_000_001) -> str:
    return str(prefix + idx)


def make_physician_name() -> str:
    first = rng.choice(_FIRST)
    last  = rng.choice(_LAST)
    return f'Dr. {first} {last}'


def assign_tier(specialty: str, territory: str, terr_volume: dict[str, int]) -> int:
    vol_score = terr_volume.get(territory, 8)
    spec_cap  = SPEC_CAPACITY[specialty]
    raw       = vol_score * spec_cap + float(rng.normal(0.0, 0.8))
    if raw >= 13.0:
        return 1
    elif raw >= 10.0:
        return 2
    else:
        return 3


def generate(mode: str = 'hybrid') -> pd.DataFrame:
    t0 = time.perf_counter()
    n_hcp = 820 if mode == 'hybrid' else 1350
    reps_pool = REPS_HYBRID if mode == 'hybrid' else REPS_SYNTH
    terr_map = REP_TO_TERR_HYBRID if mode == 'hybrid' else REP_TO_TERR_SYNTH
    terr_list = TERRITORIES_HYBRID if mode == 'hybrid' else TERRITORIES_SYNTH
    rep_names_map = REP_NAMES_HYBRID if mode == 'hybrid' else REP_NAMES_SYNTH
    npi_start = 1_001_000_001 if mode == 'hybrid' else 2_001_000_001

    rep_quality = {rep: float(rng.beta(4.0, 2.0)) for rep in reps_pool}
    terr_volume = {t: int(rng.integers(6, 11)) for t in terr_list}

    log.info('Generating %d synthetic HCP records [mode=%s, seed=%d]…', n_hcp, mode, SEED)

    hcp_reps = np.tile(reps_pool, n_hcp // len(reps_pool) + 1)[:n_hcp]
    rng.shuffle(hcp_reps)

    rows: list[dict] = []
    for idx in range(n_hcp):
        rep       = str(hcp_reps[idx])
        rep_name  = rep_names_map.get(rep, rep)
        territory = terr_map[rep]
        specialty = str(rng.choice(SPECIALTIES, p=SPEC_PROBS))
        brand     = str(rng.choice(BRAND_NAMES, p=BRAND_PROBS))
        city, st  = LOCATIONS[int(rng.integers(len(LOCATIONS)))]

        tot_clms        = int(rng.negative_binomial(n=15, p=0.45))
        tot_30day_fills = float(max(0.0, rng.gamma(shape=6.0, scale=2.5)))
        tot_drug_cst    = float(max(0.0, tot_30day_fills * float(rng.uniform(850.0, 2600.0))))

        cms_decile   = int(np.clip(np.ceil((tot_30day_fills / 30.0) * 10.0), 1, 10))
        spec_cap     = SPEC_CAPACITY[specialty]

        if mode == 'synthetic':
            hcp_tier = assign_tier(specialty, territory, terr_volume)
            lo, hi   = TIER_TARGET_RANGE[hcp_tier]
            target_calls = int(rng.integers(lo, hi + 1))
        else:
            lam          = max(2.0, cms_decile * 1.2 * spec_cap)
            target_calls = int(np.clip(rng.poisson(lam), 2, 16))
            hcp_tier     = 1 if cms_decile >= 8 else (2 if cms_decile >= 4 else 3)

        comp_factor  = float(rng.beta(7.0, 3.0))
        actual_calls = max(0, int(round(target_calls * comp_factor)))

        samples_dropped = int(rng.integers(0, max(2, actual_calls + 2)))
        samples_dropped = min(samples_dropped, actual_calls + 2)

        rq        = rep_quality[rep]
        ec50      = 4.0
        emax      = 6.5 * rq * spec_cap
        call_eff  = (emax * (actual_calls ** 1.5)) / (ec50 ** 1.5 + actual_calls ** 1.5) if actual_calls > 0 else 0.0
        samp_eff  = 1.2 * float(np.sqrt(samples_dropped)) * spec_cap
        noise     = float(rng.normal(0.0, 1.2))

        rx_lift   = float(np.clip(0.5 + call_eff + samp_eff + noise, -3.0, 18.0))
        post_fills      = float(max(0.0, tot_30day_fills * (1.0 + rx_lift / 100.0)))
        delta_log_fills = float(np.log1p(post_fills) - np.log1p(tot_30day_fills))

        rows.append({
            'Prscrbr_NPI':         make_npi(idx, npi_start),
            'Physician_Name':      make_physician_name(),
            'Specialty':           specialty,
            'City':                city,
            'State':               st,
            'Brand_Name':          brand,
            'Sales_Rep':           rep,
            'Sales_Rep_Name':      rep_name,
            'Territory':           territory,
            'HCP_Tier':            hcp_tier,
            'CMS_Volume_Decile':   cms_decile,
            'Target_Calls':        target_calls,
            'Actual_Calls':        actual_calls,
            'Samples_Dropped':     samples_dropped,
            'Tot_Clms':            tot_clms,
            'Tot_30day_Fills':     round(tot_30day_fills, 4),
            'Tot_Drug_Cst':        round(tot_drug_cst, 2),
            'Rx_Lift_Pct':         round(rx_lift, 4),
            'Delta_Log_Fills':     round(delta_log_fills, 6),
            'Post_Campaign_Fills': round(post_fills, 4),
            'dataset_mode':        mode,
        })

    df = pd.DataFrame(rows)
    elapsed = time.perf_counter() - t0

    log.info('Generated %d raw HCP records [%s] in %.4fs.', len(df), mode, elapsed)
    return df


def main() -> None:
    df_hybrid = generate('hybrid')
    df_synth  = generate('synthetic')

    out_hybrid = BASE_DIR / 'raw_crm_cms_dataset_hybrid.parquet'
    out_synth  = BASE_DIR / 'raw_crm_cms_dataset_synthetic.parquet'

    df_hybrid.to_parquet(out_hybrid, index=False)
    df_synth.to_parquet(out_synth, index=False)

    df_hybrid.to_csv(BASE_DIR / 'raw_crm_cms_dataset_hybrid.csv', index=False)
    df_synth.to_csv(BASE_DIR / 'raw_crm_cms_dataset_synthetic.csv', index=False)

    crm_cols = ['Prscrbr_NPI', 'Physician_Name', 'Specialty', 'City', 'State', 'Sales_Rep', 'Sales_Rep_Name', 'Territory', 'HCP_Tier', 'Target_Calls', 'Actual_Calls', 'Samples_Dropped']
    df_hybrid[crm_cols].to_csv(BASE_DIR / 'crm_call_activity.csv', index=False)

    df_hybrid.to_parquet(OUT_PARQUET, index=False)
    df_hybrid.to_csv(BASE_DIR / 'raw_crm_cms_dataset.csv', index=False)

    # Master rep registry
    rep_master_rows = []
    for r in REPS_HYBRID:
        rep_master_rows.append({
            'rep_id': r,
            'sales_rep_name': REP_NAMES_HYBRID[r],
            'territory_id': REP_TO_TERR_HYBRID[r],
            'is_active': True,
            'hire_date': '2021-01-15',
            'dataset_mode': 'hybrid',
        })
    for r in REPS_SYNTH:
        rep_master_rows.append({
            'rep_id': r,
            'sales_rep_name': REP_NAMES_SYNTH[r],
            'territory_id': REP_TO_TERR_SYNTH[r],
            'is_active': True,
            'hire_date': '2021-06-01',
            'dataset_mode': 'synthetic',
        })
    pd.DataFrame(rep_master_rows).to_csv(REP_MASTER_PATH, index=False)

    log.info('✅ Exported %s, %s, rep_master.csv and CSV versions.', out_hybrid, out_synth)


if __name__ == '__main__':
    main()
