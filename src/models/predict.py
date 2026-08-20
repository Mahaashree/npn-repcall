#!/usr/bin/env python3
"""
predict.py
==========
Predictive-scoring stage: load the persisted best model for each dataset mode,
derive the identical feature matrix used at training time, and write per-HCP
predicted Rx_Lift_Pct to root-level JSON artifacts consumed by the dashboard
export stage.

Input:   src/models/artifacts/best_{hybrid,synthetic}.joblib
         processed_data_{hybrid,synthetic}.parquet
Output:  predicted_rx_lift_{hybrid,synthetic}.json
"""

from __future__ import annotations
import argparse
import json
import logging
import pathlib

import joblib
import numpy as np
import pandas as pd

try:
    from ml_models_suite import build_feature_matrix
except ImportError:  # imported as a package (tests), not run directly
    from src.models.ml_models_suite import build_feature_matrix

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = pathlib.Path(__file__).resolve().parent / 'artifacts'
META_PATH = ARTIFACTS_DIR / 'best_model_meta.json'


def predict_mode(mode: str) -> None:
    model_path = ARTIFACTS_DIR / f'best_{mode}.joblib'
    parquet_path = BASE_DIR / f'processed_data_{mode}.parquet'
    out_path = BASE_DIR / f'predicted_rx_lift_{mode}.json'

    if not model_path.exists():
        log.warning('No persisted model for mode "%s" (%s) — skipping.', mode, model_path)
        return
    if not parquet_path.exists():
        log.warning('No processed parquet for mode "%s" (%s) — skipping.', mode, parquet_path)
        return

    log.info('Predictive scoring [%s]...', mode)
    df = pd.read_parquet(parquet_path)
    X, feature_names, df = build_feature_matrix(df)
    model = joblib.load(model_path)

    preds = model.predict(X)

    npi_col = 'Prscrbr_NPI' if 'Prscrbr_NPI' in df.columns else df.columns[0]
    records = []
    for i, (_, row) in enumerate(df.iterrows()):
        records.append({
            'npi': str(row.get(npi_col, '')),
            'sales_rep': str(row.get('Sales_Rep', '')),
            'territory': str(row.get('Territory', '')),
            'actual_rx_lift_pct': float(row.get('Rx_Lift_Pct', 0.0)),
            'predicted_rx_lift_pct': float(round(float(preds[i]), 4)),
        })

    payload = {
        'mode': mode,
        'model_label': _meta_label(mode),
        'n_predictions': len(records),
        'feature_names': feature_names,
        'data': records,
    }

    out_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    log.info('Wrote %s (%d HCP predictions).', out_path, len(records))


def _meta_label(mode: str) -> str:
    try:
        meta = json.loads(META_PATH.read_text(encoding='utf-8'))
        return str(meta.get(mode, {}).get('model_label', 'Unknown'))
    except (json.JSONDecodeError, OSError):
        return 'Unknown'


def main() -> None:
    parser = argparse.ArgumentParser(description='Predictive-scoring inference stage')
    parser.add_argument('--mode', choices=['hybrid', 'synthetic', 'all'],
                        default='all', help='Which dataset mode to score (default: all)')
    args = parser.parse_args()

    modes = ['hybrid', 'synthetic'] if args.mode == 'all' else [args.mode]
    for mode in modes:
        predict_mode(mode)


if __name__ == '__main__':
    main()