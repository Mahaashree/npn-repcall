# Repository Reorganization Log — Generated Pipeline Outputs

Path-only reorganization: moved live, regenerated pipeline outputs from the repository root into organized `data/generated/` subfolders. No logic changes; only path constants were updated.

## Files moved (old → new)

### data/generated/raw/
| Old path | New path |
|---|---|
| `raw_crm_cms_dataset.parquet` | `data/generated/raw/raw_crm_cms_dataset.parquet` |
| `raw_crm_cms_dataset.csv` | `data/generated/raw/raw_crm_cms_dataset.csv` |
| `raw_crm_cms_dataset_hybrid.parquet` | `data/generated/raw/raw_crm_cms_dataset_hybrid.parquet` |
| `raw_crm_cms_dataset_hybrid.csv` | `data/generated/raw/raw_crm_cms_dataset_hybrid.csv` |
| `raw_crm_cms_dataset_synthetic.parquet` | `data/generated/raw/raw_crm_cms_dataset_synthetic.parquet` |
| `raw_crm_cms_dataset_synthetic.csv` | `data/generated/raw/raw_crm_cms_dataset_synthetic.csv` |

### data/generated/processed/
| Old path | New path |
|---|---|
| `processed_data.parquet` | `data/generated/processed/processed_data.parquet` |
| `processed_data.json` | `data/generated/processed/processed_data.json` |
| `processed_data_hybrid.parquet` | `data/generated/processed/processed_data_hybrid.parquet` |
| `processed_data_hybrid.csv` | `data/generated/processed/processed_data_hybrid.csv` |
| `processed_data_hybrid.json` | `data/generated/processed/processed_data_hybrid.json` |
| `processed_data_synthetic.parquet` | `data/generated/processed/processed_data_synthetic.parquet` |
| `processed_data_synthetic.csv` | `data/generated/processed/processed_data_synthetic.csv` |
| `processed_data_synthetic.json` | `data/generated/processed/processed_data_synthetic.json` |

### data/generated/analytics/
| Old path | New path |
|---|---|
| `analytics_results.json` | `data/generated/analytics/analytics_results.json` |
| `ml_benchmarks.json` | `data/generated/analytics/ml_benchmarks.json` |
| `ml_benchmarks_hybrid.json` | `data/generated/analytics/ml_benchmarks_hybrid.json` |
| `ml_benchmarks_synthetic.json` | `data/generated/analytics/ml_benchmarks_synthetic.json` |
| `pipeline_telemetry.json` | `data/generated/analytics/pipeline_telemetry.json` |
| `pipeline_telemetry_hybrid.json` | `data/generated/analytics/pipeline_telemetry_hybrid.json` |
| `pipeline_telemetry_synthetic.json` | `data/generated/analytics/pipeline_telemetry_synthetic.json` |

### data/generated/predictions/
| Old path | New path |
|---|---|
| `predicted_rx_lift_hybrid.json` | `data/generated/predictions/predicted_rx_lift_hybrid.json` |
| `predicted_rx_lift_synthetic.json` | `data/generated/predictions/predicted_rx_lift_synthetic.json` |

## Files intentionally NOT moved
- `crm_call_activity.csv` — kept at repo root (read by `src/pipeline/dynamic_ingestion.py`)
- `dashboard/data/*` — frontend-facing exports, unchanged
- `data/rep_master.csv`, `data/doctor_master.csv` — registry files, unchanged
- `src/models/artifacts/*` — persisted model files, unchanged
- `_archive/` — untouched

## Path-constant updates (logic unchanged)
- `src/pipeline/generate_dataset.py` — added `RAW_DIR`; writes raw datasets there (`crm_call_activity.csv` stays at root)
- `src/pipeline/data_preprocessing.py` — added `RAW_DIR`, `PROCESSED_DIR`, `ANALYTICS_DIR`; inputs from `raw/`, outputs to `processed/` + `analytics/`
- `src/analytics/analytics_engine.py` — reads `processed/`, writes `analytics/analytics_results.json`
- `src/models/ml_models_suite.py` — reads `processed/`, writes `analytics/ml_benchmarks*.json`
- `src/models/predict.py` — reads `processed/`, writes `predictions/predicted_rx_lift_*.json`
- `src/export/build_dashboard_data.py` — added shared `GENERATED_DIR` + subdir constants; the 9 read-path inputs now resolve under `data/generated/`
- `tests/test_predict.py` — references updated to `data/generated/{processed,predictions}`

## Verification (post-move)
- Full pipeline re-run (6 stages, in dependency order): `generate_dataset.py` → `data_preprocessing.py` → `analytics_engine.py` → `ml_models_suite.py` → `predict.py` → `build_dashboard_data.py` — **all completed with no errors**, reading/writing exclusively under `data/generated/`
- `pytest -v`: **13 passed, 5 skipped** (skips are sklearn-gated, not run in cts-venv)
- `python -m unittest tests.test_predict`: **5 passed** (ML interpreter)
- Dashboard: `python -m http.server 8085` served `dashboard/data/manifest.json`, `reps.json`, `index.html` (HTTP 200); regenerated `scatter_points.json` / `reps.json` contain `predicted_rx_lift_pct` on all 762 hybrid points and 288 reps