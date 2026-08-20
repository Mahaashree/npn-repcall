"""
src/pipeline/load_hybrid_source.py

Loader for HYBRID mode. Hybrid mode is never synthesized anymore — it is built
only from the fixed, real CMS+CRM source file at:

    data/raw_hybrid/cms_crm_dataset.csv

This module validates the source, renames/maps its columns into the exact raw
schema the downstream stages (preprocess -> analytics -> ml -> predict -> export)
expect for hybrid mode, and returns the ready DataFrame plus the rep-master rows.

It deliberately FAILS LOUDLY (FileNotFoundError / ValueError) instead of silently
falling back to synthetic data when the source file is missing or malformed.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
import pandas as pd

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
SOURCE_PATH = BASE_DIR / 'data' / 'raw_hybrid' / 'cms_crm_dataset.csv'
RAW_DIR = BASE_DIR / 'data' / 'generated' / 'raw'

OUT_HYBRID_PARQUET = RAW_DIR / 'raw_crm_cms_dataset_hybrid.parquet'
OUT_HYBRID_CSV = RAW_DIR / 'raw_crm_cms_dataset_hybrid.csv'
OUT_DEFAULT_PARQUET = RAW_DIR / 'raw_crm_cms_dataset.parquet'
OUT_DEFAULT_CSV = RAW_DIR / 'raw_crm_cms_dataset.csv'

# Source columns whose names change to the pipeline's expected raw schema.
RENAME_MAP = {
    'Prscrbr_Type':            'Specialty',
    'Prscrbr_City':            'City',
    'Prscrbr_State_Abrv':      'State',
    'Brnd_Name':               'Brand_Name',
    'Rep_ID':                  'Sales_Rep',
    'Rep_Name':                'Sales_Rep_Name',
    'Territory_ID':            'Territory',
    'Sample_Units_Dropped':    'Samples_Dropped',
    'Post_Tot_30day_Fills':    'Post_Campaign_Fills',
}

# HCP_Tier arrives as a human label; the pipeline requires an integer 1/2/3.
HYBRID_TIER_MAP = {
    'Tier 1 (High Potential)': 1,
    'Tier 2 (Med Potential)': 2,
    'Tier 3 (Low Potential)': 3,
}

# Raw schema order mirrors what generate_dataset.py historically emitted for
# hybrid mode. CMS_Volume_Decile / Compliance_Pct / Sample_Velocity etc. are
# deliberately NOT carried over: data_preprocessing.py recomputes them.
RAW_COLS = [
    'Prscrbr_NPI', 'Physician_Name', 'Specialty', 'City', 'State', 'Brand_Name',
    'Sales_Rep', 'Sales_Rep_Name', 'Territory', 'HCP_Tier',
    'Target_Calls', 'Actual_Calls', 'Samples_Dropped',
    'Tot_Clms', 'Tot_30day_Fills', 'Tot_Drug_Cst',
    'Rx_Lift_Pct', 'Delta_Log_Fills', 'Post_Campaign_Fills',
    'dataset_mode',
]

CRITICAL_COLS = [
    'Prscrbr_NPI', 'Prscrbr_First_Name', 'Prscrbr_Last_Org_Name', 'Prscrbr_Type',
    'Prscrbr_City', 'Prscrbr_State_Abrv', 'Brnd_Name', 'Rep_ID', 'Rep_Name',
    'Territory_ID', 'HCP_Tier', 'Target_Calls', 'Actual_Calls',
    'Sample_Units_Dropped', 'Tot_Clms', 'Tot_30day_Fills', 'Tot_Drug_Cst',
    'Rx_Lift_Pct', 'Post_Tot_30day_Fills',
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load + validate + map the real hybrid source.

    Returns:
        (raw_hybrid_df, rep_master_df) where rep_master_df is the hybrid block
        (real REP-xxx rows) ready to be merged into data/rep_master.csv.

    Raises:
        FileNotFoundError if data/raw_hybrid/cms_crm_dataset.csv is missing.
        ValueError if required columns or HCP_Tier labels are missing/unknown.
    """
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            'Hybrid-mode source file is missing: %s\n'
            'Hybrid data is loaded ONLY from this real CMS+CRM file; '
            'synthesizing hybrid data is intentionally disabled. '
            'Restore the file and re-run the pipeline.' % SOURCE_PATH)

    df = pd.read_csv(SOURCE_PATH)
    missing_cols = [c for c in CRITICAL_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError('Hybrid source missing expected columns: %s' % missing_cols)

    unknown_tiers = sorted(set(df['HCP_Tier'].astype(str)) - set(HYBRID_TIER_MAP))
    if unknown_tiers:
        raise ValueError('Hybrid source has unhandled HCP_Tier labels: %s' % unknown_tiers)

    df = df.rename(columns=RENAME_MAP)
    df['HCP_Tier'] = df['HCP_Tier'].map(HYBRID_TIER_MAP).astype('int64')
    if df['HCP_Tier'].isnull().any():
        raise ValueError('HCP_Tier mapping produced nulls — source label regression.')

    df['Physician_Name'] = (
        'Dr. ' + df['Prscrbr_First_Name'].astype(str).str.strip()
        + ' ' + df['Prscrbr_Last_Org_Name'].astype(str).str.strip()
    )
    df['Delta_Log_Fills'] = np.log1p(df['Post_Campaign_Fills']) - np.log1p(df['Tot_30day_Fills'])
    df['dataset_mode'] = 'hybrid'

    df = df[RAW_COLS].copy()

    rep_block = (
        df[['Sales_Rep', 'Sales_Rep_Name', 'Territory']]
        .drop_duplicates('Sales_Rep')
        .sort_values('Sales_Rep')
    )
    rep_master = pd.DataFrame({
        'rep_id':          rep_block['Sales_Rep'],
        'sales_rep_name':  rep_block['Sales_Rep_Name'],
        'territory_id':    rep_block['Territory'],
        'is_active':       True,
        'hire_date':       '2021-01-15',
        'dataset_mode':    'hybrid',
    })

    log.info('Loaded hybrid source %s: %d rows x %d cols (reps=%d, territories=%d).',
             SOURCE_PATH, len(df), len(df.columns),
             df['Sales_Rep'].nunique(), df['Territory'].nunique())
    return df, rep_master


def main() -> None:
    df, _ = build()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_HYBRID_PARQUET, index=False)
    df.to_csv(OUT_HYBRID_CSV, index=False)
    # Default/combined raw files remain the hybrid view (generate_dataset no
    # longer synthesizes hybrid; these are the real-data copies).
    df.to_parquet(OUT_DEFAULT_PARQUET, index=False)
    df.to_csv(OUT_DEFAULT_CSV, index=False)
    log.info('Wrote hybrid raw files: %s', OUT_HYBRID_PARQUET)


if __name__ == '__main__':
    main()