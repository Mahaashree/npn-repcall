#!/usr/bin/env python3
"""Stdlib-only inference server for the CTS HCP analytics platform.

Serves the static frontend (same layout as ``python -m http.server`` run from
the repository root) plus a JSON inference endpoint::

    POST /api/predict_custom
        Content-Type: multipart/form-data          (file field name: 'file')
        or
        Content-Type: text/csv                     (raw CSV body)
        Optional parameter ``model``: hybrid | synthetic   (default hybrid)

Drives a pre-trained joblib pipeline built by
``src/models/ml_models_suite.py``. Feature vectors are produced by the exact
same ``build_feature_matrix`` used at training time, so inference is identical
to the benchmarked pipeline. No web framework, no new dependencies.

Run:  python -m src.api.predict_server --port 8110
"""

from __future__ import annotations

import argparse
import cgi
import io
import json
import logging
import mimetypes
import pathlib
import urllib.parse
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s | %(levelname)-8s | %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger('predict-server')

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent

ARTIFACT_PATHS = {
    'hybrid':    BASE_DIR / 'src' / 'models' / 'artifacts' / 'best_hybrid.joblib',
    'synthetic': BASE_DIR / 'src' / 'models' / 'artifacts' / 'best_synthetic.joblib',
}
MODEL_LABELS = {
    'hybrid':    'OLS Linear Regression',
    'synthetic': 'Random Forest Regressor',
}
IMPORTANCE_METHOD = {
    'hybrid':    'abs_coefficient_normalized',
    'synthetic': 'feature_importances_',
}
DRIVER_LABELS = {
    'hybrid': ('Driver attribution uses the pre-trained Hybrid CMS/CRM model '
               '- coefficient-weighted patterns learned from real CMS + CRM '
               'data, applied to your uploaded dataset (not freshly learned from '
               'this upload).'),
    'synthetic': ('Driver attribution uses the pre-trained Synthetic model - '
                  'random-forest feature importances learned during training, '
                  'applied to your uploaded dataset (not freshly learned from '
                  'this upload).'),
}

# Raw CSV columns the trained feature matrix is built from.
REQUIRED_COLUMNS = [
    'Actual_Calls',
    'Target_Calls',
    'Samples_Dropped',
    'Tot_30day_Fills',
    'Specialty',
    'HCP_Tier',
]
NUMERIC_COLUMNS = [
    'Actual_Calls',
    'Target_Calls',
    'Samples_Dropped',
    'Tot_30day_Fills',
]
# What each missing column feeds, so the error lists *which* columns and why.
COLUMN_PURPOSE = {
    'Actual_Calls':    'compliance percentage and monthly call cadence',
    'Target_Calls':    'compliance percentage (actual / target)',
    'Samples_Dropped': 'sample-drop ratio and sample velocity',
    'Tot_30day_Fills': 'baseline volume, log-fills, and volume saturation',
    'Specialty':       'baseline-volume normalization (per-specialty mean)',
    'HCP_Tier':        'tier interaction and tier level',
}


class PredictError(Exception):
    def __init__(self, code: str, message: str, payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.payload = payload or {}


def load_model(model_key: str):
    path = ARTIFACT_PATHS[model_key]
    if not path.exists():
        raise PredictError('MODEL_UNAVAILABLE',
                           f'Pre-trained {model_key} model is missing: {path}')
    return joblib.load(path)


def build_feature_matrix(df: pd.DataFrame):
    """Mirror of ``ml_models_suite.build_feature_matrix`` (identical math).

    Must produce byte-identical feature columns/order to the training path so
    inference matches the benchmarked pipeline.
    """
    df['CMS_Volume_Decile'] = pd.qcut(df['Tot_30day_Fills'], q=10, labels=False,
                                      duplicates='drop').astype(float) + 1.0
    df['Diminishing_Call_Log'] = np.log1p(df['Actual_Calls'])
    df['Tier_Compliance_Interaction'] = (
        df['Actual_Calls'] / df['Target_Calls'].clip(lower=1) * 100.0
    ) * df['CMS_Volume_Decile']
    df['Sample_Call_Ratio'] = df['Samples_Dropped'] / df['Actual_Calls'].clip(lower=1)
    spec_means = df.groupby('Specialty')['Tot_30day_Fills'].transform('mean').clip(lower=1.0)
    df['Baseline_Volume_Saturation'] = df['Tot_30day_Fills'] / spec_means

    base_cols = [
        'Compliance_Pct', 'Monthly_Call_Frequency', 'Sample_Velocity',
        'Log_Baseline_Fills', 'Diminishing_Call_Log',
        'Tier_Compliance_Interaction', 'Sample_Call_Ratio',
        'Baseline_Volume_Saturation',
    ]
    for col in base_cols:
        raw_col = f'{col}_raw'
        if raw_col not in df.columns:
            df[raw_col] = df[col].copy()

    feature_cols = [
        'Compliance_Pct_raw',
        'Monthly_Call_Frequency_raw',
        'Tier_Compliance_Interaction_raw',
        'Sample_Call_Ratio_raw',
        'Baseline_Volume_Saturation_raw',
        'Log_Baseline_Fills_raw',
        'HCP_Tier',
    ]
    available = [c for c in feature_cols if c in df.columns]
    X = df[available].fillna(0).astype(float).values
    return X, available, df


def validate_and_build_features(df: pd.DataFrame):
    """Validate an uploaded CSV against the trained schema and build X.

    Raises ``PredictError`` with a specific code + message; the "cannot map"
    case lists the exact missing column names.
    """
    if df is None or df.empty:
        raise PredictError('EMPTY_FILE',
                           'Uploaded file is empty or has no data rows.')

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        reasons = '; '.join(f'{c} -> feeds {COLUMN_PURPOSE[c]}' for c in missing)
        msg = (f'Uploaded CSV cannot be mapped to the trained model: missing '
               f'{len(missing)} required column{"s" if len(missing) > 1 else ""}: '
               f'{", ".join(missing)}. ({reasons}). Re-upload with these columns '
               f'(names must match exactly).')
        raise PredictError('MISSING_COLUMNS', msg,
                           {'missing_columns': missing})

    bad = {}
    for col in NUMERIC_COLUMNS:
        coerced = pd.to_numeric(df[col], errors='coerce')
        n_bad = int(coerced.isna().sum())
        if n_bad:
            bad[col] = n_bad
    if bad:
        detail = ', '.join(f'{c} ({n} cells)' for c, n in bad.items())
        raise PredictError('NON_NUMERIC_COLUMNS',
                           f'Non-numeric values found in: {detail}. '
                           f'These columns must be numeric counts.', {'columns': bad})

    fills = df['Tot_30day_Fills'].astype(float)
    if (fills < 1.0).any():
        raise PredictError('INVALID_FILLS',
                           'Tot_30day_Fills must be >= 1.0 everywhere '
                           '(the pipeline applies a baseline-fill floor).')
    if fills.nunique() < 2:
        raise PredictError('INVALID_FILLS',
                           'Tot_30day_Fills has only one distinct value; the '
                           'feature matrix needs volume spread to build '
                           'CMS_Volume_Decile bins.')

    tier = pd.to_numeric(df['HCP_Tier'], errors='coerce')
    if tier.isna().any():
        raise PredictError('INVALID_HCP_TIER',
                           'HCP_Tier contains non-numeric values or blanks.')
    if not set(np.unique(tier.astype(int))).issubset({1, 2, 3}):
        bad_tiers = sorted(set(int(t) for t in np.unique(tier.astype(int))))
        raise PredictError('INVALID_HCP_TIER',
                           f'HCP_Tier must be integer tiers 1, 2, or 3; found '
                           f'{bad_tiers}.')

    work = df.copy()
    work['HCP_Tier'] = tier.astype('int64')
    work['Compliance_Pct'] = work['Actual_Calls'] / work['Target_Calls'].clip(lower=1) * 100.0
    work['Monthly_Call_Frequency'] = work['Actual_Calls'] / 3.0
    work['Sample_Velocity'] = work['Samples_Dropped'] / work['Actual_Calls'].clip(lower=1)
    work['Log_Baseline_Fills'] = np.log1p(work['Tot_30day_Fills'].astype(float))

    X, feature_names, _ = build_feature_matrix(work)
    if np.isnan(X).any() or np.isinf(X).any():
        raise PredictError('FEATURE_DERIVATION_FAILED',
                           'Feature derivation produced NaN/inf values; '
                           'check inputs for extreme magnitudes.')

    npis = None
    if 'Prscrbr_NPI' in df.columns:
        npis = df['Prscrbr_NPI'].astype(str).where(df['Prscrbr_NPI'].notna()).tolist()
    return X, feature_names, npis


def extract_importance(model_key, model, feature_names):
    """Coefficient-weighted drivers (hybrid) or feature importances (RF)."""
    if hasattr(model, 'named_steps'):
        inner = model.named_steps['model']
    else:
        inner = model
    if model_key == 'hybrid':
        weights = np.abs(np.asarray(inner.coef_, dtype=float))
    else:
        weights = np.asarray(inner.feature_importances_, dtype=float)
    total = weights.sum()
    if total <= 0:
        weights = np.ones_like(weights)
        total = weights.sum()
    pct = (weights / total) * 100.0
    ranked = sorted(zip(feature_names, pct.tolist()),
                    key=lambda t: t[1], reverse=True)
    return [{'feature': f, 'importance_pct': round(p, 4)} for f, p in ranked]


def predict(payload_csv: str, model_key: str = 'hybrid'):
    if model_key not in ARTIFACT_PATHS:
        raise PredictError('UNKNOWN_MODEL',
                           f"model must be 'hybrid' or 'synthetic', got '{model_key}'.")

    if payload_csv is None or not payload_csv.strip():
        raise PredictError('EMPTY_FILE',
                           'Uploaded file is empty or has no data rows.')
    try:
        df = pd.read_csv(io.StringIO(payload_csv), encoding='utf-8-sig')
    except Exception as exc:
        raise PredictError('INVALID_CSV',
                           f'Could not parse upload as CSV: {exc}') from exc
    X, feature_names, npis = validate_and_build_features(df)

    model = load_model(model_key)
    preds = model.predict(X)
    lift = preds.astype(float)
    if np.isnan(lift).any():
        raise PredictError('PREDICTION_FAILED',
                           'Model produced NaN predictions for this input.')

    return {
        'ok': True,
        'model': model_key,
        'model_label': MODEL_LABELS[model_key],
        'importance_method': IMPORTANCE_METHOD[model_key],
        'driver_label': DRIVER_LABELS[model_key],
        'n_rows': int(len(df)),
        'feature_names': feature_names,
        'feature_importance': extract_importance(model_key, model, feature_names),
        'predicted_rx_lift_pct': [round(float(v), 4) for v in lift],
        'npis': npis,
    }


class PredictHandler(BaseHTTPRequestHandler):
    server_version = 'CTSPredictServer/1.0'
    MAX_BODY = 20 * 1024 * 1024
    _models = {}

    # ---- routing ---------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        if path in ('/', '/index.html'):
            self._redirect('/frontend/index.html')
            return
        if path == '/api/health':
            self._send_json(200, {
                'ok': True,
                'service': 'cts-predict-server',
                'models': {k: MODEL_LABELS[k] for k in MODEL_LABELS},
                'importance_methods': IMPORTANCE_METHOD,
            })
            return
        self._serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if urllib.parse.unquote(parsed.path) != '/api/predict_custom':
            self._send_json(404, {'ok': False, 'error': 'NOT_FOUND',
                                  'message': 'Unknown endpoint.'})
            return

        try:
            body = self.rfile.read(self._content_length())
            if len(body) > self.MAX_BODY:
                raise PredictError('PAYLOAD_TOO_LARGE',
                                   f'Upload larger than {self.MAX_BODY} bytes.')
            model_key = self._query_param(parsed.query, 'model') or 'hybrid'

            content_type = self.headers.get('Content-Type', '')
            csv_text, model_key = self._extract_csv(content_type, body, model_key)

            result = predict(csv_text, model_key=model_key)
            self._send_json(200, result)
        except PredictError as exc:
            self._send_json(400, {'ok': False, 'error': exc.code,
                                  'message': exc.message, **exc.payload})
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures
            log.exception('predict_custom failed')
            self._send_json(500, {'ok': False, 'error': 'INTERNAL_ERROR',
                                  'message': f'Unexpected server error: {exc}'})

    def do_HEAD(self):
        self.do_GET()

    # ---- helpers ---------------------------------------------------------
    def _content_length(self) -> int:
        try:
            return max(0, int(self.headers.get('Content-Length', 0)))
        except ValueError:
            return 0

    def _query_param(self, query: str, key: str):
        for pair in query.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                if urllib.parse.unquote(k) == key:
                    return urllib.parse.unquote(v)
        return None

    def _extract_csv(self, content_type: str, body: bytes, model_key: str):
        """Return (csv_text, resolved_model_key) from multipart or raw CSV."""
        ctype = content_type.split(';')[0].strip().lower()

        if ctype in ('text/csv', 'application/csv', 'text/plain',
                     'application/octet-stream'):
            return body.decode('utf-8-sig'), model_key

        if ctype.startswith('multipart/form-data'):
            environ = {
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
                'CONTENT_LENGTH': str(len(body)),
            }
            form = cgi.FieldStorage(fp=io.BytesIO(body), environ=environ)
            file_item = form['file'] if 'file' in form else None
            if file_item is None or not getattr(file_item, 'filename', None):
                raise PredictError('NO_FILE_UPLOADED',
                                   'No file attached (expected a form field '
                                   "named 'file').")
            raw = (file_item.file.read() if file_item.file
                   else file_item.value.encode('utf-8'))
            if 'model' in form and form['model'].value:
                model_key = form['model'].value
                if isinstance(model_key, bytes):
                    model_key = model_key.decode('utf-8')
                model_key = model_key.strip().lower()
            return raw.decode('utf-8-sig'), model_key

        raise PredictError('UNSUPPORTED_CONTENT_TYPE',
                           f"Expected multipart/form-data or text/csv body, "
                           f"got '{content_type}'.")

    def _serve_static(self, path: str):
        if path.startswith('/api/'):
            self._send_json(404, {'ok': False, 'error': 'NOT_FOUND',
                                  'message': f'Unknown endpoint {path}.'})
            return
        rel = path.lstrip('/') or 'frontend/index.html'
        target = (BASE_DIR / rel).resolve()
        if not str(target).startswith(str(BASE_DIR.resolve())) or not target.is_file():
            self.send_error(404, 'Not Found')
            return
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or 'application/octet-stream'
        data = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info('%s %s', self.address_string(), fmt % args)


def main():
    parser = argparse.ArgumentParser(description='CTS hybrid/synthetic predict server')
    parser.add_argument('--port', type=int, default=8110)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()

    log.info('Serving static + /api/predict_custom from %s on http://%s:%d',
             BASE_DIR, args.host, args.port)
    ThreadingHTTPServer((args.host, args.port), PredictHandler).serve_forever()


if __name__ == '__main__':
    main()