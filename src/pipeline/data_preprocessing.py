from __future__ import annotations
import json
import logging
import pathlib
import time

import numpy as np
import pandas as pd
from scipy.stats import zscore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR    = pathlib.Path(__file__).resolve().parent.parent.parent
RAW_DIR     = BASE_DIR / 'data' / 'generated' / 'raw'
PROCESSED_DIR = BASE_DIR / 'data' / 'generated' / 'processed'
ANALYTICS_DIR = BASE_DIR / 'data' / 'generated' / 'analytics'
INPUT_PATH  = RAW_DIR / 'raw_crm_cms_dataset.parquet'
OUT_PARQUET = PROCESSED_DIR / 'processed_data.parquet'
OUT_JSON    = PROCESSED_DIR / 'processed_data.json'
OUT_TEL     = ANALYTICS_DIR / 'pipeline_telemetry.json'

SCALE_COLS: list[str] = [
    'Compliance_Pct',
    'Monthly_Call_Frequency',
    'Sample_Velocity',
    'Log_Baseline_Fills',
    'Diminishing_Call_Log',
    'Tier_Compliance_Interaction',
    'Sample_Call_Ratio',
    'Tot_30day_Fills',
    'Tot_Drug_Cst',
    'Tot_Clms',
]

SPEC_DEFAULT  = 'General Practice'
CITY_DEFAULT  = 'Unknown'
STATE_DEFAULT = 'Unknown'


def load(path: pathlib.Path) -> pd.DataFrame:
    log.info('[Stage 1] Loading %s …', path)
    df = pd.read_parquet(path)
    log.info('  Loaded %d rows × %d cols.', len(df), len(df.columns))
    return df


def privacy_filter(df: pd.DataFrame) -> pd.DataFrame:
    log.info('[Stage 2] Applying CMS small-cell suppression (Tot_Clms >= 11)…')
    before = len(df)
    df = df[df['Tot_Clms'] >= 11].copy()
    log.info('  Retained %d / %d rows (dropped %d).', len(df), before, before - len(df))
    return df


def validity_filter(df: pd.DataFrame) -> pd.DataFrame:
    log.info('[Stage 3] Applying data validity filters…')
    before = len(df)
    df = df[(df['Tot_30day_Fills'] >= 1.0) & (df['Tot_Drug_Cst'] > 0.0)].copy()
    log.info('  Retained %d / %d rows.', len(df), before)
    return df


def impute_text(df: pd.DataFrame) -> pd.DataFrame:
    log.info('[Stage 4] Imputing missing text fields…')
    nulls_before = df[['Specialty', 'City', 'State']].isnull().sum().sum()
    df['Specialty'] = df['Specialty'].fillna(SPEC_DEFAULT)
    df['City']      = df['City'].fillna(CITY_DEFAULT)
    df['State']     = df['State'].fillna(STATE_DEFAULT)
    nulls_after = df[['Specialty', 'City', 'State']].isnull().sum().sum()
    log.info('  Imputed %d null(s).', nulls_before - nulls_after)
    return df, int(nulls_before - nulls_after)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info('[Stage 5] Engineering domain features for Hybrid Approach 2…')
    df['CMS_Volume_Decile']            = pd.qcut(df['Tot_30day_Fills'], q=10, labels=False, duplicates='drop').astype(float) + 1.0
    df['Compliance_Pct']               = df['Actual_Calls'] / df['Target_Calls'].clip(lower=1) * 100.0
    df['Monthly_Call_Frequency']       = df['Actual_Calls'] / 3.0
    df['Sample_Velocity']              = df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)
    df['Log_Baseline_Fills']           = np.log1p(df['Tot_30day_Fills'])
    df['Diminishing_Call_Log']        = np.log1p(df['Actual_Calls'])
    df['Tier_Compliance_Interaction'] = df['Compliance_Pct'] * df['CMS_Volume_Decile']
    df['Sample_Call_Ratio']           = df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)
    spec_means                         = df.groupby('Specialty')['Tot_30day_Fills'].transform('mean').clip(lower=1.0)
    df['Baseline_Volume_Saturation']  = df['Tot_30day_Fills'] / spec_means
    df['Delta_Log_Fills']             = np.log1p(df['Post_Campaign_Fills']) - np.log1p(df['Tot_30day_Fills'])
    log.info('  Compliance_Pct  mean=%.2f  std=%.2f',
             df['Compliance_Pct'].mean(), df['Compliance_Pct'].std())
    log.info('  Rx_Lift_Pct     mean=%.4f  std=%.4f  min=%.4f  max=%.4f',
             df['Rx_Lift_Pct'].mean(), df['Rx_Lift_Pct'].std(),
             df['Rx_Lift_Pct'].min(),  df['Rx_Lift_Pct'].max())
    return df


def scale_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info('[Stage 6] Z-score scaling %d continuous columns…', len(SCALE_COLS))
    for col in SCALE_COLS:
        if col not in df.columns:
            log.warning('  Column %r not found — skipping.', col)
            continue
        df[f'{col}_raw'] = df[col].astype(float)
        mu  = df[col].mean()
        sig = df[col].std(ddof=1)
        if sig > 0:
            df[col] = (df[col] - mu) / sig
        else:
            df[col] = 0.0
        log.info('  %-26s  μ_raw=%.4f  σ_raw=%.4f', col, mu, sig)

    for col in SCALE_COLS:
        df[col]             = pd.to_numeric(df[col], errors='coerce').astype('float64')
        raw_col = f'{col}_raw'
        if raw_col in df.columns:
            df[raw_col] = pd.to_numeric(df[raw_col], errors='coerce').astype('float64')

    df['HCP_Tier']       = df['HCP_Tier'].astype('int64')
    df['Target_Calls']   = df['Target_Calls'].astype('int64')
    df['Actual_Calls']   = df['Actual_Calls'].astype('int64')
    df['Samples_Dropped']= df['Samples_Dropped'].astype('int64')
    df['Rx_Lift_Pct']    = df['Rx_Lift_Pct'].astype('float64')
    return df


def process_file(in_path: pathlib.Path, out_parquet: pathlib.Path, out_json: pathlib.Path, out_tel: pathlib.Path):
    t_global = time.perf_counter()

    df = load(in_path)
    initial_rows = len(df)

    df = privacy_filter(df)
    after_privacy = len(df)

    df = validity_filter(df)
    retained_rows = len(df)

    df, nulls_imputed = impute_text(df)
    df = engineer_features(df)
    df = scale_features(df)

    elapsed = round(time.perf_counter() - t_global, 6)

    telemetry = {
        'initial_rows':        initial_rows,
        'after_privacy_filter': after_privacy,
        'retained_rows':       retained_rows,
        'suppressed_rows':     initial_rows - after_privacy,
        'dropped_rows':        initial_rows - retained_rows,
        'nulls_imputed':       nulls_imputed,
        'execution_time_sec':  elapsed,
        'scale_cols':          SCALE_COLS,
        'feature_cols':        ['Compliance_Pct', 'Monthly_Call_Frequency',
                                'Sample_Velocity', 'Log_Baseline_Fills', 'Diminishing_Call_Log', 'Tier_Compliance_Interaction'],
        'target_col':          'Rx_Lift_Pct',
    }

    df.to_parquet(out_parquet, index=False)
    df.to_csv(out_parquet.with_suffix('.csv'), index=False)

    records = df.to_dict(orient='records')
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):    rec[k] = int(v)
            elif isinstance(v, (np.floating,)): rec[k] = float(v)
            elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)): rec[k] = None
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, separators=(',', ':'))

    with open(out_tel, 'w', encoding='utf-8') as f:
        json.dump(telemetry, f, indent=2)


def main() -> None:
    in_hybrid = RAW_DIR / 'raw_crm_cms_dataset_hybrid.parquet'
    in_synth  = RAW_DIR / 'raw_crm_cms_dataset_synthetic.parquet'

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

    out_hybrid_pq   = PROCESSED_DIR / 'processed_data_hybrid.parquet'
    out_hybrid_json = PROCESSED_DIR / 'processed_data_hybrid.json'
    out_hybrid_tel  = ANALYTICS_DIR / 'pipeline_telemetry_hybrid.json'

    out_synth_pq   = PROCESSED_DIR / 'processed_data_synthetic.parquet'
    out_synth_json = PROCESSED_DIR / 'processed_data_synthetic.json'
    out_synth_tel  = ANALYTICS_DIR / 'pipeline_telemetry_synthetic.json'

    if not in_hybrid.exists():
        in_hybrid = INPUT_PATH
    if not in_synth.exists():
        in_synth = INPUT_PATH

    process_file(in_hybrid, out_hybrid_pq, out_hybrid_json, out_hybrid_tel)
    process_file(in_synth, out_synth_pq, out_synth_json, out_synth_tel)

    log.info('Pipeline completed processing for hybrid and synthetic modes.')


if __name__ == '__main__':
    main()
