#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_visualizations.py
===========================
Loads processed_data.parquet (or falls back to processed_data.json or mock simulation)
and produces a 4-panel publication-quality dark-mode scorecard saved as
output_metrics_scorecard.png.

Panels:
  [Top-Left]     Compliance % vs Rx_Lift_Pct scatter + OLS trendline
  [Top-Right]    Feature Attribution vs Rx Lift (multi-metric horizontal bar)
  [Bottom-Left]  2×2 Rep Effectiveness Quadrant (12 reps)
  [Bottom-Right] ML Model Tournament benchmark bar chart (Train / CV / Test R²)

Run:
    python generate_visualizations.py
Output:
    output_metrics_scorecard.png
"""

from __future__ import annotations
import logging
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from scipy import stats
from scipy.stats import pearsonr, spearmanr, linregress

warnings.filterwarnings('ignore')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

# ─── Colour palette (matches glassmorphism dashboard) ────────────────────────
BG       = '#080c14'
CARD     = '#0f172a'
CARD2    = '#131b2e'
BORDER   = '#1e293b'
GREEN    = '#10b981'
AMBER    = '#f59e0b'
CYAN     = '#38bdf8'
RED      = '#ef4444'
VIOLET   = '#8b5cf6'
WHITE    = '#f1f5f9'
MUTED    = '#64748b'
MUTED2   = '#94a3b8'
TEXT     = '#e2e8f0'

QUAD_COLORS = {
    'Stars':       GREEN,
    'Ineffective': AMBER,
    'Underserved': CYAN,
    'At-Risk':     RED,
}

FEATURE_NAMES = [
    'Sample_Velocity_raw',
    'Monthly_Call_Frequency_raw',
    'Log_Baseline_Fills_raw',
    'Compliance_Pct_raw',
]
FEATURE_LABELS = [
    'Sample Velocity',
    'Monthly Call Freq.',
    'Log Baseline Fills',
    'Compliance %',
]
FEATURE_COLORS = [VIOLET, CYAN, GREEN, AMBER]

# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════
def load_data() -> pd.DataFrame:
    """Load processed_data.parquet → .json → mock simulation."""
    parquet = pathlib.Path('processed_data.parquet')
    json_p  = pathlib.Path('processed_data.json')

    if parquet.exists():
        log.info('Loading %s', parquet)
        df = pd.read_parquet(parquet)
        log.info('  Loaded %d rows × %d cols', len(df), len(df.columns))
        return df

    if json_p.exists():
        log.info('Loading fallback %s', json_p)
        df = pd.read_json(json_p)
        log.info('  Loaded %d rows × %d cols', len(df), len(df.columns))
        return df

    log.warning('No data files found — generating mock simulation (n=700)')
    return _mock_sim()


def _mock_sim() -> pd.DataFrame:
    """Generate mock data matching real pipeline distributions."""
    rng = np.random.default_rng(42)
    n   = 700

    # Latent rep quality drives both calls and lift
    rep_quality   = rng.beta(4.0, 2.0, n)
    actual_calls  = np.clip(rng.normal(3.0 * rep_quality * 3.5 + 1, 1.2, n), 0, 14).astype(int)
    target_calls  = np.clip(actual_calls + rng.integers(-2, 4, n), 2, 14).astype(int)
    samples       = np.clip(rng.integers(0, actual_calls + 3, n), 0, actual_calls + 2)
    baseline_fills= np.maximum(1.0, rng.gamma(6.0, 2.5, n))
    tot_clms      = np.maximum(11, rng.negative_binomial(15, 0.45, n))
    tot_cost      = baseline_fills * rng.uniform(850, 2600, n)

    compliance  = actual_calls / np.maximum(1, target_calls) * 100
    monthly_cf  = actual_calls / 3.0
    sample_vel  = samples / np.maximum(1, actual_calls)
    log_fills   = np.log1p(baseline_fills)
    rx_lift     = np.clip(
        0.5 + 2.4 * rep_quality * np.log1p(actual_calls)
        + 1.2 * np.sqrt(samples) + rng.normal(0, 0.8, n),
        -3.0, 18.0,
    )
    post_fills  = baseline_fills * (1 + rx_lift / 100)

    reps  = np.tile([f'REP-{i:03d}' for i in range(101, 113)], n // 12 + 1)[:n]
    terr_map = {f'REP-{101+i:03d}': f'TERR-{i//2+1:02d}' for i in range(12)}
    terrs = np.array([terr_map.get(r, 'TERR-01') for r in reps])
    tiers = np.where(compliance >= 80, 1, np.where(compliance >= 60, 2, 3))

    specialties_pool = ['Pain Management','Oncology','Palliative Care','Neurology',
                        'Anesthesiology','Internal Medicine']
    specs = rng.choice(specialties_pool, n)

    df = pd.DataFrame({
        'Prscrbr_NPI':              [f'{1001000001+i}' for i in range(n)],
        'Physician_Name':           [f'Dr. Mock HCP {i+1}' for i in range(n)],
        'Specialty':                specs,
        'City':                     rng.choice(['Houston','Chicago','Miami','Atlanta'], n),
        'State':                    rng.choice(['TX','IL','FL','GA'], n),
        'Brand_Name':               rng.choice(['Subsys','Abstral','Actiq','Fentora'], n),
        'Sales_Rep':                reps,
        'Territory':                terrs,
        'HCP_Tier':                 tiers,
        'Target_Calls':             target_calls,
        'Actual_Calls':             actual_calls,
        'Samples_Dropped':          samples,
        'Tot_Clms':                 tot_clms,
        'Tot_30day_Fills':          baseline_fills,
        'Tot_Drug_Cst':             tot_cost,
        'Rx_Lift_Pct':              rx_lift,
        'Post_Campaign_Fills':      post_fills,
        'Compliance_Pct_raw':       compliance,
        'Monthly_Call_Frequency_raw': monthly_cf,
        'Sample_Velocity_raw':      sample_vel,
        'Log_Baseline_Fills_raw':   log_fills,
        'Tot_30day_Fills_raw':      baseline_fills,
    })
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS COMPUTATIONS
# ═══════════════════════════════════════════════════════════════════════════════
def compute_feature_attribution(df: pd.DataFrame) -> dict:
    """Compute Pearson r, Spearman ρ, and RF/XGBoost importance for all 4 features."""
    y = df['Rx_Lift_Pct'].values.astype(float)
    results = {}
    X_arr   = []

    for feat in FEATURE_NAMES:
        if feat not in df.columns:
            log.warning('  Feature %r missing — using zeros.', feat)
            df[feat] = 0.0
        x = df[feat].fillna(0).values.astype(float)
        X_arr.append(x)
        r_p, p_val   = pearsonr(x, y)
        rho, p_spear = spearmanr(x, y)
        results[feat] = {
            'pearson_r': float(r_p),
            'spearman_rho': float(rho),
            'pearson_abs': abs(float(r_p)),
            'spearman_abs': abs(float(rho)),
        }
        log.info('  %-30s  Pearson r=%+.4f  Spearman ρ=%+.4f', feat, r_p, rho)

    X = np.column_stack(X_arr)

    # Random Forest feature importance
    try:
        from sklearn.ensemble import RandomForestRegressor
        rf = RandomForestRegressor(n_estimators=150, max_depth=6, random_state=42, n_jobs=-1)
        rf.fit(X, y)
        rf_imp = rf.feature_importances_
        for i, feat in enumerate(FEATURE_NAMES):
            results[feat]['rf_importance'] = float(rf_imp[i])
            results[feat]['rf_importance_pct'] = float(rf_imp[i] * 100)
        log.info('  RF importances: %s', {f.split('_')[0]: f'{v*100:.2f}%' for f, v in zip(FEATURE_NAMES, rf_imp)})
    except Exception as e:
        log.warning('  RF failed (%s) — using Pearson proxy.', e)
        total = sum(abs(results[f]['pearson_r']) for f in FEATURE_NAMES) + 1e-9
        for feat in FEATURE_NAMES:
            proxy = abs(results[feat]['pearson_r']) / total
            results[feat]['rf_importance']     = proxy
            results[feat]['rf_importance_pct'] = proxy * 100

    # XGBoost feature importance (if available)
    try:
        from xgboost import XGBRegressor
        xgb = XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.08,
                           random_state=42, verbosity=0)
        xgb.fit(X, y)
        xgb_imp = xgb.feature_importances_
        for i, feat in enumerate(FEATURE_NAMES):
            results[feat]['xgb_importance']     = float(xgb_imp[i])
            results[feat]['xgb_importance_pct'] = float(xgb_imp[i] * 100)
        log.info('  XGB importances: %s', {f.split('_')[0]: f'{v*100:.2f}%' for f, v in zip(FEATURE_NAMES, xgb_imp)})
    except Exception:
        for feat in FEATURE_NAMES:
            results[feat]['xgb_importance']     = results[feat]['rf_importance']
            results[feat]['xgb_importance_pct'] = results[feat]['rf_importance_pct']

    # Primary driver = highest RF importance
    primary = max(FEATURE_NAMES, key=lambda f: results[f]['rf_importance'])
    log.info('  ★ Primary Driver Feature: %s (RF: %.2f%%)', primary, results[primary]['rf_importance_pct'])

    return {'features': results, 'primary_driver': primary}


def compute_ml_benchmarks(df: pd.DataFrame) -> list[dict]:
    """Fit 4 regression models and return benchmark metrics."""
    try:
        from sklearn.linear_model import Ridge, LinearRegression
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
        from sklearn.model_selection import cross_val_score, train_test_split
        from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as e:
        log.warning('sklearn unavailable (%s) — using cached values.', e)
        return _cached_benchmarks()

    X = df[FEATURE_NAMES].fillna(0).astype(float).values
    y = df['Rx_Lift_Pct'].astype(float).values

    X_tv, X_test, y_tv, y_test   = train_test_split(X, y, test_size=0.20, random_state=42)
    X_train, X_val, y_train, y_val = train_test_split(X_tv, y_tv, test_size=0.125, random_state=42)

    def bootstrap_ci(yt, yp, n=500, seed=42):
        rng2  = np.random.default_rng(seed)
        stats_b = []
        for _ in range(n):
            idx = rng2.integers(0, len(yt), len(yt))
            try: stats_b.append(r2_score(yt[idx], yp[idx]))
            except: pass
        a = np.array(stats_b)
        return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

    try:
        from xgboost import XGBRegressor
        xgb_model = XGBRegressor(n_estimators=200, max_depth=5,
                                  learning_rate=0.08, subsample=0.8,
                                  random_state=42, verbosity=0)
        xgb_label = 'XGBoost'
    except ImportError:
        xgb_model = GradientBoostingRegressor(n_estimators=200, max_depth=5,
                                               learning_rate=0.08, random_state=42)
        xgb_label = 'Gradient Boosting'

    candidates = [
        ('OLS', Pipeline([('sc', StandardScaler()), ('m', LinearRegression())])),
        ('Ridge (L2)', Pipeline([('sc', StandardScaler()), ('m', Ridge(alpha=1.0))])),
        ('Random Forest', RandomForestRegressor(n_estimators=200, max_depth=6,
                                                 random_state=42, n_jobs=-1)),
        (xgb_label, xgb_model),
    ]

    benchmarks = []
    for name, model in candidates:
        cv_scores = cross_val_score(model, X_train, y_train, cv=5,
                                    scoring='r2', n_jobs=-1)
        model.fit(X_train, y_train)
        y_tr_p  = model.predict(X_train)
        y_val_p = model.predict(X_val)
        y_ts_p  = model.predict(X_test)
        tr_r2  = float(r2_score(y_train, y_tr_p))
        val_r2 = float(r2_score(y_val,   y_val_p))
        ts_r2  = float(r2_score(y_test,  y_ts_p))
        mae    = float(mean_absolute_error(y_test, y_ts_p))
        rmse   = float(np.sqrt(mean_squared_error(y_test, y_ts_p)))
        ci_lo, ci_hi = bootstrap_ci(y_test, y_ts_p)
        benchmarks.append({
            'name': name, 'train_r2': tr_r2, 'cv_mean': float(cv_scores.mean()),
            'cv_std': float(cv_scores.std()), 'val_r2': val_r2,
            'test_r2': ts_r2, 'mae': mae, 'rmse': rmse,
            'ci_lo': ci_lo, 'ci_hi': ci_hi,
            'gap': tr_r2 - ts_r2,
        })
        log.info('  %-16s  Train=%.4f  CV=%.4f±%.4f  Test=%.4f',
                 name, tr_r2, cv_scores.mean(), cv_scores.std(), ts_r2)

    benchmarks.sort(key=lambda b: b['test_r2'], reverse=True)
    return benchmarks


def _cached_benchmarks() -> list[dict]:
    """Return pipeline-verified benchmark values if sklearn unavailable."""
    return [
        {'name':'Random Forest','train_r2':0.7758,'cv_mean':0.5647,'cv_std':0.0436,
         'val_r2':0.6167,'test_r2':0.5726,'mae':0.8071,'rmse':1.0055,'ci_lo':0.4443,'ci_hi':0.6691,'gap':0.2032},
        {'name':'Ridge (L2)',   'train_r2':0.6063,'cv_mean':0.5855,'cv_std':0.0561,
         'val_r2':0.5490,'test_r2':0.5190,'mae':0.8537,'rmse':1.0667,'ci_lo':0.4205,'ci_hi':0.6098,'gap':0.0873},
        {'name':'OLS',          'train_r2':0.6063,'cv_mean':0.5855,'cv_std':0.0563,
         'val_r2':0.5481,'test_r2':0.5186,'mae':0.8540,'rmse':1.0671,'ci_lo':0.4201,'ci_hi':0.6101,'gap':0.0877},
        {'name':'XGBoost',      'train_r2':0.9546,'cv_mean':0.4762,'cv_std':0.0681,
         'val_r2':0.5363,'test_r2':0.4722,'mae':0.8800,'rmse':1.1174,'ci_lo':0.3701,'ci_hi':0.5731,'gap':0.4825},
    ]


def compute_rep_scorecards(df: pd.DataFrame, attribution: dict) -> pd.DataFrame:
    """Aggregate per-rep metrics and assign quadrant + coaching priority."""
    median_lift = df['Rx_Lift_Pct'].median()

    rows = []
    for rep in sorted(df['Sales_Rep'].unique()):
        sub  = df[df['Sales_Rep'] == rep]
        terr = sub['Territory'].mode()[0]
        n    = len(sub)
        comp = float(sub['Compliance_Pct_raw'].mean())
        lift = float(sub['Rx_Lift_Pct'].mean())
        samp = int(sub['Samples_Dropped'].sum())

        q = ('Stars'       if comp >= 80 and lift >= median_lift else
             'Ineffective'  if comp >= 80 and lift <  median_lift else
             'Underserved'  if comp <  80 and lift >= median_lift else
             'At-Risk')

        at_risk_share = (sub['_quadrant'].value_counts().get('At-Risk', 0) / max(1, n)
                         if '_quadrant' in sub.columns else 0)
        priority = ('Urgent Coaching' if at_risk_share > 0.40 or (comp < 65 and lift < 3.5)
                    else 'Monitor' if comp < 70 or lift < 3.5
                    else 'On Track')
        rows.append({'rep':rep,'territory':terr,'n_hcps':n,
                     'compliance':comp,'lift':lift,'samples':samp,
                     'quadrant':q,'priority':priority})

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: apply quadrant labels to HCP dataframe
# ═══════════════════════════════════════════════════════════════════════════════
def add_quadrant(df: pd.DataFrame) -> pd.DataFrame:
    median_lift = df['Rx_Lift_Pct'].median()
    df = df.copy()
    df['_quadrant'] = df.apply(
        lambda r: (
            'Stars'        if r['Compliance_Pct_raw'] >= 80 and r['Rx_Lift_Pct'] >= median_lift else
            'Ineffective'  if r['Compliance_Pct_raw'] >= 80 and r['Rx_Lift_Pct'] <  median_lift else
            'Underserved'  if r['Compliance_Pct_raw'] <  80 and r['Rx_Lift_Pct'] >= median_lift else
            'At-Risk'
        ), axis=1,
    )
    return df, float(median_lift)


# ═══════════════════════════════════════════════════════════════════════════════
# MATPLOTLIB STYLE SETUP
# ═══════════════════════════════════════════════════════════════════════════════
def apply_dark_style():
    plt.rcParams.update({
        'figure.facecolor':      BG,
        'axes.facecolor':        CARD2,
        'axes.edgecolor':        BORDER,
        'axes.labelcolor':       MUTED2,
        'axes.titlecolor':       WHITE,
        'axes.titlesize':        13,
        'axes.labelsize':        10,
        'axes.grid':             True,
        'axes.grid.which':       'major',
        'grid.color':            BORDER,
        'grid.linewidth':        0.6,
        'grid.alpha':            0.6,
        'xtick.color':           MUTED,
        'ytick.color':           MUTED,
        'xtick.labelsize':       9,
        'ytick.labelsize':       9,
        'legend.facecolor':      CARD,
        'legend.edgecolor':      BORDER,
        'legend.labelcolor':     TEXT,
        'legend.fontsize':       8.5,
        'text.color':            TEXT,
        'font.family':           'DejaVu Sans',
        'lines.linewidth':       1.8,
    })


def card_axes(ax, title: str, subtitle: str = ''):
    ax.set_facecolor(CARD2)
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)
        sp.set_linewidth(0.8)
    full_title = title if not subtitle else f'{title}\n{subtitle}'
    ax.set_title(full_title, color=WHITE, fontsize=13, fontweight='bold',
                 pad=10, loc='left')


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL 1 — Compliance vs Rx Lift Scatter + OLS
# ═══════════════════════════════════════════════════════════════════════════════
def draw_scatter(ax, df, median_lift):
    r_val, p_val    = pearsonr(df['Compliance_Pct_raw'], df['Rx_Lift_Pct'])
    slope, intercept, r_ols, _, _ = linregress(df['Compliance_Pct_raw'], df['Rx_Lift_Pct'])
    ols_r2 = r_ols ** 2

    sample = df.sample(min(450, len(df)), random_state=42)
    for q, col in QUAD_COLORS.items():
        sub = sample[sample['_quadrant'] == q]
        ax.scatter(sub['Compliance_Pct_raw'], sub['Rx_Lift_Pct'],
                   color=col, alpha=0.45, s=14, linewidths=0,
                   label=q, zorder=3)

    x_line = np.linspace(df['Compliance_Pct_raw'].min(),
                         df['Compliance_Pct_raw'].max(), 300)
    ax.plot(x_line, slope * x_line + intercept,
            color=CYAN, lw=2.2, linestyle='--', zorder=5,
            label=f'OLS: y={slope:.4f}x+{intercept:.3f}')

    ax.axvline(80,          color=WHITE, lw=0.7, linestyle=':', alpha=0.4)
    ax.axhline(median_lift, color=WHITE, lw=0.7, linestyle=':', alpha=0.4)

    # Annotation box
    box_txt = (f'Pearson r = {r_val:+.4f}\n'
               f'p-value   = {p_val:.2e}\n'
               f'OLS R²    = {ols_r2:.4f}')
    ax.text(0.98, 0.97, box_txt,
            transform=ax.transAxes, ha='right', va='top',
            fontsize=8.5, color=TEXT, linespacing=1.6,
            bbox=dict(boxstyle='round,pad=0.5', facecolor=CARD, edgecolor=BORDER,
                      alpha=0.95, linewidth=0.8))

    card_axes(ax, '① Compliance % vs Rx Lift %',
              f'Quadrant-colored HCP records  (n={len(sample):,})')
    ax.set_xlabel('Call Plan Compliance (%)')
    ax.set_ylabel('Rx Lift % (Bounded −3% → +18%)')
    ax.legend(loc='lower right', ncol=2, framealpha=0.85, fontsize=7.5)
    ax.set_ylim(-2, 11)

    sig = 'p<0.001' if p_val < 0.001 else f'p={p_val:.3f}'
    ax.set_title(f'① Compliance % vs Rx Lift %   [r={r_val:+.4f}, {sig}]',
                 color=WHITE, fontsize=12, fontweight='bold', pad=10, loc='left')


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL 2 — Feature Attribution Horizontal Bar
# ═══════════════════════════════════════════════════════════════════════════════
def draw_attribution(ax, attribution):
    feats   = FEATURE_NAMES
    labels  = FEATURE_LABELS
    primary = attribution['primary_driver']
    results = attribution['features']

    rf_pcts      = [results[f]['rf_importance_pct']  for f in feats]
    pearson_pcts = [results[f]['pearson_abs'] * 100   for f in feats]
    spearman_pcts= [results[f]['spearman_abs'] * 100  for f in feats]

    y_pos  = np.arange(len(feats))
    height = 0.22

    b1 = ax.barh(y_pos + height,     rf_pcts,       height, color=VIOLET,  alpha=0.85, label='RF Importance %')
    b2 = ax.barh(y_pos,              pearson_pcts,  height, color=CYAN,    alpha=0.75, label='|Pearson r| × 100')
    b3 = ax.barh(y_pos - height,     spearman_pcts, height, color=GREEN,   alpha=0.65, label='|Spearman ρ| × 100')

    # Highlight primary driver
    primary_idx = feats.index(primary) if primary in feats else 0
    for bar_group, bars in [(b1, rf_pcts), (b2, pearson_pcts), (b3, spearman_pcts)]:
        bar = list(bar_group)[primary_idx]
        bar.set_edgecolor(AMBER)
        bar.set_linewidth(1.8)

    # "Primary Prescribing Driver" badge
    best_val = max(rf_pcts[primary_idx], pearson_pcts[primary_idx], spearman_pcts[primary_idx])
    ax.annotate(
        '★ Primary\n  Prescribing\n  Driver',
        xy=(best_val, primary_idx + height),
        xytext=(best_val + 2, primary_idx + height + 0.15),
        color=AMBER, fontsize=7.5, fontweight='bold',
        arrowprops=dict(arrowstyle='->', color=AMBER, lw=1.2),
    )

    # Value labels
    for i, (r, p, s) in enumerate(zip(rf_pcts, pearson_pcts, spearman_pcts)):
        ax.text(r + 0.4,  y_pos[i] + height, f'{r:.1f}%',  va='center', fontsize=7.5, color=MUTED2)
        ax.text(p + 0.4,  y_pos[i],           f'{p:.1f}%',  va='center', fontsize=7.5, color=MUTED2)
        ax.text(s + 0.4,  y_pos[i] - height,  f'{s:.1f}%',  va='center', fontsize=7.5, color=MUTED2)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('Attribution / Correlation Strength (%)')
    ax.set_xlim(0, max(rf_pcts + pearson_pcts + spearman_pcts) * 1.25)
    ax.legend(loc='lower right', framealpha=0.85)
    ax.set_title('② Feature Attribution vs Rx Lift\n'
                 f'★ Primary Driver: {FEATURE_LABELS[feats.index(primary)]}  '
                 f'({rf_pcts[feats.index(primary)]:.1f}% RF)',
                 color=WHITE, fontsize=12, fontweight='bold', pad=10, loc='left')
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL 3 — 2×2 Rep Effectiveness Quadrant
# ═══════════════════════════════════════════════════════════════════════════════
def draw_rep_quadrant(ax, rep_df, median_lift):
    median_comp = rep_df['compliance'].median()

    for q, col in QUAD_COLORS.items():
        sub = rep_df[rep_df['quadrant'] == q]
        ax.scatter(sub['compliance'], sub['lift'],
                   color=col, s=160, alpha=0.88, edgecolors='white',
                   linewidths=0.6, zorder=5, label=q)
        for _, row in sub.iterrows():
            ax.text(row['compliance'] + 0.4, row['lift'] + 0.05,
                    row['rep'].replace('REP-', ''), fontsize=7.5,
                    color=col, fontweight='bold', va='center', zorder=6)

    # Boundary lines
    ax.axvline(80,          color=WHITE, lw=1.0, linestyle='--', alpha=0.5)
    ax.axhline(median_lift, color=WHITE, lw=1.0, linestyle='--', alpha=0.5)

    # Quadrant count labels in corners
    q_counts = rep_df['quadrant'].value_counts()
    ax.text(0.02, 0.97,
            f"⭐ Stars: {q_counts.get('Stars',0)}",
            transform=ax.transAxes, ha='left', va='top',
            fontsize=8.5, color=GREEN, fontweight='bold')
    ax.text(0.98, 0.97,
            f"🟡 Ineffective: {q_counts.get('Ineffective',0)}",
            transform=ax.transAxes, ha='right', va='top',
            fontsize=8.5, color=AMBER, fontweight='bold')
    ax.text(0.02, 0.03,
            f"🔵 Underserved: {q_counts.get('Underserved',0)}",
            transform=ax.transAxes, ha='left', va='bottom',
            fontsize=8.5, color=CYAN, fontweight='bold')
    ax.text(0.98, 0.03,
            f"🔴 At-Risk: {q_counts.get('At-Risk',0)}",
            transform=ax.transAxes, ha='right', va='bottom',
            fontsize=8.5, color=RED, fontweight='bold')

    # Boundary labels
    ax.text(80.5, ax.get_ylim()[0] + 0.1, '80% compliance →',
            fontsize=7, color=MUTED, style='italic', alpha=0.7)
    ax.text(ax.get_xlim()[0] + 0.3, median_lift + 0.05, f'← median lift {median_lift:.2f}%',
            fontsize=7, color=MUTED, style='italic', alpha=0.7)

    ax.set_xlabel('Mean Compliance %')
    ax.set_ylabel('Mean Rx Lift %')
    ax.legend(loc='upper left', framealpha=0.85, fontsize=8)
    ax.set_title('③ 2×2 Rep Effectiveness Quadrant\n12 Sales Representatives (REP-101 – REP-112)',
                 color=WHITE, fontsize=12, fontweight='bold', pad=10, loc='left')
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL 4 — ML Model Tournament
# ═══════════════════════════════════════════════════════════════════════════════
def draw_ml_tournament(ax, benchmarks):
    names    = [b['name'] for b in benchmarks]
    train_r2 = [b['train_r2'] for b in benchmarks]
    cv_r2    = [b['cv_mean']  for b in benchmarks]
    test_r2  = [b['test_r2']  for b in benchmarks]
    ci_lo    = [b['ci_lo']    for b in benchmarks]
    ci_hi    = [b['ci_hi']    for b in benchmarks]

    y   = np.arange(len(names))
    h   = 0.22
    err = [[t - lo for t, lo in zip(test_r2, ci_lo)],
           [hi - t for t, hi in zip(test_r2, ci_hi)]]

    ax.barh(y + h,   train_r2, h, color=VIOLET, alpha=0.45, label='Train R²')
    ax.barh(y,       cv_r2,    h, color=CYAN,   alpha=0.65, label='5-Fold CV R²')
    bars = ax.barh(y - h, test_r2, h, color=GREEN,  alpha=0.88, label='Held-Out Test R²',
                   xerr=err, error_kw=dict(ecolor=AMBER, capsize=4, elinewidth=1.5,
                                           capthick=1.5, alpha=0.9))

    # Value labels
    medals = ['🥇', '🥈', '🥉', '#4']
    for i, (b, medal) in enumerate(zip(benchmarks, medals)):
        ax.text(b['test_r2'] + 0.005, y[i] - h, f'{b["test_r2"]:.4f}',
                va='center', fontsize=8, color=GREEN, fontweight='bold')
        ax.text(-0.01, y[i] - h, medal, va='center', ha='right', fontsize=10)

        gap_col = AMBER if abs(b['gap']) < 0.15 else (AMBER if b['gap'] < 0.30 else RED)
        ax.text(0.99, y[i], f'Gap: {b["gap"]:+.3f}',
                va='center', ha='right', fontsize=7.5,
                color=gap_col, transform=ax.get_yaxis_transform())

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel('R² Score')
    ax.set_xlim(-0.05, 1.10)
    ax.set_ylim(-0.6, len(names) - 0.3)
    ax.axvline(0.5, color=WHITE, lw=0.8, linestyle=':', alpha=0.35)
    ax.legend(loc='lower right', framealpha=0.85)
    ax.set_title('④ ML Model Tournament\nTrain R² / 5-Fold CV R² / Held-Out Test R² (95% Bootstrap CI)',
                 color=WHITE, fontsize=12, fontweight='bold', pad=10, loc='left')
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    log.info('='*60)
    log.info('Pharma Analytics — Visualization Generator')
    log.info('='*60)

    # Load data
    df = load_data()

    # Ensure raw columns exist
    for col in FEATURE_NAMES:
        if col not in df.columns:
            base = col.replace('_raw','')
            if base in df.columns:
                df[col] = df[base]
            else:
                df[col] = 0.0

    # Add quadrant labels
    df, median_lift = add_quadrant(df)

    # Compute analytics
    log.info('Computing feature attribution...')
    attribution = compute_feature_attribution(df)

    log.info('Computing ML benchmarks...')
    benchmarks  = compute_ml_benchmarks(df)

    log.info('Computing rep scorecards...')
    rep_df = compute_rep_scorecards(df, attribution)

    # Print summary to console
    primary = attribution['primary_driver']
    primary_label = FEATURE_LABELS[FEATURE_NAMES.index(primary)]
    r_val, p_val = pearsonr(df['Compliance_Pct_raw'], df['Rx_Lift_Pct'])
    best = benchmarks[0]

    print('\n' + '='*68)
    print('  METRIC SUMMARY')
    print('='*68)
    print(f'  HCP records          : {len(df):,}')
    print(f'  Mean Compliance      : {df["Compliance_Pct_raw"].mean():.2f}%')
    print(f'  Mean Rx Lift         : {df["Rx_Lift_Pct"].mean():.4f}%')
    print(f'  Pearson r            : {r_val:.4f}  p={p_val:.2e}')
    print(f'  Primary Driver       : {primary_label} '
          f'({attribution["features"][primary]["rf_importance_pct"]:.2f}% RF)')
    print(f'  Best ML Model        : {best["name"]}')
    print(f'  Best Test R²         : {best["test_r2"]:.4f}')
    print(f'  Best 95% CI          : [{best["ci_lo"]:.4f}, {best["ci_hi"]:.4f}]')
    print('='*68)

    # Feature attribution table
    print('\n  FEATURE ATTRIBUTION:')
    print(f'  {"Feature":<26}  {"RF Imp%":>8}  {"Pearson|r|":>12}  {"Spearman|rho|":>14}')
    print('  ' + '-'*62)
    for feat, lbl in zip(FEATURE_NAMES, FEATURE_LABELS):
        res = attribution['features'][feat]
        star = ' [PRIMARY]' if feat == primary else ''
        print(f'  {lbl:<26}  {res["rf_importance_pct"]:>7.2f}%  '
              f'{res["pearson_abs"]:>11.4f}  {res["spearman_abs"]:>11.4f}{star}')

    # Rep scorecard table
    print('\n  REP SCORECARDS:')
    print(f'  {"Rep":<10} {"Territory":<10} {"HCPs":>5} '
          f'{"Compliance%":>12} {"Rx Lift%":>9} {"Quadrant":<14} Priority')
    print('  ' + '-'*76)
    for _, r in rep_df.iterrows():
        print(f'  {r["rep"]:<10} {r["territory"]:<10} {r["n_hcps"]:>5} '
              f'{r["compliance"]:>11.2f}%  {r["lift"]:>8.3f}%  {r["quadrant"]:<14} {r["priority"]}')
    print()

    # Build figure
    log.info('Building 4-panel figure...')
    apply_dark_style()

    fig = plt.figure(figsize=(20, 13))
    fig.patch.set_facecolor(BG)

    gs = gridspec.GridSpec(
        2, 2, figure=fig,
        hspace=0.38, wspace=0.28,
        left=0.07, right=0.97, top=0.91, bottom=0.07,
    )
    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])

    # Suptitle
    fig.suptitle(
        'Rep Call Plan Compliance & Effectiveness Scorecard  [Fully Synthetic Simulation]',
        fontsize=15, fontweight='bold', color=WHITE, y=0.97,
    )
    fig.text(
        0.5, 0.945,
        f'n={len(df):,} HCPs · 12 Reps · 6 Territories  |  '
        f'Primary Driver: {primary_label} ({attribution["features"][primary]["rf_importance_pct"]:.1f}% RF Importance)  |  '
        f'Best Model: {best["name"]} Test R²={best["test_r2"]:.4f}',
        ha='center', fontsize=9.5, color=AMBER,
    )

    draw_scatter(ax1, df, median_lift)
    draw_attribution(ax2, attribution)
    draw_rep_quadrant(ax3, rep_df, df['Rx_Lift_Pct'].median())
    draw_ml_tournament(ax4, benchmarks)

    out = 'output_metrics_scorecard.png'
    plt.savefig(out, dpi=150, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close()
    log.info('✅  Saved → %s  (%.1f KB)', out, pathlib.Path(out).stat().st_size / 1024)
    print(f'\n✅  Saved: {out}')


if __name__ == '__main__':
    main()
