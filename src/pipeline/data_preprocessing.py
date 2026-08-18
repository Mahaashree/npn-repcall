#!/usr/bin/env python3
"""
data_preprocessing.py
=====================
Ingest raw_crm_cms_dataset.parquet, apply CMS-style small-cell suppression
and data validity filters, engineer features, z-score scale continuous
regressors, and export processed outputs for the analytics and ML stages.

Outputs:
  processed_data.parquet   — full processed HCP records
  processed_data.json      — same, for dashboard consumption
  pipeline_telemetry.json  — execution telemetry for pipeline inspector
"""

from __future__ import annotations
import json
import logging
import pathlib
import time

import numpy as np
import pandas as pd
from scipy.stats import zscore

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = pathlib.Path(__file__).resolve().parent.parent.parent
INPUT_PATH  = BASE_DIR / 'raw_crm_cms_dataset.parquet'
OUT_PARQUET = BASE_DIR / 'processed_data.parquet'
OUT_JSON    = BASE_DIR / 'processed_data.json'
OUT_TEL     = BASE_DIR / 'pipeline_telemetry.json'

# ── Columns to z-score scale (preserving _raw counterparts) ──────────────────
# NOTE: Rx_Lift_Pct is the ML target — intentionally NOT scaled here.
SCALE_COLS: list[str] = [
    'Compliance_Pct',
    'Monthly_Call_Frequency',
    'Sample_Velocity',
    'Log_Baseline_Fills',
    'Tot_30day_Fills',
    'Tot_Drug_Cst',
    'Tot_Clms',
]

# ── Text imputation defaults ──────────────────────────────────────────────────
SPEC_DEFAULT  = 'General Practice'
CITY_DEFAULT  = 'Unknown'
STATE_DEFAULT = 'Unknown'


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE STAGES
# ═══════════════════════════════════════════════════════════════════════════════
def load(path: pathlib.Path) -> pd.DataFrame:
    log.info('[Stage 1] Loading %s …', path)
    df = pd.read_parquet(path)
    log.info('  Loaded %d rows × %d cols.', len(df), len(df.columns))
    return df


def privacy_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 2 — Small-Cell Suppression (mirrors CMS public dataset disclosure rules).
    Rows with Tot_Clms < 11 represent prescribers with too few claims to be
    reported publicly, protecting against individual re-identification.
    """
    log.info('[Stage 2] Applying CMS small-cell suppression (Tot_Clms >= 11)…')
    before = len(df)
    df = df[df['Tot_Clms'] >= 11].copy()
    log.info('  Retained %d / %d rows (dropped %d).', len(df), before, before - len(df))
    return df


def validity_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 3 — Data validity: remove records with zero fills or zero drug cost."""
    log.info('[Stage 3] Applying data validity filters…')
    before = len(df)
    df = df[(df['Tot_30day_Fills'] >= 1.0) & (df['Tot_Drug_Cst'] > 0.0)].copy()
    log.info('  Retained %d / %d rows.', len(df), before)
    return df


def impute_text(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 4 — Impute missing text columns with domain defaults."""
    log.info('[Stage 4] Imputing missing text fields…')
    nulls_before = df[['Specialty', 'City', 'State']].isnull().sum().sum()
    df['Specialty'] = df['Specialty'].fillna(SPEC_DEFAULT)
    df['City']      = df['City'].fillna(CITY_DEFAULT)
    df['State']     = df['State'].fillna(STATE_DEFAULT)
    nulls_after = df[['Specialty', 'City', 'State']].isnull().sum().sum()
    log.info('  Imputed %d null(s).', nulls_before - nulls_after)
    return df, int(nulls_before - nulls_after)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 5 — Feature engineering.

    Compliance_Pct         = Actual_Calls / max(1, Target_Calls) × 100
    Monthly_Call_Frequency = Actual_Calls / 3.0
    Sample_Velocity        = Samples_Dropped / max(1, Actual_Calls)
    Log_Baseline_Fills     = ln(1 + Tot_30day_Fills)
    """
    log.info('[Stage 5] Engineering features…')
    df['Compliance_Pct']        = df['Actual_Calls'] / df['Target_Calls'].clip(lower=1) * 100.0
    df['Monthly_Call_Frequency']= df['Actual_Calls'] / 3.0
    df['Sample_Velocity']       = df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)
    df['Log_Baseline_Fills']    = np.log1p(df['Tot_30day_Fills'])
    log.info('  Compliance_Pct  mean=%.2f  std=%.2f',
             df['Compliance_Pct'].mean(), df['Compliance_Pct'].std())
    log.info('  Rx_Lift_Pct     mean=%.4f  std=%.4f  min=%.4f  max=%.4f',
             df['Rx_Lift_Pct'].mean(), df['Rx_Lift_Pct'].std(),
             df['Rx_Lift_Pct'].min(),  df['Rx_Lift_Pct'].max())
    return df


def scale_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 6 — Z-score standardisation of continuous regressors.
    Raw values are preserved in `<col>_raw` columns.
    Rx_Lift_Pct (the ML target) is intentionally NOT scaled.
    """
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

    # Enforce numeric dtypes
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


def export_outputs(df: pd.DataFrame, telemetry: dict) -> None:
    """Stage 7 — Export processed_data.parquet, .json, and pipeline_telemetry.json."""
    log.info('[Stage 7] Exporting outputs…')

    # Parquet
    df.to_parquet(OUT_PARQUET, index=False)
    log.info('  ✅ %s  (%d rows × %d cols)', OUT_PARQUET, len(df), len(df.columns))

    # JSON — convert numpy types for JSON serialiser
    records = df.to_dict(orient='records')
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):    rec[k] = int(v)
            elif isinstance(v, (np.floating,)): rec[k] = float(v)
            elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)): rec[k] = None
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, separators=(',', ':'))
    log.info('  ✅ %s  (%.1f KB)', OUT_JSON, OUT_JSON.stat().st_size / 1024)

    # Telemetry
    with open(OUT_TEL, 'w', encoding='utf-8') as f:
        json.dump(telemetry, f, indent=2)
    log.info('  ✅ %s', OUT_TEL)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    t_global = time.perf_counter()

    df = load(INPUT_PATH)
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
                                'Sample_Velocity', 'Log_Baseline_Fills'],
        'target_col':          'Rx_Lift_Pct',
    }

    export_outputs(df, telemetry)

    log.info('Pipeline completed in %.4fs — %d HCP records ready.', elapsed, retained_rows)
    log.info('Final column set: %s', list(df.columns))


if __name__ == '__main__':
    main()
