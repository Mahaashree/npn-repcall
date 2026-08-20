# Rep Call Plan Compliance & Effectiveness Scorecard

An end-to-end pharma sales-operations analytics platform that simulates a remote-detailing campaign, scores sales reps on call-plan compliance versus prescribing outcome (Rx lift), benchmarks ML models on lift prediction, and surfaces a manager-facing dashboard for reallocating call effort toward the highest-lift prescribers.

## Business problem

Pharmaceutical sales managers deploy field reps to engage prescribers on a monthly call plan — a target number of visits and sample drops per HCP. The operational question is straightforward: **does adherence to the plan actually move prescribing volume, and where should scarce detailing effort be redirected first?** This project builds a synthetic-but-realistic dataset with the structural shape of a specialty-pharma campaign (prescriber baselines, tiering, call/sample activity, and a causal Rx-lift signal), then measures the compliance↔lift relationship, ranks every rep on that effectiveness, and proposes a per-territory call reallocation plan.

## Live results

Numbers below are produced fresh from the current pipeline run (2026-08-20) and read directly from `dashboard/data/*.json`. All figures are computed inside the repo; nothing is copied from prior documentation.

| Metric | Hybrid mode | Synthetic mode |
|---|---|---|
| Sales reps scored | 288 | 350 |
| Territories | 12 | 14 |
| Prescriber records after privacy filter | 762 | 1,227 |
| Rows suppressed at privacy filter | 58 of 820 (7.1%) | 123 of 1,350 (9.1%) |
| Mean compliance rate | 69.81% | 70.03% |
| Mean Rx lift (observed) | 5.609% | 5.057% |
| Mean Rx lift (predicted) | 5.520% | 5.061% |
| Pearson r — compliance × observed lift | 0.30 | 0.23 |
| Pearson r — compliance × predicted lift | 0.39 | 0.24 |
| Best forecasting model | Random Forest Regressor | Random Forest Regressor |
| Best model Test R² | 0.6215 | 0.6044 |
| Bootstrap 95% CI (Test R²) | [0.5220, 0.6979] | [0.5069, 0.6727] |
| Test RMSE | 1.79 | 1.64 |

**An honest note on model performance.** The winning model explains roughly 60–62% of out-of-sample variance in Rx-lift prediction, and the bootstrap confidence interval is wide (e.g. hybrid [0.52, 0.70]). Two models (Random Forest and Gradient Boosting) finish within a few points of each other in every run. On synthetic data this is expected — the lift signal is generated from a known functional form plus noise, so the residual variance is irreducible rather than a modeling failure. Treat the absolute R² as directional evidence that call and sampling behavior carries a real, learnable association with prescribing lift — not as a production-ready forecast guarantee.

Top attribution drivers (both modes): **monthly call frequency (62.6%)** and **sample drop ratio (31.5%)** dominate the model's feature importance, which is consistent with the campaign design.

## Screenshots

All screenshots are freshly captured from the running dashboard against the files produced in the Phase 1 run above.

| Screenshot | What it shows and why it matters |
|---|---|
| `docs/screenshots/overview.png` | Executive KPI cards (mean compliance 69.8%, 762 HCPs across 288 reps) plus the Program Drivers panel — the at-a-glance summary a sales ops lead reads first. |
| `docs/screenshots/performance-matrix.png` | The compliance × Rx-lift scatter with the 2x2 quadrant cards (Star Performers / Efficiency Risk / Unrealized Potential / Needs Intervention). This is the core analytical view: it visually separates reps to keep vs. coach. |
| `docs/screenshots/reps-scorecard.png` | The rep-by-rep scorecard table with compliance, cadence, sample ratio, lift, quadrant, and coaching flag — the actionable per-rep detail layer. |
| `docs/screenshots/territory-engine.png` | The reallocation engine built for this project: recommendation-bucket summary cards, top-6 upside/capacity-release movers, and the 288-row filterable reallocation table with %-of-target units, search, bucket filter, and CSV export. |
| `docs/screenshots/prescribers.png` | The prescriber directory with demography, baseline fill volume, post-campaign lift, and assigned rep — the ground-level data behind every summary. |
| `docs/screenshots/coaching-queue.png` | Today's prioritized coaching tasks (urgent gaps, monitor candidates) — the operational hand-off from analytics to the field manager. |
| `docs/screenshots/pipeline-inspector.png` | The data-engineering pipeline viewer showing stage-by-stage execution telemetry — for auditors verifying provenance. |
| `docs/screenshots/architecture-modal.png` | The end-to-end architecture and ingestion telemetry overlay — documents the whole flow from raw HCP records through models to the dashboard. |

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
```

Two dataset modes run side-by-side and are carried through every stage:

- **Hybrid** — real CMS stay-on-label prescriber structure as the baseline shape, re-pointed at an Insys/TIRF-style product and overlaid with an exogenous synthetic CRM detailing layer.
- **Synthetic** — fully synthetic profiles generated from statistical distributions, structurally identical schema for end-to-end testing at larger scale.

## Tech stack

- **Python 3.10** — pandas, numpy, scikit-learn, XGBoost, SHAP, scipy, pyarrow, joblib, jsonschema, pytest, mypy (`requirements.txt`).
- **Frontend** — vanilla ES modules (`frontend/js/`), hand-built SVG/canvas charting, hash-routed single-page app, no framework dependencies. Dev tooling: Playwright, ESLint, Prettier (`package.json`).
- **Model fallback note** — if XGBoost cannot load its OpenMP runtime (`libomp`, a common issue on macOS without Homebrew), the suite logs a warning and substitutes `GradientBoostingRegressor`; this is non-blocking and CI passes either way.

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

# 2. Serve the dashboard
venv/bin/python -m http.server 8110
# open http://localhost:8110/frontend/index.html

# 3. Run the test suite (backend; frontend changes are verified via browser/CDP)
venv/bin/python -m pytest -v
```

## Known limitations

- **Model performance ceiling on synthetic data** — the lift signal is generated, so residual variance is lower-bounded; R² ~0.60 with wide bootstrap CIs should be read as directional, not predictive guarantees.
- **Data provenance** — neither mode contains real patient PII or real prescribing records. Hybrid mode mimics CMS/Insys-style structure; synthetic mode is fully statistical. Any business conclusions are demonstration-grade until validated against proprietary field data.
- **XGBoost / libomp fallback** — on machines without a loadable OpenMP runtime, XGBoost is skipped with a warning and Gradient Boosting is substituted; benchmarking still completes.

## Project structure

```
├── frontend/                 # Static ES-module SPA (app.js, tables.js, filters.js, charts.js, modals.js)
├── dashboard/data/           # Manifest-verified JSON consumed by the frontend
├── src/
│   ├── pipeline/             # generate → preprocess
│   ├── analytics/            # scoring, reallocation engine
│   ├── models/               # ML tournament, artifacts, prediction
│   └── export/               # dashboard export + checksums
├── data/generated/           # raw / processed / analytics / predictions artifacts
├── tests/                    # pytest suite (export integrity, ingestion, ML flow)
├── docs/                     # audit/technical documentation + screenshots
└── schema/                   # JSON schemas
```