# Rep Call Plan Compliance & Effectiveness Scorecard

An end-to-end pharma sales-operations analytics platform that simulates a remote-detailing campaign, scores sales reps on call-plan compliance versus prescribing outcome (Rx lift), benchmarks ML models on lift prediction, and surfaces a manager-facing dashboard for reallocating call effort toward the highest-lift prescribers.

## Business problem

Pharmaceutical sales managers deploy field reps to engage prescribers on a monthly call plan — a target number of visits and sample drops per HCP. The operational question is straightforward: **does adherence to the plan actually move prescribing volume, and where should scarce detailing effort be redirected first?** This project builds a synthetic-but-realistic dataset with the structural shape of a specialty-pharma campaign (prescriber baselines, tiering, call/sample activity, and a causal Rx-lift signal), then measures the compliance↔lift relationship, ranks every rep on that effectiveness, and proposes a per-territory call reallocation plan.

## Live results

Numbers below are produced fresh from the current pipeline run (2026-08-21) and read directly from `dashboard/data/*.json`. All figures are computed inside the repo; nothing is copied from prior documentation.

| Metric | Hybrid mode | Synthetic mode |
|---|---|---|
| Sales reps scored | 12 | 350 |
| Territories | 6 | 14 |
| Prescriber records after privacy filter | 400 | 1,215 |
| Rows suppressed at privacy filter | 0 of 400 (0.0%) | 135 of 1,350 (10.0%) |
| Mean compliance rate | 85.2% | 69.4% |
| Mean Rx lift (observed) | 3.05% | 4.69% |
| Mean Rx lift (predicted) | 3.09% | 4.70% |
| Pearson r — compliance × observed lift (HCP-level) | 0.28 | 0.18 |
| Pearson r — compliance × predicted lift (HCP-level) | 0.54 | 0.14 |
| Best forecasting model | OLS Linear Regression | Random Forest Regressor |
| Best model Test R² | 0.098 | 0.672 |
| Bootstrap 95% CI (Test R²) | [0.02, 0.16] | [0.60, 0.73] |
| Test RMSE | 2.83 | 1.57 |

**An honest note on model performance — why Hybrid's R² is much lower than Synthetic's.** The two modes tell very different stories. **Hybrid mode** runs on the real CMS prior-prescriber plus IDR + Open Payments CSV (`data/raw_hybrid/cms_crm_dataset.csv`, 400 HCPs / 12 reps / 6 territories): the compliance data is dense (85.2% plan adherence, 0 rows suppressed) but the sample is small (400 HCPs) and the signal is weak — the HCP-level compliance→lift correlation is only 0.28. No model can learn much from a single 80-row holdout; R² bounces between −0.03 and +0.16 depending on which rows land in the test split. Hybrid therefore reports the **repeated 5-fold CV pooled out-of-sample R²**, and deploys **OLS Linear Regression** for interpretability: pooled Test R² **0.098** with bootstrap CI [0.02, 0.16]. The in-sample R² is 0.14, so the association is real but explains only ~10% of variance — the honest, directional read for a small real-world slice. **Synthetic mode** (1,215 HCPs) is generated from a known functional form plus noise, so it shows a healthy, reproducible Test R² of 0.67 with CI [0.60, 0.73]. Treat the absolute R² as directional evidence, not a production-grade guarantee.

Top attribution drivers (hybrid, shown in the dashboard's ML Driver Attribution panel): **monthly call frequency (~29.5%)** and **call-plan compliance (~20.2%)** lead, followed by **sample call ratio (~14.6%)** and the volume-interaction features — an ordering that shifts toward call-visit mechanics on the small real slice. The panel reflects the Random Forest benchmark's permutation importance, while the deployed OLS model carries the comparable signed coefficients shown in the note above.

## Screenshots

All screenshots are freshly captured from the running dashboard against the files produced in the Phase 1 run above.

### Overview

![Overview](docs/screenshots/overview.png)

Executive KPI cards (mean compliance 85.2%, 400 HCPs across 12 reps) plus the Program Drivers panel — the at-a-glance summary a sales ops lead reads first.

### Performance Matrix

![Performance Matrix](docs/screenshots/performance-matrix.png)

The compliance × Rx-lift scatter with the 2x2 quadrant cards (Star Performers / Efficiency Risk / Unrealized Potential / Needs Intervention). This is the core analytical view: it visually separates reps to keep vs. coach.

### Reps Scorecard

The rep-by-rep scorecard table with compliance, cadence, sample ratio, lift, quadrant, and coaching flag — the actionable per-rep detail layer.

### Territory Engine

The reallocation engine built for this project: recommendation-bucket summary cards, top-6 upside/capacity-release movers, and the 12-row filterable reallocation table with %-of-target units, search, bucket filter, and CSV export.

### Prescribers

The prescriber directory with demography, baseline fill volume, post-campaign lift, and assigned rep — the ground-level data behind every summary.

### Coaching Queue

![Coaching Queue](docs/screenshots/coaching-queue.png)

Today's prioritized coaching tasks (urgent gaps, monitor candidates) — the operational hand-off from analytics to the field manager.

### Pipeline Inspector

The data-engineering pipeline viewer showing stage-by-stage execution telemetry — for auditors verifying provenance.

### Architecture Modal

![Architecture Modal](docs/screenshots/architecture-modal.png)

The end-to-end architecture and ingestion telemetry overlay — documents the whole flow from raw HCP records through models to the dashboard.

## Architecture

The project is a staged data-engineering + analytics pipeline; every stage writes versioned, checksummed artifacts into `data/generated/`:

```
generate  src/pipeline/generate_dataset.py      → data/generated/raw/*          (HCP records, CRM call/sample activity)
preprocess src/pipeline/data_preprocessing.py   → data/generated/processed/*    (feature engineering, scaling)
analytics src/analytics/analytics_engine.py     → data/generated/analytics/*    (compliance, lift, reallocation, telemetry)
ml        src/models/ml_models_suite.py          → src/models/artifacts/*        (model tournament, SHAP, bootstrap CI)
predict   src/models/predict.py                  → data/generated/predictions/*  (scored HCP lift)
export    src/export/build_dashboard_data.py     → dashboard/data/*              (verified JSON for the frontend)
dashboard frontend/ (static SPA)                consumes dashboard/data/*        (manifest-verified, hash-checked)
serve     src/api/predict_server.py              → http://127.0.0.1:8110         (static files + inference endpoint)
```

Two dataset modes run side-by-side and are carried through every stage:

- **Hybrid** — real CMS stay-on-label prescriber structure as the baseline shape, re-pointed at an Insys/TIRF-style product and overlaid with an exogenous synthetic CRM detailing layer.
- **Synthetic** — fully synthetic profiles generated from statistical distributions, structurally identical schema for end-to-end testing at larger scale.

### Inference Server (`src/api/predict_server.py`)

A stdlib-only HTTP server (`ThreadingHTTPServer`, zero dependencies) that serves **both**:

1. **Static frontend** — same layout as `python -m http.server` run from the repository root (routes `/` → `/frontend/index.html`, serves all `frontend/` assets).
2. **POST `/api/predict_custom`** — inference-only scoring endpoint for custom dataset uploads. Accepts `multipart/form-data` (field `file`) or raw `text/csv` body, plus optional `model` query parameter (`hybrid` | `synthetic`, default `hybrid`).

The endpoint **does not retrain**. It loads the pre-trained joblib pipeline from `src/models/artifacts/best_hybrid.joblib` (OLS) or `best_synthetic.joblib` (Random Forest), builds the identical feature matrix using the same `build_feature_matrix` logic as training, and returns:

```json
{
  "ok": true,
  "model": "hybrid",
  "model_label": "OLS Linear Regression",
  "importance_method": "abs_coefficient_normalized",
  "driver_label": "Driver attribution uses the pre-trained Hybrid CMS/CRM model...",
  "n_rows": 100,
  "feature_names": ["Compliance_Pct_raw", "Monthly_Call_Frequency_raw", ...],
  "feature_importance": [{"feature": "Monthly_Call_Frequency_raw", "importance_pct": 38.11}, ...],
  "predicted_rx_lift_pct": [3.63, 4.24, 5.07, ...],
  "npis": ["1003000126", "1003000127", ...]
}
```

**Validation behavior** — if the uploaded CSV lacks required columns (`Actual_Calls`, `Target_Calls`, `Samples_Dropped`, `Tot_30day_Fills`, `Specialty`, `HCP_Tier`), the endpoint returns **400** with a specific error code and the exact missing column names:

```json
{
  "ok": false,
  "error": "MISSING_COLUMNS",
  "message": "Uploaded CSV cannot be mapped to the trained model: missing 3 required columns: Samples_Dropped, Specialty, HCP_Tier. (Samples_Dropped -> feeds sample-drop ratio and sample velocity; Specialty -> feeds baseline-volume normalization (per-specialty mean); HCP_Tier -> feeds tier interaction and tier level). Re-upload with these columns (names must match exactly).",
  "missing_columns": ["Samples_Dropped", "Specialty", "HCP_Tier"]
}
```

The frontend surfaces these as red error chips so users see exactly which columns to add.

## Tech stack

- **Python 3.10** — pandas, numpy, scikit-learn, XGBoost, SHAP, scipy, pyarrow, joblib, jsonschema, pytest, mypy (`requirements.txt`).
- **Frontend** — vanilla ES modules (`frontend/js/`), hand-built SVG/canvas charting, hash-routed single-page app, no framework dependencies. Dev tooling: Playwright, ESLint, Prettier (`package.json`).
- **Model fallback note** — if XGBoost cannot load its OpenMP runtime (`libomp`, a common issue on macOS without Homebrew), the pipeline logs a warning and substitutes `GradientBoostingRegressor`; this is non-blocking and CI passes either way. `predict.py` applies the same substitution at inference if a persisted XGBoost artifact fails to load on this machine (re-fitting the equivalent Gradient Boosting model on the processed feature matrix), so end-to-end scoring completes regardless.

## How to run

Use `venv/bin/python` — the only interpreter in this environment with the complete ML stack (scikit-learn, xgboost, shap).

```bash
# 1. Reproduce the data + analytics + model artifacts
venv/bin/python src/pipeline/generate_dataset.py
venv/bin/python src/pipeline/data_preprocessing.py
venv/bin/python src/analytics/analytics_engine.py
venv/bin/python src/models/ml_models_suite.py
venv/bin/python src/models/predict.py
venv/bin/python src/export/build_dashboard_data.py

# 2. Serve the dashboard (static frontend + inference endpoint)
venv/bin/python -m src.api.predict_server --port 8110
# open http://127.0.0.1:8110/frontend/index.html

# 3. Run the test suite (backend; frontend changes are verified via browser/CDP)
venv/bin/python -m pytest -v
```

## Custom Dataset Upload

The dashboard includes a **Choose Dataset** modal (triggered from the header) with three options:

1. **Synthetic** — 1,215 HCPs, 350 reps, 14 territories (pre-loaded).
2. **Hybrid CMS** — 400 HCPs, 12 reps, 6 territories from real CMS + synthetic CRM overlay (pre-loaded).
3. **Upload Dataset** — upload a custom CSV and have it scored by the pre-trained model.

### Upload flow

1. Click **Upload Dataset** → file picker opens.
2. Select a CSV with at least the required columns (see validation list above).
3. A **staged processing view** appears with four steps:
   - 🔍 **Column Inspection** — scans required vs. missing columns
   - 🧪 **Auto-Synthesis** — fills any missing columns via statistical distributions (Gamma fills, Poisson samples, Normal calls)
   - ⚙️ **Derived Features** — calculates cadence, sample ratio, interactions
   - 🤖 **ML Driver Attribution** — calls `/api/predict_custom` with the uploaded CSV; the pre-trained model returns per-HCP predicted Rx lift + feature importance
4. On success: modal shows ✓ Done, switches to the Custom dataset, and closes after ~1.2s.
5. On validation failure: the error panel renders the **specific missing columns as red chips** (e.g., "Samples_Dropped", "Specialty", "HCP_Tier") — no generic "upload failed" message.
6. If the inference endpoint is unreachable (e.g., running under plain `http.server`), the UI falls back to full client-side synthesis so the app still works offline.

### Required columns for upload

| Column | Purpose |
|---|---|
| `Actual_Calls` | compliance percentage and monthly call cadence |
| `Target_Calls` | compliance percentage (actual / target) |
| `Samples_Dropped` | sample-drop ratio and sample velocity |
| `Tot_30day_Fills` | baseline volume, log-fills, and volume saturation |
| `Specialty` | baseline-volume normalization (per-specialty mean) |
| `HCP_Tier` | tier interaction and tier level (must be 1, 2, or 3) |

Additional columns (`Prscrbr_NPI`, `Physician_Name`, `Brand_Name`, `City`, `State`, `Sales_Rep`, `Territory`, `Rx_Lift_Pct`, `Post_Campaign_Fills`) are optional and used if present; otherwise synthesized.

## Known limitations

- **Model performance ceiling on synthetic data** — the lift signal is generated, so residual variance is lower-bounded; R² ~0.67 with wide bootstrap CIs should be read as directional, not predictive guarantees.
- **Data provenance** — no real patient PII and no per-patient prescribing records. Hybrid mode loads genuinely real CMS prior-prescriber utilization (`data/raw_hybrid/cms_crm_dataset.csv` — aggregate CMS Part B prescriber columns, no patient identifiers) overlaid with an exogenous synthetic CRM detailing layer. Synthetic mode is fully statistical. Any business conclusions are demonstration-grade until validated against proprietary field data.
- **XGBoost / libomp fallback** — on machines without a loadable OpenMP runtime, XGBoost is skipped with a warning and Gradient Boosting is substituted; benchmarking still completes.
- **Netlify deployment** — Netlify can only host the **static frontend**. The Python backend (`src/api/predict_server.py`) needs separate hosting (e.g., Render, Fly.io, Cloud Run, EC2) for the `/api/predict_custom` endpoint to work in production. Without the backend, custom uploads fall back to client-side synthesis only.
- **Playwright e2e tests** — browser binaries are not installed in this environment (`npx playwright install` required); e2e tests cannot run on this machine. Backend unit/integration tests (18 tests) pass.

## Project structure

```
├── frontend/                 # Static ES-module SPA (app.js, tables.js, filters.js, charts.js, modals.js)
├── dashboard/data/           # Manifest-verified JSON consumed by the frontend
├── src/
│   ├── api/                  # predict_server.py (static + inference endpoint)
│   ├── pipeline/             # generate → preprocess
│   ├── analytics/            # scoring, reallocation engine
│   ├── models/               # ML tournament, artifacts, prediction
│   └── export/               # dashboard export + checksums
├── data/generated/           # raw / processed / analytics / predictions artifacts
├── tests/                    # pytest suite (export integrity, ingestion, ML flow)
├── docs/                     # audit/technical documentation + screenshots
└── schema/                   # JSON schemas
```