#!/usr/bin/env python3
"""
ml_models_suite.py
==================
Benchmark 4 regression models predicting Rx_Lift_Pct at the HCP level.
Strictly leakage-free: target is Rx_Lift_Pct (the campaign effect, bounded
-3% to +18%), derived from the causal formula in generate_dataset.py.
Post_Campaign_Fills is excluded from features.

Partitioning: 70% Train / 10% Validation / 20% Held-Out Test
Cross-validation: 5-Fold strictly within the 70% training split.
Explainability: SHAP values (LinearExplainer / TreeExplainer).

Output: ml_benchmarks.json
"""

from __future__ import annotations
import json
import logging
import pathlib
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import shap

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    warnings.warn('XGBoost not available; substituting GradientBoostingRegressor.')

warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR    = pathlib.Path(__file__).resolve().parent.parent.parent
INPUT_PATH  = BASE_DIR / 'processed_data.parquet'
OUTPUT_PATH = BASE_DIR / 'ml_benchmarks.json'
SEED        = 42
N_BOOTSTRAP = 1000
CV_FOLDS    = 5

# Features (raw/unscaled versions — linear models use StandardScaler pipeline)
FEATURE_COLS: list[str] = [
    'Compliance_Pct_raw',
    'Monthly_Call_Frequency_raw',
    'Sample_Velocity_raw',
    'Log_Baseline_Fills_raw',
    'HCP_Tier',         # ordinal: 1=high, 2=medium, 3=low
]
TARGET_COL = 'Rx_Lift_Pct'

# Columns that must NOT appear in features (leakage prevention)
LEAKAGE_COLS: set[str] = {
    'Post_Campaign_Fills',
    'Rx_Lift_Pct',
}


def safe_json(v):
    if isinstance(v, (np.integer,)):    return int(v)
    if isinstance(v, (np.floating,)):   return float(v)
    if isinstance(v, np.ndarray):       return v.tolist()
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)): return None
    return v


def bootstrap_ci(y_true, y_pred, n=N_BOOTSTRAP, seed=SEED):
    rng   = np.random.default_rng(seed)
    stats = []
    for _ in range(n):
        idx = rng.integers(0, len(y_true), len(y_true))
        try:
            stats.append(r2_score(y_true[idx], y_pred[idx]))
        except Exception:
            pass
    stats = np.array(stats)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def load_and_partition(path: pathlib.Path):
    log.info('[Stage 1] Loading and partitioning data...')
    df = pd.read_parquet(path)
    log.info('  Loaded %d HCP records.', len(df))

    # Ensure raw feature columns exist
    for col in ['Compliance_Pct', 'Monthly_Call_Frequency', 'Sample_Velocity', 'Log_Baseline_Fills']:
        raw_col = f'{col}_raw'
        if raw_col not in df.columns:
            if col in df.columns:
                df[raw_col] = df[col].copy()
            elif col == 'Monthly_Call_Frequency':
                df[raw_col] = df['Actual_Calls'] / 3.0
            elif col == 'Sample_Velocity':
                df[raw_col] = df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)
            elif col == 'Log_Baseline_Fills':
                df[raw_col] = np.log1p(df['Tot_30day_Fills_raw'] if 'Tot_30day_Fills_raw' in df.columns else df['Tot_30day_Fills'])
            elif col == 'Compliance_Pct':
                df[raw_col] = df['Actual_Calls'] / df['Target_Calls'].clip(lower=1) * 100

    available_features = [c for c in FEATURE_COLS if c in df.columns]
    missing_features   = [c for c in FEATURE_COLS if c not in df.columns]
    if missing_features:
        log.warning('  Missing feature columns: %s', missing_features)

    X = df[available_features].fillna(0).astype(float).values
    y = df[TARGET_COL].astype(float).values

    log.info('  Feature matrix: %d samples x %d features.', X.shape[0], X.shape[1])
    log.info('  Target (Rx_Lift_Pct): mean=%.4f  std=%.4f  [%.4f, %.4f]',
             y.mean(), y.std(), y.min(), y.max())

    # 70 / 10 / 20 strict split (no leakage through shuffling)
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.20, random_state=SEED)
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.20 / 0.80, random_state=SEED)
    # 0.20/0.80 gives 10% of total for val

    log.info('  Partition: train=%d  val=%d  test=%d  (total=%d)',
             len(X_train), len(X_val), len(X_test), len(X))
    return X_train, X_val, X_test, y_train, y_val, y_test, available_features, df


def benchmark_model(name: str, key: str, model_family: str, model, X_train, X_val, X_test,
                    y_train, y_val, y_test, feature_names, df_for_shap) -> dict:
    log.info('  Benchmarking: %s', name)
    t0 = time.perf_counter()

    # 5-Fold CV within train split
    log.info('    Running 5-fold intra-train CV...')
    cv_scores = cross_val_score(model, X_train, y_train, cv=CV_FOLDS,
                                scoring='r2', n_jobs=-1)
    cv_mean = float(cv_scores.mean())
    cv_std  = float(cv_scores.std())
    log.info('    CV R2: %.4f +/- %.4f', cv_mean, cv_std)

    # Fit on full train split
    log.info('    Fitting on full train split...')
    model.fit(X_train, y_train)

    y_train_pred = model.predict(X_train)
    y_val_pred   = model.predict(X_val)
    y_test_pred  = model.predict(X_test)

    train_r2 = float(r2_score(y_train, y_train_pred))
    val_r2   = float(r2_score(y_val,   y_val_pred))
    test_r2  = float(r2_score(y_test,  y_test_pred))
    test_mae = float(mean_absolute_error(y_test, y_test_pred))
    test_rmse= float(np.sqrt(mean_squared_error(y_test, y_test_pred)))
    overfit_gap = round(train_r2 - test_r2, 6)

    # Bootstrap CI
    log.info('    Running 1000-sample bootstrap CI...')
    ci_lo, ci_hi = bootstrap_ci(y_test, y_test_pred)

    # Feature importance
    log.info('    Computing feature importance and SHAP...')
    fi_pct, shap_pct, shap_method = _importance(model, model_family,
                                                  X_train, X_test, feature_names)

    elapsed = time.perf_counter() - t0
    log.info('    Done - Train R2=%.4f | CV=%.4f+/-%.4f | Val R2=%.4f | Test R2=%.4f | %.2fs',
             train_r2, cv_mean, cv_std, val_r2, test_r2, elapsed)

    return {
        'model_label':          name,
        'model_key':            key,
        'model_family':         model_family,
        'in_sample_train_r2':   round(train_r2, 6),
        'intra_train_cv': {
            'folds':      CV_FOLDS,
            'mean_r2':    round(cv_mean, 6),
            'std_r2':     round(cv_std,  6),
            'fold_scores': [round(s, 6) for s in cv_scores.tolist()],
        },
        'validation_r2':       round(val_r2, 6),
        'test_r2':             round(test_r2, 6),
        'test_mae':            round(test_mae, 6),
        'test_rmse':           round(test_rmse, 6),
        'bootstrap_95pct_ci_test_r2': {
            'lower_bound':  round(ci_lo, 6),
            'upper_bound':  round(ci_hi, 6),
            'n_iterations': N_BOOTSTRAP,
        },
        'overfitting': {
            'gap':        round(overfit_gap, 6),
            'assessment': 'Healthy generalisation' if abs(overfit_gap) < 0.15 else
                          ('Moderate overfit' if overfit_gap < 0.30 else 'Severe overfit'),
        },
        'feature_importance': {
            'global_importance_method': 'permutation' if model_family in ('Ensemble', 'Gradient Boosting') else 'abs_coefficient',
            'global_importance_pct':    fi_pct,
            'global_importance_ranked': [
                {'rank': i+1, 'feature': fn, 'importance_pct': round(fi_pct[fn], 4)}
                for i, fn in enumerate(sorted(fi_pct, key=fi_pct.get, reverse=True))
            ],
            'shap_method':              shap_method,
            'shap_importance_pct':      shap_pct,
            'shap_importance_ranked': [
                {'rank': i+1, 'feature': fn, 'shap_importance_pct': round(shap_pct[fn], 4)}
                for i, fn in enumerate(sorted(shap_pct, key=shap_pct.get, reverse=True))
            ],
        },
        'fit_time_sec': round(elapsed, 4),
    }


def _importance(model, family, X_train, X_test, feature_names):
    """Compute global feature importance and SHAP values."""
    n   = len(feature_names)
    eps = 1e-9

    # ── Global importance ─────────────────────────────────────────────────────
    if family == 'Linear':
        # abs(coef) for pipeline with StandardScaler
        if hasattr(model, 'named_steps'):
            coef = np.abs(model.named_steps['model'].coef_)
        else:
            coef = np.abs(model.coef_)
        total = coef.sum() + eps
        fi_pct = {fn: round(float(c / total * 100), 4) for fn, c in zip(feature_names, coef)}
    else:
        # Tree-based: feature_importances_
        if hasattr(model, 'feature_importances_'):
            imp = model.feature_importances_
        else:
            imp = np.ones(n) / n
        total = imp.sum() + eps
        fi_pct = {fn: round(float(v / total * 100), 4) for fn, v in zip(feature_names, imp)}

    # ── SHAP ─────────────────────────────────────────────────────────────────
    try:
        if family == 'Linear':
            if hasattr(model, 'named_steps'):
                scaler = model.named_steps['scaler']
                inner  = model.named_steps['model']
                X_bg_s = scaler.transform(X_train[:50])
                X_ts_s = scaler.transform(X_test)
                explainer = shap.LinearExplainer(inner, X_bg_s)
                shap_vals = explainer.shap_values(X_ts_s)
            else:
                explainer = shap.LinearExplainer(model, X_train[:50])
                shap_vals = explainer.shap_values(X_test)
            shap_method = 'SHAP_LinearExplainer'
        else:
            if hasattr(model, 'get_booster'):
                explainer = shap.TreeExplainer(model)
            else:
                explainer = shap.TreeExplainer(model)
            shap_vals = explainer.shap_values(X_test)
            shap_method = 'SHAP_TreeExplainer'

        mean_abs_shap = np.abs(shap_vals).mean(axis=0)
        s_total = mean_abs_shap.sum() + eps
        shap_pct = {fn: round(float(v / s_total * 100), 4)
                    for fn, v in zip(feature_names, mean_abs_shap)}
    except Exception as e:
        log.warning('    SHAP failed (%s) — using global importance as proxy.', e)
        shap_pct   = fi_pct.copy()
        shap_method = 'fallback_global'

    return fi_pct, shap_pct, shap_method


def main() -> None:
    t_global = time.perf_counter()
    log.info('=' * 65)
    log.info('Pharma CRM - ML Benchmarking Suite  START')
    log.info('=' * 65)

    X_train, X_val, X_test, y_train, y_val, y_test, feat_names, df = \
        load_and_partition(INPUT_PATH)

    # Model definitions
    models = [
        ('OLS Linear Regression',  'OLS_LinearRegression',  'Linear',
         Pipeline([('scaler', StandardScaler()), ('model', LinearRegression())])),
        ('Ridge Regression (L2, a=1.0)', 'Ridge_Regression', 'Linear',
         Pipeline([('scaler', StandardScaler()), ('model', Ridge(alpha=1.0))])),
        ('Random Forest Regressor', 'RandomForest', 'Ensemble',
         RandomForestRegressor(n_estimators=200, max_depth=6, random_state=SEED, n_jobs=-1)),
    ]
    if HAS_XGB:
        models.append(('XGBoost Regressor', 'XGBoost', 'Gradient Boosting',
                       XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.08,
                                    subsample=0.8, random_state=SEED, verbosity=0)))
    else:
        models.append(('Gradient Boosting Regressor', 'GradientBoosting', 'Gradient Boosting',
                       GradientBoostingRegressor(n_estimators=200, max_depth=5,
                                                  learning_rate=0.08, random_state=SEED)))

    log.info('[Stage 2-5] Benchmarking %d models...', len(models))
    benchmarks = []
    for name, key, family, model in models:
        bm = benchmark_model(name, key, family, model,
                             X_train, X_val, X_test,
                             y_train, y_val, y_test,
                             feat_names, df)
        benchmarks.append(bm)

    # Tournament table (ranked by Test R2)
    log.info('[Stage 6] Building tournament comparison table...')
    ranked = sorted(benchmarks, key=lambda b: b['test_r2'], reverse=True)
    tournament = []
    for rank, b in enumerate(ranked, start=1):
        tournament.append({
            'rank':               rank,
            'model_label':        b['model_label'],
            'model_family':       b['model_family'],
            'in_sample_train_r2': b['in_sample_train_r2'],
            'cv_mean_r2':         b['intra_train_cv']['mean_r2'],
            'cv_std_r2':          b['intra_train_cv']['std_r2'],
            'validation_r2':      b['validation_r2'],
            'test_r2':            b['test_r2'],
            'test_mae':           b['test_mae'],
            'test_rmse':          b['test_rmse'],
            'bootstrap_ci_lower': b['bootstrap_95pct_ci_test_r2']['lower_bound'],
            'bootstrap_ci_upper': b['bootstrap_95pct_ci_test_r2']['upper_bound'],
            'overfitting_gap':    b['overfitting']['gap'],
            'overfitting_status': b['overfitting']['assessment'],
            'fit_time_sec':       b['fit_time_sec'],
        })
        log.info('  #%d %-35s Test R2=%.4f  MAE=%.4f  RMSE=%.4f  Gap=%+.4f',
                 rank, b['model_label'], b['test_r2'], b['test_mae'], b['test_rmse'],
                 b['overfitting']['gap'])

    best = ranked[0]
    best_summary = {
        'rank':           1,
        'model_label':    best['model_label'],
        'test_r2':        best['test_r2'],
        'test_mae':       best['test_mae'],
        'test_rmse':      best['test_rmse'],
        'bootstrap_ci':   f"[{best['bootstrap_95pct_ci_test_r2']['lower_bound']:.4f}, {best['bootstrap_95pct_ci_test_r2']['upper_bound']:.4f}]",
        'overfitting_gap': best['overfitting']['gap'],
        'status':          best['overfitting']['assessment'],
    }
    log.info('Best model: %s  [Test R2=%.4f]', best['model_label'], best['test_r2'])

    partition_sizes = {
        'train_rows': int(len(X_train)), 'train_pct': round(len(X_train)/(len(X_train)+len(X_val)+len(X_test))*100, 1),
        'val_rows':   int(len(X_val)),   'val_pct':   round(len(X_val)/(len(X_train)+len(X_val)+len(X_test))*100, 1),
        'test_rows':  int(len(X_test)),  'test_pct':  round(len(X_test)/(len(X_train)+len(X_val)+len(X_test))*100, 1),
    }

    output = {
        'metadata': {
            'source_file':         str(INPUT_PATH),
            'target_variable':     TARGET_COL,
            'target_description':  'Rx_Lift_Pct: campaign effect, bounded -3% to +18%',
            'n_samples':           int(len(X_train) + len(X_val) + len(X_test)),
            'n_features':          int(len(feat_names)),
            'feature_names':       feat_names,
            'partition':           partition_sizes,
            'cv_folds':            CV_FOLDS,
            'bootstrap_iterations': N_BOOTSTRAP,
            'leakage_exclusions':  sorted(LEAKAGE_COLS),
            'total_wall_time_sec': round(time.perf_counter() - t_global, 4),
        },
        'benchmarks':       benchmarks,
        'tournament_table': tournament,
        'best_model_summary': best_summary,
    }

    # Verification
    log.info('[Stage 8] Verifying output integrity...')
    assert len(output['benchmarks']) == len(models)
    assert output['tournament_table'][0]['rank'] == 1
    assert output['best_model_summary']['test_r2'] is not None
    log.info('  All verification checks passed.')

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=safe_json)
    log.info('Exported %s (%.1f KB).', OUTPUT_PATH, OUTPUT_PATH.stat().st_size / 1024)
    log.info('Suite completed in %.2f seconds.', time.perf_counter() - t_global)


if __name__ == '__main__':
    main()
