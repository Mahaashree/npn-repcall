from __future__ import annotations
import json
import logging
import pathlib
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('dynamic_ingestion')

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent

# Domain definitions
SPECIALTIES: list[str] = [
    'Pain Management', 'Oncology', 'Palliative Care', 'Neurology',
    'Anesthesiology', 'Internal Medicine', 'Family Practice',
    'Orthopedics', 'Emergency Medicine', 'Psychiatry',
]
SPEC_PROBS: list[float] = [0.26, 0.18, 0.14, 0.10, 0.10, 0.09, 0.06, 0.04, 0.02, 0.01]

BRAND_NAMES: list[str] = ['Subsys', 'Abstral', 'Actiq', 'Fentora', 'Lazanda']
BRAND_PROBS: list[float] = [0.35, 0.25, 0.18, 0.14, 0.08]

LOCATIONS: list[tuple[str, str]] = [
    ('Los Angeles', 'CA'), ('Houston', 'TX'), ('Miami', 'FL'),
    ('New York', 'NY'), ('Chicago', 'IL'), ('Philadelphia', 'PA'),
    ('Columbus', 'OH'), ('Detroit', 'MI'), ('Atlanta', 'GA'),
    ('Charlotte', 'NC'), ('Phoenix', 'AZ'), ('Seattle', 'WA'),
    ('Denver', 'CO'), ('Boston', 'MA'), ('Las Vegas', 'NV'),
    ('Portland', 'OR'), ('Nashville', 'TN'), ('Baltimore', 'MD'),
    ('Austin', 'TX'), ('Jacksonville', 'FL'),
]

REPS: list[str] = [f'REP-{i:03d}' for i in range(101, 113)]
TERRITORIES: list[str] = [f'TERR-{i:02d}' for i in range(1, 7)]
REP_TO_TERR: dict[str, str] = {REPS[i]: TERRITORIES[i // 2] for i in range(12)}

SPEC_CAPACITY: dict[str, float] = {
    'Pain Management': 1.40, 'Oncology': 1.30, 'Palliative Care': 1.25,
    'Neurology': 1.10, 'Anesthesiology': 1.20,
    'Internal Medicine': 0.90, 'Family Practice': 0.80,
    'Orthopedics': 0.95, 'Emergency Medicine': 0.70, 'Psychiatry': 0.80,
}

_FIRST = [
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
    'Thomas', 'Charles', 'Mary', 'Patricia', 'Jennifer', 'Linda', 'Barbara', 'Elizabeth',
    'Susan', 'Jessica', 'Sarah', 'Karen', 'Lisa', 'Nancy', 'Betty', 'Margaret',
]
_LAST = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
    'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
]

REQUIRED_DOMAINS = [
    'Prscrbr_NPI', 'Physician_Name', 'Specialty', 'City', 'State', 'Brand_Name',
    'Sales_Rep', 'Territory', 'HCP_Tier', 'Target_Calls', 'Actual_Calls',
    'Samples_Dropped', 'Tot_Clms', 'Tot_30day_Fills', 'Tot_Drug_Cst',
    'Rx_Lift_Pct', 'Post_Campaign_Fills'
]


class IngestionReport:
    def __init__(self, initial_columns: List[str], missing_columns: List[str], row_count: int):
        self.initial_columns = initial_columns
        self.missing_columns = missing_columns
        self.row_count = row_count
        self.synthesized_columns = list(missing_columns)
        self.derived_features: List[str] = []
        self.execution_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'row_count': self.row_count,
            'initial_columns': self.initial_columns,
            'missing_columns': self.missing_columns,
            'synthesized_columns': self.synthesized_columns,
            'derived_features': self.derived_features,
            'execution_time_sec': round(self.execution_time_sec, 4),
        }


def inspect_schema(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Inspect columns and identify missing required domains."""
    existing_cols = list(df.columns)
    lower_map = {c.lower(): c for c in existing_cols}
    missing: List[str] = []
    
    for req in REQUIRED_DOMAINS:
        if req not in existing_cols and req.lower() not in lower_map:
            missing.append(req)
            
    return existing_cols, missing


def auto_synthesize(df: pd.DataFrame, missing_cols: List[str], seed: int = 42) -> pd.DataFrame:
    """
    Synthesize missing required columns using domain distributions:
    - Gamma for baseline fills
    - Poisson for samples dropped
    - Uniform / Normal for calls and targets
    - Beta for compliance factors and quality
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    df = df.copy()

    lower_map = {c.lower(): c for c in df.columns}
    for req in REQUIRED_DOMAINS:
        if req not in df.columns and req.lower() in lower_map:
            df.rename(columns={lower_map[req.lower()]: req}, inplace=True)

    # 1. Identity & Profile
    if 'Prscrbr_NPI' in missing_cols or 'Prscrbr_NPI' not in df.columns:
        df['Prscrbr_NPI'] = [str(1_001_000_001 + i) for i in range(n)]

    if 'Physician_Name' in missing_cols or 'Physician_Name' not in df.columns:
        df['Physician_Name'] = [
            f"Dr. {rng.choice(_FIRST)} {rng.choice(_LAST)}" for _ in range(n)
        ]

    if 'Specialty' in missing_cols or 'Specialty' not in df.columns:
        df['Specialty'] = rng.choice(SPECIALTIES, size=n, p=SPEC_PROBS)

    if 'City' in missing_cols or 'State' in missing_cols:
        locs = [LOCATIONS[int(i)] for i in rng.integers(0, len(LOCATIONS), size=n)]
        if 'City' not in df.columns:
            df['City'] = [l[0] for l in locs]
        if 'State' not in df.columns:
            df['State'] = [l[1] for l in locs]

    if 'Brand_Name' in missing_cols or 'Brand_Name' not in df.columns:
        df['Brand_Name'] = rng.choice(BRAND_NAMES, size=n, p=BRAND_PROBS)

    if 'Sales_Rep' in missing_cols or 'Sales_Rep' not in df.columns:
        rep_arr = np.tile(REPS, (n // len(REPS)) + 1)[:n]
        rng.shuffle(rep_arr)
        df['Sales_Rep'] = rep_arr

    if 'Territory' in missing_cols or 'Territory' not in df.columns:
        df['Territory'] = df['Sales_Rep'].map(lambda r: REP_TO_TERR.get(r, 'TERR-01'))

    # 2. Baseline Prescribing & Financials (Gamma & Negative Binomial)
    if 'Tot_Clms' in missing_cols or 'Tot_Clms' not in df.columns:
        df['Tot_Clms'] = rng.negative_binomial(n=15, p=0.45, size=n)

    if 'Tot_30day_Fills' in missing_cols or 'Tot_30day_Fills' not in df.columns:
        df['Tot_30day_Fills'] = np.maximum(1.0, rng.gamma(shape=6.0, scale=2.5, size=n)).round(2)

    if 'Tot_Drug_Cst' in missing_cols or 'Tot_Drug_Cst' not in df.columns:
        cost_mult = rng.uniform(850.0, 2600.0, size=n)
        df['Tot_Drug_Cst'] = (df['Tot_30day_Fills'] * cost_mult).round(2)

    if 'CMS_Volume_Decile' not in df.columns:
        df['CMS_Volume_Decile'] = np.clip(np.ceil((df['Tot_30day_Fills'] / 30.0) * 10.0), 1, 10).astype(int)

    if 'HCP_Tier' in missing_cols or 'HCP_Tier' not in df.columns:
        df['HCP_Tier'] = df['CMS_Volume_Decile'].map(lambda d: 1 if d >= 8 else (2 if d >= 4 else 3))

    # 3. CRM Detailing Activity (Uniform / Normal / Poisson)
    if 'Target_Calls' in missing_cols or 'Target_Calls' not in df.columns:
        spec_caps = df['Specialty'].map(lambda s: SPEC_CAPACITY.get(s, 1.0)).values
        lams = np.maximum(2.0, df['CMS_Volume_Decile'].values * 1.2 * spec_caps)
        df['Target_Calls'] = np.clip(rng.poisson(lams), 2, 16)

    if 'Actual_Calls' in missing_cols or 'Actual_Calls' not in df.columns:
        comp_factors = rng.beta(7.0, 3.0, size=n)
        df['Actual_Calls'] = np.maximum(0, np.round(df['Target_Calls'].values * comp_factors).astype(int))

    if 'Samples_Dropped' in missing_cols or 'Samples_Dropped' not in df.columns:
        sample_lams = np.maximum(0.5, df['Actual_Calls'].values * 0.95)
        df['Samples_Dropped'] = np.clip(rng.poisson(sample_lams), 0, df['Actual_Calls'].values + 3)

    # 4. Response & Lift Metrics
    if 'Rx_Lift_Pct' in missing_cols or 'Rx_Lift_Pct' not in df.columns:
        rep_qualities = {r: float(rng.beta(4.0, 2.0)) for r in REPS}
        rq = df['Sales_Rep'].map(lambda r: rep_qualities.get(r, 0.65)).values
        spec_caps = df['Specialty'].map(lambda s: SPEC_CAPACITY.get(s, 1.0)).values
        
        actual = df['Actual_Calls'].values
        samples = df['Samples_Dropped'].values
        
        ec50 = 4.0
        emax = 6.5 * rq * spec_caps
        call_eff = np.where(actual > 0, (emax * (actual ** 1.5)) / (ec50 ** 1.5 + (actual ** 1.5)), 0.0)
        samp_eff = 1.2 * np.sqrt(samples) * spec_caps
        noise = rng.normal(0.0, 1.2, size=n)
        
        rx_lift = np.clip(0.5 + call_eff + samp_eff + noise, -3.0, 18.0)
        df['Rx_Lift_Pct'] = np.round(rx_lift, 4)

    if 'Post_Campaign_Fills' in missing_cols or 'Post_Campaign_Fills' not in df.columns:
        df['Post_Campaign_Fills'] = np.maximum(0.0, df['Tot_30day_Fills'] * (1.0 + df['Rx_Lift_Pct'] / 100.0)).round(2)

    return df


def calculate_derived_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Re-calculate derived features for explainable AI drivers and downstream inference.
    """
    df = df.copy()
    derived: List[str] = []

    # 1. Primary Program Drivers
    df['Monthly_Call_Frequency_raw'] = (df['Actual_Calls'] / 3.0).round(4)
    derived.append('Monthly_Call_Frequency_raw')

    df['Sample_Call_Ratio_raw'] = (df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)).round(4)
    derived.append('Sample_Call_Ratio_raw')

    df['Compliance_Pct_raw'] = (df['Actual_Calls'] / df['Target_Calls'].clip(lower=1) * 100.0).round(4)
    derived.append('Compliance_Pct_raw')

    # 2. Auxiliary features
    if 'Tot_30day_Fills_raw' not in df.columns:
        df['Tot_30day_Fills_raw'] = df['Tot_30day_Fills'].astype(float)
        derived.append('Tot_30day_Fills_raw')

    df['Log_Baseline_Fills_raw'] = np.log1p(df['Tot_30day_Fills_raw']).round(4)
    derived.append('Log_Baseline_Fills_raw')

    df['Diminishing_Call_Log_raw'] = np.log1p(df['Actual_Calls']).round(4)
    derived.append('Diminishing_Call_Log_raw')

    if 'CMS_Volume_Decile' not in df.columns:
        df['CMS_Volume_Decile'] = np.clip(np.ceil((df['Tot_30day_Fills_raw'] / 30.0) * 10.0), 1, 10).astype(int)

    df['Tier_Compliance_Interaction_raw'] = (df['Compliance_Pct_raw'] * df['CMS_Volume_Decile']).round(4)
    derived.append('Tier_Compliance_Interaction_raw')

    spec_means = df.groupby('Specialty')['Tot_30day_Fills_raw'].transform('mean').clip(lower=1.0)
    df['Baseline_Volume_Saturation_raw'] = (df['Tot_30day_Fills_raw'] / spec_means).round(4)
    derived.append('Baseline_Volume_Saturation_raw')

    df['Delta_Log_Fills'] = (np.log1p(df['Post_Campaign_Fills']) - np.log1p(df['Tot_30day_Fills_raw'])).round(6)
    derived.append('Delta_Log_Fills')

    return df, derived


def compute_driver_scorecards(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Compute rep scorecards with true whole-integer driver metrics (Cadence, Sample Drop Volume, Baseline Fills, Compliance)
    and actionable multi-driver coaching recommendations.
    """
    scorecards = []
    reps = sorted(df['Sales_Rep'].dropna().unique())
    
    fills_col = 'Tot_30day_Fills_raw' if 'Tot_30day_Fills_raw' in df.columns else 'Tot_30day_Fills'
    terr_75th_fills_per_hcp = df.groupby('Territory')[fills_col].quantile(0.75).round(2).to_dict() if 'Territory' in df.columns and fills_col in df.columns else {}

    for rep in reps:
        sub = df[df['Sales_Rep'] == rep]
        n_hcp = len(sub)
        target_calls = int(sub['Target_Calls'].sum())
        actual_calls = int(sub['Actual_Calls'].sum())
        samples = int(sub['Samples_Dropped'].sum())
        
        # 4 Driver Whole Integer Actuals & Targets
        cadence = int(round(actual_calls / 3.0))
        target_cadence = int(round(target_calls / 3.0))

        sample_ratio = round(float(samples / max(1, actual_calls)), 2)
        target_sample_ratio = 1.00

        territory = sub['Territory'].mode()[0] if not sub.empty and 'Territory' in sub.columns else 'TERR-01'
        baseline_volume = int(round(sub[fills_col].sum())) if fills_col in sub.columns else int(round(n_hcp * 20.0))
        p75_hcp = float(terr_75th_fills_per_hcp.get(territory, 20.0))
        target_baseline = int(round(n_hcp * p75_hcp))

        compliance_pct = int(round(actual_calls / max(1, target_calls) * 100.0))
        target_compliance = 80

        rx_lift = round(float(sub['Rx_Lift_Pct'].mean()), 3) if n_hcp else 0.0
        comp_pct = compliance_pct

        # Dynamic Multi-Driver Coaching Decision Matrix:
        if rx_lift >= 4.5 and cadence >= target_cadence:
            quadrant = 'Star Performers'
            priority = 'On Track'
            action_flag = '🟢 Maintain & Scale'
            rec = f'Top Performer: Exceeding targets ({cadence}/{target_cadence} monthly calls, {samples}/{actual_calls} samples dropped, +{rx_lift:.2f}% Rx Lift). Share detailing best practices across territory.'
            bottleneck = f'Top Performer (+{rx_lift:.2f}% Rx Lift, {cadence}/{target_cadence} calls/mo)'
            trajectory = 'improving'
        elif rx_lift >= 4.5 and cadence < target_cadence:
            quadrant = 'Star Performers'
            priority = 'Monitor'
            action_flag = '🟡 Efficiency Optimization'
            rec = f'High Return, Low Volume: High prescriber responsiveness. {rep} completed {cadence} of {target_cadence} target monthly calls and dropped {samples} samples across {actual_calls} visits. Increase visit volume to {target_cadence} calls/mo and ensure 1 sample per visit to maximize total adoption.'
            bottleneck = f'High Return, Low Volume ({cadence}/{target_cadence} calls/mo, {samples}/{actual_calls} samples)'
            trajectory = 'improving'
        elif 2.5 <= rx_lift < 4.5:
            quadrant = 'Unrealized Potential'
            priority = 'Monitor'
            action_flag = '🟡 Targeting Refinement'
            rec = f'Moderate Lift: On track with {cadence}/{target_cadence} monthly calls. Refine call planning and sample distribution ({samples}/{actual_calls} samples) toward top-tier physicians.'
            bottleneck = f'Targeting Refinement (+{rx_lift:.2f}% Lift, {cadence}/{target_cadence} calls/mo)'
            trajectory = 'stable'
        elif rx_lift < 2.5 and (cadence < target_cadence or samples < actual_calls):
            quadrant = 'Needs Intervention'
            priority = 'Urgent Coaching'
            action_flag = '🔴 Urgent Coaching'
            rec = f'Driver Deficit: Falling short of call target ({cadence} vs {target_cadence} monthly calls) and sample target ({samples} vs {actual_calls} samples dropped across visits). Prioritize doctor visit cadence.'
            bottleneck = f'Call Deficit ({cadence} vs {target_cadence} calls/mo)' if cadence < target_cadence else f'Sample Deficit ({samples} vs {actual_calls} samples)'
            trajectory = 'declining'
        else:
            quadrant = 'Efficiency Risk'
            priority = 'Monitor'
            action_flag = '🟡 Performance Review'
            rec = f'Review Detailing Quality: Completed {cadence}/{target_cadence} monthly calls and {samples}/{actual_calls} samples dropped. Optimize detailing message and targeting.'
            bottleneck = f'Detailing Quality Review (+{rx_lift:.2f}% Rx Lift)'
            trajectory = 'declining'

        # Calculate Rep CEI
        cad_score = min(1.0, (actual_calls / 3.0) / max(1.0, target_calls / 3.0))
        samp_score = min(1.0, (samples / max(1.0, actual_calls)) / 1.0)
        tier_score = (sub['HCP_Tier'].isin([1, 2]).sum() / max(1, n_hcp)) if 'HCP_Tier' in sub.columns else 1.0
        comp_score_val = min(1.0, actual_calls / max(1.0, target_calls))
        cei_score = round(float((cad_score * 0.676 + samp_score * 0.249 + tier_score * 0.056 + comp_score_val * 0.019) * 100.0), 1)

        scorecards.append({
            'rep_id': str(rep),
            'sales_rep_name': str(rep),
            'territory_id': str(territory),
            'is_active': True,
            'prescriber_count': n_hcp,
            'total_target_calls': target_calls,
            'total_actual_calls': actual_calls,
            'samples': samples,
            'monthly_cadence': cadence,
            'target_monthly_cadence': target_cadence,
            'sample_ratio': sample_ratio,
            'target_sample_ratio': target_sample_ratio,
            'baseline_volume': baseline_volume,
            'target_baseline_volume': target_baseline,
            'compliance_pct': comp_pct,
            'target_compliance_pct': target_compliance,
            'cei_score': cei_score,
            'rx_lift_pct': rx_lift,
            'quadrant': quadrant,
            'coaching_priority': priority,
            'action_flag': action_flag,
            'reallocation_recommendation': rec,
            'driver_recommendation': rec,
            'driver_bottleneck': bottleneck,
            'trajectory_direction': trajectory,
            'sample_size_flag': n_hcp >= 30,
        })

    return scorecards


def ingest_file(file_input: Union[str, pathlib.Path, pd.DataFrame], seed: int = 42) -> Tuple[pd.DataFrame, IngestionReport, List[Dict[str, Any]]]:
    """
    Main entry point for dynamic dataset ingestion:
    1. Loads CSV / Parquet / DataFrame
    2. Inspects columns
    3. Synthesizes missing domain distributions
    4. Calculates derived driver metrics
    5. Returns enriched DataFrame, Report, and Scorecards.
    """
    t0 = time.perf_counter()

    if isinstance(file_input, pd.DataFrame):
        df = file_input.copy()
    else:
        path = pathlib.Path(file_input)
        if not path.exists():
            raise FileNotFoundError(f'Input file not found: {path}')
        if path.suffix.lower() == '.parquet':
            df = pd.read_parquet(path)
        elif path.suffix.lower() == '.csv':
            df = pd.read_csv(path)
        elif path.suffix.lower() == '.json':
            df = pd.read_json(path)
        else:
            df = pd.read_csv(path)

    existing_cols, missing_cols = inspect_schema(df)
    report = IngestionReport(existing_cols, missing_cols, len(df))

    # Auto-synthesize missing columns
    df_synth = auto_synthesize(df, missing_cols, seed=seed)

    # Calculate derived features
    df_enriched, derived_cols = calculate_derived_features(df_synth)
    report.derived_features = derived_cols

    # Compute rep scorecards with program drivers
    scorecards = compute_driver_scorecards(df_enriched)

    report.execution_time_sec = time.perf_counter() - t0
    log.info('Dynamic ingestion completed for %d records in %.4fs (missing: %s)',
             len(df_enriched), report.execution_time_sec, missing_cols)

    return df_enriched, report, scorecards


if __name__ == '__main__':
    sample_path = BASE_DIR / 'crm_call_activity.csv'
    if sample_path.exists():
        df_out, rep, cards = ingest_file(sample_path)
        log.info('Test ingestion report: %s', rep.to_dict())
        log.info('Generated %d rep scorecards.', len(cards))
