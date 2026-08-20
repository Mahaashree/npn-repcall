from __future__ import annotations
import json
import pathlib
import unittest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / 'src' / 'models' / 'artifacts'

try:
    import sklearn  # noqa: F401  # ML stack only installed under system python3
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


@unittest.skipUnless(HAS_SKLEARN, 'scikit-learn not installed in this interpreter')
class TestPredictiveScoring(unittest.TestCase):
    def test_best_models_persisted(self):
        for mode in ('hybrid', 'synthetic'):
            self.assertTrue(
                (ARTIFACTS_DIR / f'best_{mode}.joblib').exists(),
                f'missing {ARTIFACTS_DIR}/best_{mode}.joblib',
            )

    def test_model_meta_exists(self):
        meta_path = ARTIFACTS_DIR / 'best_model_meta.json'
        self.assertTrue(meta_path.exists(), 'missing best_model_meta.json')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        for mode in ('hybrid', 'synthetic'):
            self.assertIn(mode, meta, f'mode {mode} missing from meta')
            self.assertIn('model_label', meta[mode])

    def test_predicted_lift_artifacts_written(self):
        for mode in ('hybrid', 'synthetic'):
            self.assertTrue(
                (BASE_DIR / f'predicted_rx_lift_{mode}.json').exists(),
                f'missing predicted_rx_lift_{mode}.json',
            )

    def test_prediction_count_matches_processed(self):
        import pandas as pd

        for mode in ('hybrid', 'synthetic'):
            pq = BASE_DIR / f'processed_data_{mode}.parquet'
            if not pq.exists():
                continue
            df = pd.read_parquet(pq)
            with open(BASE_DIR / f'predicted_rx_lift_{mode}.json', 'r', encoding='utf-8') as f:
                payload = json.load(f)
            self.assertEqual(len(payload['data']), len(df),
                             f'prediction count != processed row count for {mode}')

    def test_predictions_flow_into_dashboard_export(self):
        with open(BASE_DIR / 'dashboard' / 'data' / 'scatter_points.json', 'r', encoding='utf-8') as f:
            scatter = json.load(f)
        items = scatter.get('data', scatter)
        if not items:
            self.skipTest('scatter_points.json has no hybrid data items')
        present = sum(1 for h in items if h.get('predicted_rx_lift_pct') is not None)
        self.assertGreater(present, 0, 'no scatter point carries predicted_rx_lift_pct')

        with open(BASE_DIR / 'dashboard' / 'data' / 'reps.json', 'r', encoding='utf-8') as f:
            reps = json.load(f)
        rep_items = reps.get('data', [])
        present_reps = sum(1 for r in rep_items if r.get('predicted_rx_lift_pct') is not None)
        self.assertGreater(present_reps, 0, 'no rep carries predicted_rx_lift_pct')


if __name__ == '__main__':
    unittest.main()