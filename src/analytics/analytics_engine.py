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
PROCESSED_DIR = BASE_DIR / 'data' / 'generated' / 'processed'
ANALYTICS_DIR = BASE_DIR / 'data' / 'generated' / 'analytics'
INPUT_PATH = PROCESSED_DIR / 'processed_data.parquet'
OUTPUT_PATH = ANALYTICS_DIR / 'analytics_results.json'

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


def calculate_rep_cei(sub: pd.DataFrame, driver_weights: Optional[dict] = None) -> float:
    if driver_weights is None:
        driver_weights = {'cadence': 0.676, 'samples': 0.249, 'tier': 0.056, 'compliance': 0.019}

    n_hcp = len(sub)
    if n_hcp == 0:
        return 0.0

    total_target = int(sub['Target_Calls'].sum())
    total_actual = int(sub['Actual_Calls'].sum())
    total_samples = int(sub['Samples_Dropped'].sum())

    # 1. Cadence Score (Actual Monthly Calls / Target Monthly Calls, capped at 1.0)
    actual_monthly = total_actual / 3.0
    target_monthly = total_target / 3.0
    cadence_score = min(1.0, actual_monthly / max(1.0, target_monthly))

    # 2. Sample Score (Sample Ratio vs Target Sample Ratio 1.0, capped at 1.0)
    sample_ratio = total_samples / max(1.0, total_actual)
    sample_score = min(1.0, sample_ratio / 1.0)

    # 3. HCP Tier Score (Assigned High Tier 1 & 2 HCPs / Total HCPs)
    high_tier_hcps = int(sub['HCP_Tier'].isin([1, 2]).sum()) if 'HCP_Tier' in sub.columns else n_hcp
    tier_score = min(1.0, high_tier_hcps / max(1, n_hcp))

    # 4. Compliance Score (Actual Calls / Target Calls, capped at 1.0)
    comp_score = min(1.0, total_actual / max(1.0, total_target))

    w_cad = driver_weights.get('cadence', 0.676)
    w_samp = driver_weights.get('samples', 0.249)
    w_tier = driver_weights.get('tier', 0.056)
    w_comp = driver_weights.get('compliance', 0.019)
    w_sum = w_cad + w_samp + w_tier + w_comp or 1.0

    cei_raw = (cadence_score * w_cad + sample_score * w_samp + tier_score * w_tier + comp_score * w_comp) / w_sum
    return round(float(cei_raw * 100.0), 1)


def calculate_hcp_cei(row: pd.Series, driver_weights: Optional[dict] = None) -> float:
    if driver_weights is None:
        driver_weights = {'cadence': 0.676, 'samples': 0.249, 'tier': 0.056, 'compliance': 0.019}

    target = max(1.0, float(row.get('Target_Calls', 10)))
    actual = float(row.get('Actual_Calls', 0))
    samples = float(row.get('Samples_Dropped', 0))
    tier = int(row.get('HCP_Tier', 3))

    cadence_score = min(1.0, (actual / 3.0) / max(1.0, target / 3.0))
    sample_score = min(1.0, (samples / max(1.0, actual)) / 1.0)
    tier_score = 1.0 if tier == 1 else (0.8 if tier == 2 else 0.5)
    comp_score = min(1.0, actual / target)

    w_cad = driver_weights.get('cadence', 0.676)
    w_samp = driver_weights.get('samples', 0.249)
    w_tier = driver_weights.get('tier', 0.056)
    w_comp = driver_weights.get('compliance', 0.019)
    w_sum = w_cad + w_samp + w_tier + w_comp or 1.0

    cei_raw = (cadence_score * w_cad + sample_score * w_samp + tier_score * w_tier + comp_score * w_comp) / w_sum
    return round(float(cei_raw * 100.0), 1)


def compute_performance_matrix(df: pd.DataFrame) -> dict:
    log.info('[Matrix] Computing dual-mode 2x2 performance matrix...')
    median_lift = float(df['Rx_Lift_Pct'].median())
    df = df.copy()

    # Calculate HCP-level CEI
    df['cei_score'] = df.apply(calculate_hcp_cei, axis=1)

    # 1. Legacy Matrix: 80% Compliance split
    df['_quadrant_legacy'] = df.apply(
        lambda row: classify_quadrant(
            row['Compliance_Pct_raw'], row['Rx_Lift_Pct'], median_lift), axis=1)
    
    # 2. CEI Matrix: 75% CEI split
    def _classify_cei(row):
        cei = float(row.get('cei_score', 0))
        lift = float(row.get('Rx_Lift_Pct', 0))
        if cei >= 75.0 and lift >= median_lift:
            return 'Star Performers'
        elif cei < 75.0 and lift >= median_lift:
            return 'Efficient High-Performers'
        elif cei >= 75.0 and lift < median_lift:
            return 'Targeting Risk'
        else:
            return 'Needs Intervention'

    df['_quadrant_cei'] = df.apply(_classify_cei, axis=1)
    df['_quadrant'] = df['_quadrant_legacy']

    summary_legacy = []
    for q in ['Stars', 'Ineffective', 'Underserved', 'At-Risk']:
        sub = df[df['_quadrant_legacy'] == q]
        n   = len(sub)
        summary_legacy.append({
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

    summary_cei = []
    cei_actions = {
        'Star Performers': 'Maintain & Scale • Best Practices',
        'Efficient High-Performers': 'Scale Monthly Detailing Capacity',
        'Targeting Risk': 'Reallocate Calls to Top-Tier HCPs',
        'Needs Intervention': 'Driver Deficit Coaching • Call & Sample Boost',
    }
    for q in ['Star Performers', 'Efficient High-Performers', 'Targeting Risk', 'Needs Intervention']:
        sub = df[df['_quadrant_cei'] == q]
        n   = len(sub)
        summary_cei.append({
            'quadrant':          q,
            'cei_band':          '>=75%' if q in ('Star Performers', 'Targeting Risk') else '<75%',
            'lift_band':         'High' if q in ('Star Performers', 'Efficient High-Performers') else 'Low',
            'action':            cei_actions[q],
            'record_count':      int(n),
            'pct_of_total':      round(n / max(1, len(df)) * 100, 2),
            'mean_cei_score':    round(float(sub['cei_score'].mean()), 2) if n > 0 else 0.0,
            'mean_rx_lift_pct':  round(float(sub['Rx_Lift_Pct'].mean()), 4) if n > 0 else 0.0,
            'total_lift_volume': round(float((sub['Post_Campaign_Fills'] - sub['Tot_30day_Fills_raw']).sum()), 2) if n > 0 else 0.0,
            'prescriber_count':  int(sub['Prscrbr_NPI'].nunique()) if n > 0 else 0,
        })

    return {
        'median_lift_threshold': round(median_lift, 4),
        'quadrant_summary': summary_legacy,
        'quadrant_summary_legacy': summary_legacy,
        'quadrant_summary_cei': summary_cei,
        '_df': df
    }


def compute_rep_scorecards(df: pd.DataFrame) -> list[dict]:
    log.info('[Scorecards] Building rep scorecards for %d reps...', df['Sales_Rep'].nunique())
    
    # 75th percentile of territory baseline fills per HCP for Driver 3 statistical target
    fills_col = 'Tot_30day_Fills_raw' if 'Tot_30day_Fills_raw' in df.columns else 'Tot_30day_Fills'
    terr_75th_fills_per_hcp = df.groupby('Territory')[fills_col].quantile(0.75).round(2).to_dict()

    scorecards = []
    for rep in sorted(df['Sales_Rep'].unique()):
        sub = df[df['Sales_Rep'] == rep]
        territory  = sub['Territory'].mode()[0]
        prim_spec  = sub['Specialty'].mode()[0]
        n_hcp      = int(len(sub))
        total_target = int(sub['Target_Calls'].sum())
        total_actual = int(sub['Actual_Calls'].sum())
        call_attainment = round(total_actual / max(1, total_target) * 100, 2)
        mean_comp    = round(float(sub['Compliance_Pct_raw'].mean()), 4) if 'Compliance_Pct_raw' in sub.columns else round(call_attainment, 4)
        mean_lift    = round(float(sub['Rx_Lift_Pct'].mean()), 4)
        total_samples= int(sub['Samples_Dropped'].sum())
        
        # Quadrant counts
        qcounts = {
            'Stars':       int((sub['_quadrant'] == 'Stars').sum()),
            'Ineffective': int((sub['_quadrant'] == 'Ineffective').sum()),
            'Underserved': int((sub['_quadrant'] == 'Underserved').sum()),
            'At-Risk':     int((sub['_quadrant'] == 'At-Risk').sum()),
        }
        dom_q = max(qcounts, key=lambda k: qcounts[k])

        # 4 Key Program Driver Whole Integer Actuals & Targets:
        # Driver 1: Monthly Call Frequency (67.6% Weight) - Whole Monthly Calls
        cadence = int(round(total_actual / 3.0))
        target_cadence = int(round(total_target / 3.0))

        # Driver 2: Sample Drop Volume (24.9% Weight) - Whole Samples Dropped vs Visits
        sample_ratio = round(float(total_samples / max(1, total_actual)), 2)
        target_sample_ratio = 1.00

        # Driver 3: Baseline Prescribing Volume (3.8% Weight) - Sum of Baseline Fills for Assigned HCPs vs Territory Benchmark
        baseline_volume = int(round(sub[fills_col].sum()))
        p75_hcp = float(terr_75th_fills_per_hcp.get(territory, 20.0))
        target_baseline = int(round(n_hcp * p75_hcp))

        # Driver 4: Target Call Compliance (1.9% Weight) - Clean Whole Percentage
        compliance_pct = int(round(total_actual / max(1, total_target) * 100.0))
        target_compliance = 80

        sales_rep_name = str(sub['Sales_Rep_Name'].iloc[0]) if 'Sales_Rep_Name' in sub.columns else str(rep)
        
        # Dynamic Multi-Driver Coaching Decision Matrix:
        if mean_lift >= 4.5 and cadence >= target_cadence:
            dom_q = 'Stars'
            priority = 'On Track'
            action_flag = '🟢 Maintain & Scale'
            rec_text = f'Top Performer: Exceeding targets ({cadence}/{target_cadence} monthly calls, {total_samples}/{total_actual} samples dropped, +{mean_lift:.2f}% Rx Lift). Share detailing best practices across territory.'
            bottleneck = f'Top Performer (+{mean_lift:.2f}% Rx Lift, {cadence}/{target_cadence} calls/mo)'
            trajectory = 'improving'
        elif mean_lift >= 4.5 and cadence < target_cadence:
            dom_q = 'Stars'
            priority = 'Monitor'
            action_flag = '🟡 Efficiency Optimization'
            rec_text = f'High Return, Low Volume: High prescriber responsiveness. {sales_rep_name} completed {cadence} of {target_cadence} target monthly calls and dropped {total_samples} samples across {total_actual} visits. Increase visit volume to {target_cadence} calls/mo and ensure 1 sample per visit to maximize total adoption.'
            bottleneck = f'High Return, Low Volume ({cadence}/{target_cadence} calls/mo, {total_samples}/{total_actual} samples)'
            trajectory = 'improving'
        elif 2.5 <= mean_lift < 4.5:
            dom_q = 'Underserved'
            priority = 'Monitor'
            action_flag = '🟡 Targeting Refinement'
            rec_text = f'Moderate Lift: On track with {cadence}/{target_cadence} monthly calls. Refine call planning and sample distribution ({total_samples}/{total_actual} samples) toward top-tier physicians.'
            bottleneck = f'Targeting Refinement (+{mean_lift:.2f}% Lift, {cadence}/{target_cadence} calls/mo)'
            trajectory = 'stable'
        elif mean_lift < 2.5 and (cadence < target_cadence or total_samples < total_actual):
            dom_q = 'At-Risk'
            priority = 'Urgent Coaching'
            action_flag = '🔴 Urgent Coaching'
            rec_text = f'Driver Deficit: Falling short of call target ({cadence} vs {target_cadence} monthly calls) and sample target ({total_samples} vs {total_actual} samples dropped across visits). Prioritize doctor visit cadence.'
            bottleneck = f'Call Deficit ({cadence} vs {target_cadence} calls/mo)' if cadence < target_cadence else f'Sample Deficit ({total_samples} vs {total_actual} samples)'
            trajectory = 'declining'
        else:
            dom_q = 'Ineffective'
            priority = 'Monitor'
            action_flag = '🟡 Performance Review'
            rec_text = f'Review Detailing Quality: Completed {cadence}/{target_cadence} monthly calls and {total_samples}/{total_actual} samples dropped. Optimize detailing message and targeting.'
            bottleneck = f'Detailing Quality Review (+{mean_lift:.2f}% Rx Lift)'
            trajectory = 'declining'

        # Calculate Rep CEI
        cei_score = calculate_rep_cei(sub)
        if cei_score >= 75.0 and mean_lift >= float(df['Rx_Lift_Pct'].median()):
            dom_q_cei = 'Star Performers'
        elif cei_score < 75.0 and mean_lift >= float(df['Rx_Lift_Pct'].median()):
            dom_q_cei = 'Efficient High-Performers'
        elif cei_score >= 75.0 and mean_lift < float(df['Rx_Lift_Pct'].median()):
            dom_q_cei = 'Targeting Risk'
        else:
            dom_q_cei = 'Needs Intervention'

        # Net recommended call delta
        net_delta = round(float(sub['Target_Calls'].mean() * (1 + (mean_lift - df['Rx_Lift_Pct'].mean()) / 100)) - sub['Target_Calls'].mean(), 2)
        scorecards.append({
            'sales_rep':                   rep,
            'sales_rep_name':              sales_rep_name,
            'territory':                   territory,
            'territory_primary_specialty': prim_spec,
            'prescriber_count':            n_hcp,
            'total_target_calls':          total_target,
            'total_actual_calls':          total_actual,
            'call_attainment_pct':         call_attainment,
            'monthly_cadence':             cadence,
            'target_monthly_cadence':      target_cadence,
            'sample_ratio':                sample_ratio,
            'target_sample_ratio':         target_sample_ratio,
            'baseline_volume':             baseline_volume,
            'target_baseline_volume':      target_baseline,
            'compliance_pct':              compliance_pct,
            'target_compliance_pct':       target_compliance,
            'cei_score':                   cei_score,
            'mean_compliance_pct':         mean_comp,
            'mean_rx_lift_pct':            mean_lift,
            'total_samples_dropped':       total_samples,
            'quadrant_counts':             qcounts,
            'dominant_quadrant':           dom_q,
            'dominant_quadrant_cei':       dom_q_cei,
            'coaching_priority':           priority,
            'action_flag':                 action_flag,
            'driver_recommendation':       rec_text,
            'driver_bottleneck':           bottleneck,
            'trajectory_direction':        trajectory,
            'sample_size_flag':            n_hcp >= 30,
            'net_recommended_call_delta':  net_delta,
        })
        log.info('  %-10s  territory=%-8s  hcps=%d  cadence=%d/%d  samples=%d/%d  fills=%d/%d  lift=%.3f%%  flag=%s',
                 rep, territory, n_hcp, cadence, target_cadence, total_samples, total_actual, baseline_volume, target_baseline, mean_lift, action_flag)
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


def analyze_dataset(df_path: pathlib.Path) -> dict:
    df = pd.read_parquet(df_path)
    for col in ['Compliance_Pct', 'Tot_30day_Fills']:
        raw_col = f'{col}_raw'
        if raw_col not in df.columns and col in df.columns:
            df[raw_col] = df[col].copy()
    kpis    = compute_kpis(df)
    matrix  = compute_performance_matrix(df)
    df_quad = matrix.pop('_df')
    scorecards = compute_rep_scorecards(df_quad)
    realloc    = compute_call_reallocation(df_quad)
    return {
        'kpis': kpis,
        'performance_matrix': matrix,
        'rep_scorecards': scorecards,
        'call_plan_reallocation': realloc,
        'total_hcp_records': int(len(df)),
        'total_sales_reps': int(df['Sales_Rep'].nunique()),
        'total_territories': int(df['Territory'].nunique()),
    }


def main() -> None:
    t0 = time.perf_counter()
    pq_hybrid = PROCESSED_DIR / 'processed_data_hybrid.parquet'
    pq_synth  = PROCESSED_DIR / 'processed_data_synthetic.parquet'

    if not pq_hybrid.exists():
        pq_hybrid = INPUT_PATH
    if not pq_synth.exists():
        pq_synth = INPUT_PATH

    log.info('Running analytics engine on hybrid: %s', pq_hybrid)
    hybrid_res = analyze_dataset(pq_hybrid)

    log.info('Running analytics engine on synthetic: %s', pq_synth)
    synth_res  = analyze_dataset(pq_synth)

    output = {
        'metadata': {
            'execution_time_sec': round(time.perf_counter() - t0, 6),
        },
        'hybrid': hybrid_res,
        'synthetic': synth_res,
        'kpis': hybrid_res['kpis'],
        'performance_matrix': hybrid_res['performance_matrix'],
        'rep_scorecards': hybrid_res['rep_scorecards'],
        'call_plan_reallocation': hybrid_res['call_plan_reallocation'],
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=safe)
    log.info('Exported %s (%.1f KB).', OUTPUT_PATH, OUTPUT_PATH.stat().st_size / 1024)
    log.info('Analytics engine completed in %.4fs.', time.perf_counter() - t0)


if __name__ == '__main__':
    main()

