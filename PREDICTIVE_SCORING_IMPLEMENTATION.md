# PREDICTIVE_SCORING_IMPLEMENTATION.md

**Date:** 2026-08-19
**Repo:** `/Users/mahaashreeanburaj/Downloads/cts(3 modes)` — pharma sales-ops analytics POC.
**Goal:** close the gap where the ML tournament's winning model was benchmarked but never used — make the model's **predictions** reach the dashboard (predictive scoring).

---

## 1. The problem (confirmed by code trace)

The ML suite trained and scored four models (Ridge / OLS / Random Forest / XGBoost-or-GradientBoosting) but discarded every fitted estimator:

- `src/models/ml_models_suite.py` produced `y_*_pred` at `:134-136` and used them **only** to compute R² / MAE / RMSE / bootstrap CI (`:138-146`).
- The JSON exported (`ml_benchmarks.json`) contained only summaries: `metadata`, `benchmarks`, `tournament_table`, `best_model_summary` (`:337-354`). No model binary, no predictions.
- The dashboard (`reps.json`, `scatter_points.json`, KPIs) read the **ground-truth `Rx_Lift_Pct`** column directly (`build_dashboard_data.py:289`, `analytics_engine.py:441`) — so the dashboard reported *which* model won but never used any model's output.

**Impact:** the model recommended to the user (Random Forest, R² 0.62) drove zero dashboard numbers.

## 2. The fix (model persistence + inference stage)

### New artifacts
| Artifact | Purpose |
|---|---|
| `src/models/artifacts/best_hybrid.joblib` / `best_synthetic.joblib` | Serialized **winning** model per dataset mode (`joblib`) |
| `src/models/artifacts/best_model_meta.json` | Mode → {model label, target, feature names, metrics, path, saved-at} |
| `predicted_rx_lift_hybrid.json` / `predicted_rx_lift_synthetic.json` (repo root) | Per-HCP `predicted_rx_lift_pct` + actual, wired into the dashboard |

### Code changes
1. **`src/models/ml_models_suite.py`**
   - Extracted the model feature-engineering block out of `load_and_partition()` into a new shared function **`build_feature_matrix(df) -> (X, feature_names, df)`**. Same code path is now used at **train time and inference time**, guaranteeing identical feature derivation (this matters because `Baseline_Volume_Saturation_raw` is *not* stored in the parquet — it must be re-derived).
   - `run_suite()` now keeps the fitted estimator for every benchmarked model and, after ranking, persists the winner per mode via **`persist_best_model()`** (`joblib.dump` + metadata JSON).
   - Mode is inferred from the input filename (`processed_data_hybrid.parquet` → `hybrid`).

2. **`src/models/predict.py`** *(new)* — the inference stage:
   - Loads the persisted `best_{mode}.joblib`, re-derives features with `build_feature_matrix`, predicts `Predicted_Rx_Lift_Pct` for every HCP, writes root-level JSON artifacts. Run via `python3 src/models/predict.py [--mode hybrid|synthetic|all]`.

3. **`src/export/build_dashboard_data.py`**
   - Loads the prediction artifacts (`load_predictions`) and attaches them to both processed dataframes (`attach_predictions`) — hybrid and synthetic.
   - `build_reps_data` now emits `predicted_rx_lift_pct` (mean of each rep's HCP predictions) alongside the existing actual `rx_lift_pct`.
   - `build_scatter_points_data` emits per-HCP `predicted_rx_lift_pct` alongside `rx_lift_pct`.
   - No existing field is removed; the schema is permissive (`additionalProperties` allowed), so no contract change was required and no frontend change was needed. **`analytics_engine.py` was intentionally NOT touched.**

4. **`requirements.txt`** — added `joblib>=1.3.0`.

5. **`tests/test_predict.py`** *(new)* — 5 tests: persisted models exist, meta exists, artifacts written, prediction count == processed row count, and predictions actually flow into `reps.json` / `scatter_points.json`.

## 3. Problems encountered & how each was fixed

| # | Problem | Symptom | Fix |
|---|---|---|---|
| 1 | **Feature engineering was embedded in the training loader**, so an inference stage could not reproduce identical inputs (especially `Baseline_Volume_Saturation_raw`, computed in-memory and never stored). | Inference would silently use a different feature set than training → wrong predictions. | Extracted `build_feature_matrix(df)` and call it from both `load_and_partition()` and `predict.py`. |
| 2 | **`joblib` unavailable in the repo's pytest venv** (`cts-venv` has no scikit-learn stack). | ML-aware tests would fail/error in the default `pytest` run. | New tests use `@unittest.skipUnless(HAS_SKLEARN, ...)` so `cts-venv pytest` skips them cleanly while `python3` (which has the full ML stack) executes them. |
| 3 | **`pytest` not installed under system `python3`**, the interpreter that actually has scikit-learn/joblib. | Could not run the new tests under the ML interpreter. | Tests are stdlib `unittest`-based; run under `python3 -m unittest tests.test_predict` (worked: 5/5 OK). |
| 4 | **XGBoost fails to load on this Mac** (`libomp`/OpenMP runtime missing) — raises `XGBoostError`, **not** `ImportError`. | Training crashed at import even though the suite has a documented XGBoost fallback (`HAS_XGB=False` → GradientBoosting). | Widened the try/except to `except Exception` with a warning; suite now runs to completion with Gradient Boosting as the fallback competitor. |
| 5 | **Test venv split** — `cts-venv` has pandas/pyarrow but no sklearn/scipy; `python3` has the ML stack but no pytest/its own venv. | One canonical interpreter is not enough to run both pipeline and test suite. | Pipeline runs under `python3`; unit tests run under `cts-venv` for the existing 13 and under `python3 unittest` for the 5 ML-gated ones. Documented here so the split is expected, not a bug. |

## 4. Verification results (2026-08-19)

| Check | Command | Result |
|---|---|---|
| ML suite (train + persist) | `python3 src/models/ml_models_suite.py` | OK — winner RF persisted for both modes; XGBoost safely substituted with GradientBoosting |
| Inference | `python3 src/models/predict.py` | OK — 762 hybrid + 1227 synthetic HCP predictions |
| Dashboard export | `python3 src/export/build_dashboard_data.py` | OK — all 6 payloads schema-validated; predictions attached |
| Prediction coverage (hybrid scatter) | inspect `scatter_points.json` | 762/762 points have `predicted_rx_lift_pct` |
| Prediction coverage (reps) | inspect `reps.json` | 288/288 reps have `predicted_rx_lift_pct` |
| Unit tests (ML env) | `python3 -m unittest tests.test_predict` | **5 passed** |
| Unit tests (repo venv) | `pytest -q` | **13 passed, 5 skipped** (new tests auto-skip — no sklearn) |
| E2E (Playwright, port 8091) | `npx playwright test` | **11 passed** |

## 5. How to run the predictive-scoring chain

```bash
# 1. Train + benchmark + persist winners (needs scikit-learn + joblib)
python3 src/models/ml_models_suite.py

# 2. Score every HCP with the persisted best model
python3 src/models/predict.py

# 3. Rebuild dashboard data (reps/scatter now carry predicted_rx_lift_pct)
python3 src/export/build_dashboard_data.py
```

## 6. Notes / behavior change

- Dashboard **actual** lift values are unchanged (`rx_lift_pct` still = ground truth). The model's output now travels alongside them as `predicted_rx_lift_pct` (rep-level mean and per-HCP point) — nothing downstream was overwritten.
- Persisted `.joblib` files are regenerable artifacts; they are committed for reproducibility (see `src/models/artifacts/`).
- Environment caveat: the repo's test venv intentionally skips ML-gated tests; full ML runs need the interpreter that has `scikit-learn`/`joblib` (here: system `python3`).