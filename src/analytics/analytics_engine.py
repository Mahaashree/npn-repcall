#!/usr/bin/env python3
"""
analytics_engine.py
===================
Compute KPIs, 2x2 performance matrix segmentation, manager call-plan
re-allocation, and 12 rep scorecards from processed_data.parquet.

Input:  processed_data.parquet
Output: analytics_results.json
"""

from __future__ import annotations
import json
import logging
import pathlib
import time

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import pearsonr

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
INPUT_PATH = BASE_DIR / 'processed_data.parquet'
OUTPUT_PATH = BASE_DIR / 'analytics_results.json'

QUADRANT_ACTIONS = {
    'Stars':       'Maintain & Reward \u2022 Model for Best Practices',
    'Ineffective': 'Clinical Detail Coaching \u2022 Focus on Messaging Quality',
    'Underserved': 'Expand Target Capacity \u2022 Increase Visit Frequency',
    'At-Risk':     'Performance Management \u2022 Call Plan Realignment',
}


def safe(v):
    """Convert numpy scalars to native Python types for JSON serialisation."""
    if isinstance(v, (np.integer,)):   return int(v)
    if isinstance(v, (np.floating,)):  return float(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)): return None
    return v


def classify_quadrant(compliance_pct: float, rx_lift: float, median_lift: float) -> str:
    high_comp = compliance_pct >= 80.0
    high_lift = rx_lift >= median_lift
    if high_comp and high_lift:     return 'Stars'
    if high_comp and not high_lift: return 'Ineffective'
    if not high_comp and high_lift: return 'Underserved'
    return 'At-Risk'


def compute_kpis(df: pd.DataFrame) -> dict:
    log.info('[KPIs] Computing executive KPIs...')
    comp     = df['Compliance_Pct_raw'].values
    lift     = df['Rx_Lift_Pct'].values
    mean_comp = float(np.mean(comp))
    mean_lift = float(np.mean(lift))
    # Overall Rx Volume Growth % (mean post vs mean baseline)
    baseline_total   = float(df['Tot_30day_Fills_raw'].sum())
    postcampaign_total = float(df['Post_Campaign_Fills'].sum())
    overall_rx_growth_pct = ((postcampaign_total - baseline_total) / max(1, baseline_total)) * 100.0
    total_lift_volume = float(postcampaign_total - baseline_total)
    # Pearson r
    r, p = pearsonr(comp, lift)
    # OLS regression: Rx_Lift_Pct ~ Compliance_Pct
    from scipy.stats import linregress
    slope, intercept, r_value, p_val_ols, se = linregress(comp, lift)
    kpis = {
        'n_hcps': int(len(df)),
        'n_reps': int(df['Sales_Rep'].nunique()),
        'n_territories': int(df['Territory'].nunique()),
        'mean_compliance_rate_pct': round(mean_comp, 4),
        'mean_rx_lift_pct': round(mean_lift, 4),
        'overall_rx_volume_growth_pct': round(overall_rx_growth_pct, 4),
        'total_lift_volume': round(total_lift_volume, 2),
        'pearson_correlation': {
            'r': round(float(r), 6),
            'p_value': round(float(p), 6),
            'interpretation': 'statistically significant (p<0.05)' if p < 0.05 else 'not statistically significant',
        },
        'ols_regression': {
            'slope': round(float(slope), 6),
            'intercept': round(float(intercept), 6),
            'r_squared': round(float(r_value ** 2), 6),
            'equation': f'Rx_Lift_Pct = {slope:.4f} * Compliance_Pct + {intercept:.4f}',
        },
    }
    log.info('  mean_compliance=%.2f%%  mean_lift=%.4f%%  pearson_r=%.4f  p=%.4f',
             mean_comp, mean_lift, r, p)
    return kpis


def compute_performance_matrix(df: pd.DataFrame) -> dict:
    log.info('[Matrix] Computing 2x2 performance matrix...')
    median_lift = float(df['Rx_Lift_Pct'].median())
    df = df.copy()
    df['_quadrant'] = df.apply(
        lambda row: classify_quadrant(
            row['Compliance_Pct_raw'], row['Rx_Lift_Pct'], median_lift), axis=1)
    summary = []
    order = ['Stars', 'Ineffective', 'Underserved', 'At-Risk']
    for q in order:
        sub = df[df['_quadrant'] == q]
        n   = len(sub)
        summary.append({
            'quadrant':          q,
            'compliance_band':   '>=80' if q in ('Stars', 'Ineffective') else '<80',
            'lift_band':         'High' if q in ('Stars', 'Underserved') else 'Low',
            'action':            QUADRANT_ACTIONS[q],
            'record_count':      int(n),
            'pct_of_total':      round(n / max(1, len(df)) * 100, 2),
            'mean_compliance_pct': round(float(sub['Compliance_Pct_raw'].mean()), 4) if n > 0 else 0.0,
            'mean_rx_lift_pct':  round(float(sub['Rx_Lift_Pct'].mean()), 4) if n > 0 else 0.0,
            'total_lift_volume': round(float((sub['Post_Campaign_Fills'] - sub['Tot_30day_Fills_raw']).sum()), 2) if n > 0 else 0.0,
            'prescriber_count':  int(sub['Prscrbr_NPI'].nunique()) if n > 0 else 0,
        })
        log.info('  %-12s  n=%d (%.1f%%)  mean_lift=%.3f%%', q, n, n/max(1,len(df))*100,
                 sub['Rx_Lift_Pct'].mean() if n > 0 else 0)
    return {'median_lift_threshold': round(median_lift, 4), 'quadrant_summary': summary, '_df': df}


def compute_rep_scorecards(df: pd.DataFrame) -> list[dict]:
    log.info('[Scorecards] Building 12 rep scorecards...')
    scorecards = []
    for rep in sorted(df['Sales_Rep'].unique()):
        sub = df[df['Sales_Rep'] == rep]
        territory  = sub['Territory'].mode()[0]
        prim_spec  = sub['Specialty'].mode()[0]
        n_hcp      = int(len(sub))
        total_target = int(sub['Target_Calls'].sum())
        total_actual = int(sub['Actual_Calls'].sum())
        call_attainment = round(total_actual / max(1, total_target) * 100, 2)
        mean_comp    = round(float(sub['Compliance_Pct_raw'].mean()), 4)
        mean_lift    = round(float(sub['Rx_Lift_Pct'].mean()), 4)
        total_samples= int(sub['Samples_Dropped'].sum())
        # Quadrant counts (if _quadrant column present)
        qcounts = {
            'Stars':       int((sub['_quadrant'] == 'Stars').sum()),
            'Ineffective': int((sub['_quadrant'] == 'Ineffective').sum()),
            'Underserved': int((sub['_quadrant'] == 'Underserved').sum()),
            'At-Risk':     int((sub['_quadrant'] == 'At-Risk').sum()),
        }
        dom_q = max(qcounts, key=lambda k: qcounts[k])
        # Coaching priority
        at_risk_share = qcounts['At-Risk'] / max(1, n_hcp)
        if at_risk_share > 0.40:
            priority = 'Urgent Coaching'
        elif mean_comp < 70 or mean_lift < 3.0:
            priority = 'Monitor'
        else:
            priority = 'On Track'
        # Net recommended call delta
        net_delta = round(float(sub['Target_Calls'].mean() * (1 + (mean_lift - df['Rx_Lift_Pct'].mean()) / 100)) - sub['Target_Calls'].mean(), 2)
        scorecards.append({
            'sales_rep':                   rep,
            'territory':                   territory,
            'territory_primary_specialty': prim_spec,
            'prescriber_count':            n_hcp,
            'total_target_calls':          total_target,
            'total_actual_calls':          total_actual,
            'call_attainment_pct':         call_attainment,
            'mean_compliance_pct':         mean_comp,
            'mean_rx_lift_pct':            mean_lift,
            'total_samples_dropped':       total_samples,
            'quadrant_counts':             qcounts,
            'dominant_quadrant':           dom_q,
            'coaching_priority':           priority,
            'net_recommended_call_delta':  net_delta,
        })
        log.info('  %-10s  territory=%-8s  hcps=%d  compliance=%.1f%%  lift=%.3f%%  priority=%s',
                 rep, territory, n_hcp, mean_comp, mean_lift, priority)
    return scorecards


def compute_call_reallocation(df: pd.DataFrame) -> dict:
    log.info('[Reallocation] Computing territory call re-allocation...')
    # Territory mean lift for each HCP
    terr_mean = df.groupby('Territory')['Rx_Lift_Pct'].mean().to_dict()
    df2 = df.copy()
    df2['territory_mean_lift'] = df2['Territory'].map(terr_mean)
    df2['reallocated_target'] = df2.apply(
        lambda r: round(r['Target_Calls'] * (1 + (r['Rx_Lift_Pct'] - r['territory_mean_lift']) / 100), 2),
        axis=1,
    )
    df2['call_delta'] = (df2['reallocated_target'] - df2['Target_Calls']).round(2)
    # Territory-level summary
    terr_summary = []
    for terr in sorted(df2['Territory'].unique()):
        sub = df2[df2['Territory'] == terr]
        increasing = int((sub['call_delta'] > 0).sum())
        decreasing = int((sub['call_delta'] < 0).sum())
        terr_summary.append({
            'territory':               terr,
            'reps':                    sorted(sub['Sales_Rep'].unique().tolist()),
            'n_hcps':                  int(len(sub)),
            'calls_to_add':            round(float(sub[sub['call_delta'] > 0]['call_delta'].sum()), 2),
            'calls_to_reallocate':     round(float(sub[sub['call_delta'] < 0]['call_delta'].sum()), 2),
            'net_call_delta':          round(float(sub['call_delta'].sum()), 2),
            'hcps_with_increase':      increasing,
            'hcps_with_decrease':      decreasing,
        })
        log.info('  %-8s  hcps=%d  net_delta=%+.1f  inc=%d  dec=%d',
                 terr, len(sub), sub['call_delta'].sum(), increasing, decreasing)
    # Rep-level summary
    rep_summary = []
    for rep in sorted(df2['Sales_Rep'].unique()):
        sub = df2[df2['Sales_Rep'] == rep]
        add_calls = round(float(sub[sub['call_delta'] > 0]['call_delta'].sum()), 2)
        free_calls = abs(round(float(sub[sub['call_delta'] < 0]['call_delta'].sum()), 2))
        net_delta = round(float(sub['call_delta'].sum()), 2)
        inc_cnt = int((sub['call_delta'] > 0).sum())
        dec_cnt = int((sub['call_delta'] < 0).sum())

        if add_calls > free_calls + 0.5:
            rec = 'Expand high-lift prescriber visits'
        elif free_calls > add_calls + 0.5:
            rec = 'Reallocate to higher-lift HCPs'
        else:
            rec = 'Reallocate calls within territory (Balanced)'

        rep_summary.append({
            'sales_rep':               rep,
            'territory':               sub['Territory'].mode()[0],
            'calls_to_add':            add_calls,
            'calls_to_reallocate':     free_calls,
            'net_call_delta':          net_delta,
            'prescribers_with_increase': inc_cnt,
            'prescribers_with_decrease': dec_cnt,
            'recommendation':          rec,
        })
    # HCP detail (first 200 for JSON size control)
    hcp_detail = []
    for _, row in df2.iterrows():
        hcp_detail.append({
            'sales_rep':             row['Sales_Rep'],
            'prscrbr_npi':           row['Prscrbr_NPI'],
            'physician_name':        row['Physician_Name'],
            'territory':             row['Territory'],
            'target_calls':          int(row['Target_Calls']),
            'actual_calls':          int(row['Actual_Calls']),
            'compliance_pct':        round(float(row['Compliance_Pct_raw']), 2),
            'rx_lift_pct':           round(float(row['Rx_Lift_Pct']), 4),
            'territory_mean_lift':   round(float(row['territory_mean_lift']), 4),
            'reallocated_target':    round(float(row['reallocated_target']), 2),
            'call_delta':            round(float(row['call_delta']), 2),
        })
    return {
        'territory_reallocation_summary': terr_summary,
        'rep_reallocation_summary':       rep_summary,
        'hcp_reallocation_detail':        hcp_detail,
    }


def main() -> None:
    t0 = time.perf_counter()
    df = pd.read_parquet(INPUT_PATH)
    log.info('Loaded %d HCP records from %s.', len(df), INPUT_PATH)
    # Ensure _raw columns exist (generated by preprocessing)
    for col in ['Compliance_Pct', 'Tot_30day_Fills']:
        raw_col = f'{col}_raw'
        if raw_col not in df.columns and col in df.columns:
            df[raw_col] = df[col].copy()
    kpis    = compute_kpis(df)
    matrix  = compute_performance_matrix(df)
    df_quad = matrix.pop('_df')   # enriched df with _quadrant column
    scorecards = compute_rep_scorecards(df_quad)
    realloc    = compute_call_reallocation(df_quad)
    output = {
        'metadata': {
            'source_file':            str(INPUT_PATH),
            'total_hcp_records':      int(len(df)),
            'total_sales_reps':       int(df['Sales_Rep'].nunique()),
            'total_territories':      int(df['Territory'].nunique()),
            'execution_time_sec':     round(time.perf_counter() - t0, 6),
        },
        'kpis':               kpis,
        'performance_matrix': matrix,
        'rep_scorecards':     scorecards,
        'call_plan_reallocation': realloc,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=safe)
    log.info('Exported %s (%.1f KB).', OUTPUT_PATH, OUTPUT_PATH.stat().st_size / 1024)
    log.info('Analytics engine completed in %.4fs.', time.perf_counter() - t0)


if __name__ == '__main__':
    main()
