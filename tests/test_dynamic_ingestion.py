from __future__ import annotations
import pathlib
import unittest
import pandas as pd
import numpy as np

from src.pipeline.dynamic_ingestion import (
    inspect_schema,
    auto_synthesize,
    calculate_derived_features,
    compute_driver_scorecards,
    ingest_file,
    REQUIRED_DOMAINS,
)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent


class TestDynamicIngestion(unittest.TestCase):
    def test_inspect_schema_with_missing_columns(self):
        df_partial = pd.DataFrame({
            'Prscrbr_NPI': ['1001000001', '1001000002'],
            'Physician_Name': ['Dr. Alice Smith', 'Dr. Bob Jones'],
            'Actual_Calls': [6, 8],
        })
        existing, missing = inspect_schema(df_partial)
        self.assertIn('Prscrbr_NPI', existing)
        self.assertIn('Physician_Name', existing)
        self.assertIn('Tot_30day_Fills', missing)
        self.assertIn('Samples_Dropped', missing)
        self.assertIn('Specialty', missing)

    def test_auto_synthesize_and_distributions(self):
        df_minimal = pd.DataFrame({
            'Physician_Name': [f'Dr. Physician {i}' for i in range(50)],
        })
        existing, missing = inspect_schema(df_minimal)
        df_synth = auto_synthesize(df_minimal, missing, seed=123)

        # Verify all required domains exist
        for req in REQUIRED_DOMAINS:
            self.assertIn(req, df_synth.columns, f"Missing required domain: {req}")

        # Check statistical properties of synthesized data
        self.assertTrue((df_synth['Tot_30day_Fills'] > 0).all(), "Fills should be positive")
        self.assertTrue((df_synth['Target_Calls'] >= 2).all(), "Target calls should be >= 2")
        self.assertTrue((df_synth['Actual_Calls'] >= 0).all(), "Actual calls should be >= 0")
        self.assertTrue((df_synth['Samples_Dropped'] >= 0).all(), "Samples should be >= 0")

    def test_calculate_derived_features(self):
        df = pd.DataFrame({
            'Prscrbr_NPI': ['1001000001', '1001000002'],
            'Physician_Name': ['Dr. A', 'Dr. B'],
            'Specialty': ['Pain Management', 'Oncology'],
            'Target_Calls': [10, 8],
            'Actual_Calls': [9, 6],
            'Samples_Dropped': [10, 3],
            'Tot_30day_Fills': [20.0, 15.0],
            'Rx_Lift_Pct': [5.2, 2.1],
            'Post_Campaign_Fills': [21.04, 15.315],
            'Sales_Rep': ['REP-101', 'REP-102'],
            'Territory': ['TERR-01', 'TERR-02'],
            'HCP_Tier': [1, 2],
            'CMS_Volume_Decile': [8, 5],
        })
        df_enriched, derived = calculate_derived_features(df)

        self.assertIn('Monthly_Call_Frequency_raw', df_enriched.columns)
        self.assertIn('Sample_Call_Ratio_raw', df_enriched.columns)
        self.assertIn('Compliance_Pct_raw', df_enriched.columns)

        # Check values: Actual_Calls / 3.0
        self.assertAlmostEqual(df_enriched['Monthly_Call_Frequency_raw'].iloc[0], 9.0 / 3.0, places=3)
        # Sample ratio: 10 / 9
        self.assertAlmostEqual(df_enriched['Sample_Call_Ratio_raw'].iloc[0], 10.0 / 9.0, places=3)

    def test_driver_scorecards_thresholds(self):
        df = pd.DataFrame({
            'Prscrbr_NPI': [f'NPI-{i}' for i in range(16)],
            'Physician_Name': [f'Dr. {i}' for i in range(16)],
            'Specialty': ['Pain Management'] * 16,
            'Sales_Rep': ['REP-101'] * 4 + ['REP-102'] * 4 + ['REP-103'] * 4 + ['REP-104'] * 4,
            'Territory': ['TERR-01'] * 4 + ['TERR-01'] * 4 + ['TERR-02'] * 4 + ['TERR-02'] * 4,
            'Target_Calls': [30] * 4 + [10] * 4 + [10] * 4 + [10] * 4,
            # REP-101: Low cadence (actual = 40 vs target = 120 calls), lift = 1.8% -> Urgent Coaching (Call Deficit)
            # REP-102: Exceeding calls (actual = 200 vs target = 40), low samples (40 samples = 0.20 ratio < 1.0), lift = 1.8% -> Urgent Coaching (Sample Deficit)
            # REP-103: High performer (actual = 200 calls, samples = 240, lift = 6.0%) -> On Track (Top Performer)
            # REP-104: Moderate lift (actual = 200 calls, samples = 200, lift = 3.2%) -> Monitor (Targeting Refinement)
            'Actual_Calls': [10] * 4 + [50] * 4 + [50] * 4 + [50] * 4,
            'Samples_Dropped': [10] * 4 + [10] * 4 + [60] * 4 + [50] * 4,
            'Tot_30day_Fills': [20.0] * 16,
            'Rx_Lift_Pct': [1.8] * 4 + [1.8] * 4 + [6.0] * 4 + [3.2] * 4,
            'Post_Campaign_Fills': [20.36] * 4 + [20.36] * 4 + [21.2] * 4 + [20.64] * 4,
            'HCP_Tier': [1] * 16,
            'CMS_Volume_Decile': [8] * 16,
        })
        df_enriched, _ = calculate_derived_features(df)
        scorecards = compute_driver_scorecards(df_enriched)
        cards_map = {c['rep_id']: c for c in scorecards}

        # Check driver target fields existence
        for c in scorecards:
            self.assertIn('monthly_cadence', c)
            self.assertIn('target_monthly_cadence', c)
            self.assertIn('sample_ratio', c)
            self.assertIn('target_sample_ratio', c)
            self.assertIn('baseline_volume', c)
            self.assertIn('target_baseline_volume', c)
            self.assertIn('compliance_pct', c)
            self.assertIn('target_compliance_pct', c)

        # REP-101 should be Call Deficit -> Urgent Coaching
        self.assertIn('Call Deficit', cards_map['REP-101']['action_flag'] + ' ' + cards_map['REP-101']['driver_bottleneck'])
        self.assertEqual(cards_map['REP-101']['coaching_priority'], 'Urgent Coaching')

        # REP-102 should be Low Sample Ratio -> Urgent Coaching
        self.assertIn('Sample', cards_map['REP-102']['action_flag'] + ' ' + cards_map['REP-102']['driver_bottleneck'])
        self.assertEqual(cards_map['REP-102']['coaching_priority'], 'Urgent Coaching')

        # REP-103 should be Top Performer -> On Track
        self.assertIn('Top Performer', cards_map['REP-103']['action_flag'] + ' ' + cards_map['REP-103']['driver_bottleneck'])
        self.assertEqual(cards_map['REP-103']['coaching_priority'], 'On Track')

        # REP-104 should be Targeting Refinement -> Monitor
        self.assertIn('Targeting Refinement', cards_map['REP-104']['action_flag'] + ' ' + cards_map['REP-104']['driver_bottleneck'])
        self.assertEqual(cards_map['REP-104']['coaching_priority'], 'Monitor')


if __name__ == '__main__':
    unittest.main()
