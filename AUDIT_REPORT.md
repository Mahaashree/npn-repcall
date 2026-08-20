# AUDIT_REPORT.md — Phase 1 Investigation (read-only)

**Date of audit:** 2026-08-19
**Repo:** root `/Users/mahaashreeanburaj/Downloads/cts(3 modes)` — pharma sales-ops analytics POC (Pharma Analytics Platform).
**Method:** every claim below was verified by reading code or running commands during this session. Commands + key output are shown inline. **No files were changed or archived in this phase** (a prior-phase `AUDIT_REPORT.md` existed at this path and is replaced by this write; that is the only modification, as instructed).

---

## 1. Git history

```
git log --oneline --all
  → e6a74c6 Add files via upload
git rev-list --count --all
  → 1
git log --format="%h|%an|%ae|%ci|%s"
  → e6a74c6|MADHUMITHA|231501089@rajalakshmi.edu.in|2026-08-18 12:21:28 +0530|Add files via upload
```

- **Commits:** 1 (single snapshot).
- **Time span:** one point in time (2026-08-18 12:21:28 +0530).
- **Contributors:** one (MADHUMITHA, rajalakshmi edu address).
- **AI/iteration evidence in the log:** **none** — the message is the stock GitHub "Add files via upload" web-upload message; with a single commit there is no history in which iteration could appear.
- **Where iteration actually lives:** the **working tree**, not git. `git status` shows ~40 modified/untracked files vs HEAD (frontend fixes, `dashboard/data/*`, `src/*`, `Dockerfile`, `analytics_results.json`, report docs, `synthetic_crm_dataset.csv`, `src/pipeline/dynamic_ingestion.py`, `test-results/`, `__pycache__/`, and the deleted `" - Copy.prettierrc"`). All AI-assisted/iterative generation is visible only on disk.

---

## 2. Canonical report check

Files globbed: `*REPORT*`, `AUDIT*`, `docs/*.md` at root.

| File | Dataset variant documented | Generation / date evidence noted |
|------|-----------------------------|----------------------------------|
| `PROJECT_FULL_TECHNICAL_REPORT.md` (root) | **Dual (Hybrid + Synthetic)** — but documents the **OLD snapshot**: 749 hybrid / 742 synthetic HCPs, RF `0.6052` hybrid vs XGB `0.5943` synthetic, 71/78 suppressed | no explicit timestamp in header; numbers match the pre-live-run snapshot |
| `docs/PROJECT_COMPREHENSIVE_REVIEW.md` | **Fully Synthetic** | `Generated: 2026-08-17 12:22:58` |
| `docs/BUILD_LOG.md` | pipeline **dry-run** export (hybrid/synthetic) | `2026-08-17 20:52:36 Starting Dashboard Data Export Pipeline (DRY RUN)`; references a `sandbox.js` module that no longer exists (removed) |
| `docs/AUDIT.md` | **Old pre-refactor frontend** — documents the now-removed static hero (RF `0.6842`, CI `[0.6214,0.7380]`) | no timestamp |
| `docs/SYSTEM_DOCUMENTATION.md` | **Dual-mode** architecture overview | no timestamp in header |
| `HARDCODED_DATA_AUDIT.md` (root) | **Dual (current live)** — documents live data: 820/1350 initial, 762/1227 retained, RF wins both modes | audit dated 2026-08-19 |
| `AUDIT_REPORT.md` (root) | prior Phase-1 audit artifact | was dated 2026-08-19 17:19; replaced by this report |

**Takeaway:** reports contradict each other and the live data — `PROJECT_FULL_TECHNICAL_REPORT.md` and `docs/AUDIT.md` freeze the *previous* run (749/742, 0.6052/0.5943, hero 0.6842); the live dashboard data (data_version `4ac7a09f619fd864`, generated `2026-08-19T08:55:35Z`) has 762/1227 retained and RF `0.6215`/`0.6044` winning both modes. The live-correct docs are `HARDCODED_DATA_AUDIT.md` and `docs/SYSTEM_DOCUMENTATION.md`.

---

## 3. What the running app actually reads

**Frontend fetches (only `dashboard/data/*` JSON):** confirmed in `frontend/js/data-loader.js`:
- `manifest.json` probed across candidate paths `['dashboard/data','../dashboard/data','data','.']` (lines 151–166).
- Exactly 7 payloads fetched via `fetchAndVerifyJson` against the manifest's SHA-256 map (lines 178–185): `reps.json`, `ml_results.json`, `attribution.json`, `scatter_points.json`, `coaching_queue.json`, `pipeline_telemetry.json` (+ `manifest.json` first).
- Empirically confirmed this session by the Playwright HTTP log — the browser issues **only** these 7 `GET /dashboard/data/*.json` plus `frontend/index.html`, `frontend/js/*.js`, `frontend/styles.css`, Google Fonts, and the Chart.js CDN (`index.html:16-19,632`).
- No other fetch/XHR exists in `frontend/js/*`. The custom file input (`index.html:236`) accepts `.csv/.parquet/.json` but is handled 100% client-side by `processCustomDataset` (`data-loader.js:451+`) — nothing is POSTed to a backend.

**What `src/export/build_dashboard_data.py` writes into `dashboard/data/`:** JSON payloads + `manifest.json` (SHA-256 per file, `data_version`, `generated_at`), written at lines 587–616 into `OUTPUT_DIR = BASE_DIR/dashboard/data` (line 35). Its **inputs** are: root `analytics_results.json`, `ml_benchmarks.json`, `pipeline_telemetry{.json,_hybrid.json,_synthetic.json}` (lines 28–32, 458–475), `processed_data{.parquet,_hybrid.parquet,_synthetic.parquet}` (33, 477–494), and registry masters `data/rep_master.csv`, `data/doctor_master.csv` (25–26, 432–433).

---

## 4. Suspect artifact reference audit

Legend: **LIVE** = read by pipeline/dashboard code; **WRITE-ONLY** = written by the pipeline but read nowhere downstream (regenerated every run); **ORPHAN** = no code reference at all; **BORDERLINE** = read only from an ad-hoc `__main__`/demo block.

| Artifact | Referenced by code (file:line) | Upstream write | Downstream read | Verdict |
|---|---|---|---|---|
| `ml_benchmarks_hybrid.json` | `src/models/ml_models_suite.py:355` (write), `:373` | ml_models_suite | only `ml_benchmarks.json` is read (by export) | **WRITE-ONLY** (reproducible per run) |
| `ml_benchmarks_synthetic.json` | `src/models/ml_models_suite.py:356` (write), `:373` | ml_models_suite | none | **WRITE-ONLY** (reproducible) |
| `pipeline_telemetry_hybrid.json` | `src/pipeline/data_preprocessing.py:180` (write); `src/export/build_dashboard_data.py:464-468` (read) | preprocess | export (per-mode telemetry source) | **LIVE** — do not archive |
| `pipeline_telemetry_synthetic.json` | `src/pipeline/data_preprocessing.py:184` (write); `build_dashboard_data.py:471-475` (read) | preprocess | export | **LIVE** — do not archive |
| `processed_data_hybrid.parquet` | `data_preprocessing.py:178` (write); `ml_models_suite.py:352`, `analytics_engine.py:477`, `build_dashboard_data.py:490` (read) | preprocess | ml/analytics/export | **LIVE** — canonical |
| `processed_data_synthetic.parquet` | same chain (`preprocess:182`, `ml:353`, `analytics:478`, `export:491`) | preprocess | ml/analytics/export | **LIVE** — canonical |
| `processed_data_hybrid.csv` | `data_preprocessing.py:159` (`to_csv` mirror of the parquet) | preprocess | none | **WRITE-ONLY** mirror |
| `processed_data_synthetic.csv` | `data_preprocessing.py:159` | preprocess | none | **WRITE-ONLY** mirror |
| `processed_data_hybrid.json` | `data_preprocessing.py:179` (write) | preprocess (debug dump) | none | **WRITE-ONLY** debug |
| `processed_data_synthetic.json` | `data_preprocessing.py:183` (write) | preprocess (debug dump) | none | **WRITE-ONLY** debug |
| `raw_crm_cms_dataset_hybrid.parquet` | `generate_dataset.py:207` (write); `data_preprocessing.py:173` (read) | generate | preprocess | **LIVE** — pipeline input |
| `raw_crm_cms_dataset_synthetic.parquet` | `generate_dataset.py:208` (write); `preprocessing:173-178` (read) | generate | preprocess | **LIVE** — pipeline input |
| `raw_crm_cms_dataset_hybrid.csv` | `generate_dataset.py:215` (write) | generate | none | **WRITE-ONLY** mirror |
| `raw_crm_cms_dataset_synthetic.csv` | `generate_dataset.py:216` (write) | generate | none | **WRITE-ONLY** mirror |
| `raw_crm_cms_dataset.csv` | `generate_dataset.py:222` (write) | generate (hybrid alias) | none | **WRITE-ONLY** mirror |
| `raw_crm_cms_dataset.parquet` | `generate_dataset.py:11` (OUT_PARQUET write :221); fallback input `data_preprocessing.py:19` | generate | preprocess **fallback only** | **BORDERLINE** live-fallback |
| `processed_data.parquet` | fallback input `ml_models_suite.py:35`, `analytics_engine.py` (INPUT_PATH), `build_dashboard_data.py:33/479`; read by `generate_visualizations.py:89-92` | preprocess (legacy single-mode path, not called in current `main()`) | fallback readers | **BORDERLINE** live-fallback |
| `processed_data.json` | fallback reader `generate_visualizations.py:90-93` | preprocess (legacy) | fallback | **BORDERLINE** live-fallback |
| `synthetic_crm_dataset.csv` | **no code reference** (only prior `AUDIT_REPORT.md`) | unknown/legacy | none | **ORPHAN** — archive candidate |
| `crm_call_activity.csv` | write `generate_dataset.py:219`; demo read `dynamic_ingestion.py:409` (under `if __name__=='__main__'` only) | generate | dynamic ingestion demo only | **BORDERLINE** (demo-scope read) |
| `data/output/*` (`analytics_results.json`, `ml_benchmarks.json`, `pipeline_telemetry.json`, `processed_data.*`, `raw_crm_cms_dataset.parquet`, `synthetic_crm_dataset.parquet`) | **no code writes or reads** (`grep "data/output"` → only the audit report) | none (legacy output dir) | none | **ORPHAN** — archive candidates |
| `" - Copy.prettierrc"` | — | — | — | already **deleted** in working tree (`D`) |
| `dashboard/data/*.json` (7 files) | frontend reads all (see §3) | export | frontend | **LIVE** — keep |

Reprovenance note: `ml_benchmarks{,_hybrid,_synthetic}.json` all embed `source_file: C:\Users\Marcellus\Desktop\cts updated\processed_data_{hybrid,synthetic}.parquet` — evidence of a prior Windows dev machine; the paths do not exist on this checkout, so the benchmark outputs are snapshots, not live-derived on demand.

---

## 5. CSV vs Parquet — what the pipeline actually reads/writes

`grep -rnE "read_csv|to_csv|read_parquet|to_parquet" src/`:

- **Canonical table format = Parquet.** The read chain is parquet end-to-end: `data_preprocessing` reads `raw_*_{hybrid,synthetic}.parquet` → writes `processed_*_{hybrid,synthetic}.parquet`; `ml_models_suite` and `analytics_engine` read parquet only; `build_dashboard_data` reads the per-mode parquets (plus JSON analytics/benchmarks). `generate_visualizations.py:94` and `dynamic_ingestion.py:380` also read parquet (the latter falls back to CSV for arbitrary uploads).
- **CSV = write-only convenience mirrors** (no downstream reader): `to_csv` calls exist only in `generate_dataset.py:215-222` (raw + `crm_call_activity.csv` + `rep_master.csv`) and `data_preprocessing.py:159` (processed mirror). The one CSV read in the table chain is the **master registry** (`rep_master.csv`, `doctor_master.csv` read by `build_dashboard_data.py:432-433`) — those are CSV **by design** (registry tables, small).
- **JSON = telemetry/analytics contract + debug/fallback**: `processed_data_*.json` are debug dumps; `processed_data.json` and `processed_data.parquet` are fallback inputs for `generate_visualizations`/the suites.

**Bottom line:** keep the **Parquet** variants as the canonical tables; the CSV copies are reproducible mirrors; the per-mode JSON debug dumps and the `_hybrid/_synthetic` per-mode benchmark/CSV/JSON artifacts are all regenerated each run.

---

## 6. Deployment configs

### `Dockerfile`
- **Stage 1 (builder):** `COPY data/`, `COPY schema/`, `COPY src/`, then `COPY generate_dataset.py .`, `COPY data_preprocessing.py .`, `COPY analytics_engine.py .`, `COPY ml_models_suite.py .` — **these four root-level scripts DO NOT exist.** The real paths are `src/pipeline/generate_dataset.py`, `src/pipeline/data_preprocessing.py`, `src/analytics/analytics_engine.py`, `src/models/ml_models_suite.py`. `docker build` will **fail on the first such `COPY`**.
- **Stage 2 (nginx):** `COPY index.html`, `COPY styles.css`, `COPY app.js`, `COPY js/` — **none of these exist at repo root**; they live in `frontend/`. Second guaranteed `COPY` failure.
- Implication: intended target is a **Dockerized nginx self-host** serving the dashboard at `/` + `nginx.conf` override. **Confirmed bug** (the root-path COPY lines) — unrelated to cleanup but real.
- `requirements.txt`, `data/`, `schema/`, `src/` copies are consistent with actual layout.

### `nginx.conf`
- Root `/usr/share/nginx/html`, `index index.html`, `try_files … /index.html`, `/dashboard/data/` no-cache + CORS. **Internally consistent** with the Dockerfile's *assumed* layout (index.html at html root). It does **not** match the actual layout (`frontend/index.html`, `frontend/js/*`), so a corrected build must serve `frontend/` or rewrite `/`.
- Only meaningful if the Docker target is chosen.

### `netlify.toml`
- `publish = "."`, headers for `/dashboard/data/*`. Statically consistent with the actual repo-root-serving layout (files exist at those relative paths), **but** Netlify would serve `frontend/index.html` only at `/frontend/index.html` — no root `index.html` and no `_redirects`, so the SPA home route is unconfigured. Intended target: Netlify static host.

### `vercel.json`
- `version 2`, `cleanUrls`, `trailingSlash false`, headers for `/dashboard/data/*`. Same as Netlify: repo-root host, `frontend/` subdir not wired to the root path; no redirect/rewrite to `frontend/index.html`. Intended target: Vercel static host.

**Open question (for you, not resolved here):** which is the intended deployment target — Docker/nginx self-host, Netlify, or Vercel? Docker is the only one that is currently broken (COPY paths bug). The static hosts would deploy but expose the dashboard at `/frontend/index.html` unless redirects/base-path config is added.

---

## 7. Test suite state

```
pytest (venv): 13 passed in ~2.5s        → 13/13 ✓ (matches last session)
npx playwright test (temp @playwright/test@1.49.1): 11 passed → 11/11 ✓ (matches last session)
```
Note: the repo-pinned `@playwright/test@1.62.1` cannot install its browsers on this macOS 13 arm64 host, so the e2e suite is run from the pre-existing temp Playwright install on port 8091. No regressions since the last fix session.

---

## 8. Scope check (for reference only)

The original 1-week POC scope was a **rep-level compliance/effectiveness scorecard correlating call-plan compliance with Rx-lift**. What is actually in the repo now goes well beyond that: a dual-mode + custom-ingest data platform (CMS hybrid + full synthetic + client-side CSV upload), a leakage-free 4-model ML tournament (Ridge/OLS/RF/XGBoost, CV, bootstrap CI, SHAP attribution), a multi-tab interactive dashboard (Executive KPIs, performance matrix with legacy/CEI toggles, rep scorecards + manager territory reallocation, prescribers browser, coaching queue, architecture/pipeline inspectors), Web-Crypto manifest verification, schema-contract validation, 13 pytest + 11 Playwright e2e tests, and a 6-doc documentation stack. In short: a production-flavored analytics product, not a minimal scorecard POC.

---

## Recommended Actions (archive-only; nothing executed yet — awaiting your go-ahead)

1. **Archive (safe, reproducible-only, no code reader):**
   - `synthetic_crm_dataset.csv` (orphan, untracked)
   - `data/output/*` (orphan legacy output dir — all 7 files)
   - `processed_data_hybrid.csv`, `processed_data_synthetic.csv` (write-only mirrors)
   - `processed_data_hybrid.json`, `processed_data_synthetic.json` (debug dumps)
   - `raw_crm_cms_dataset_hybrid.csv`, `raw_crm_cms_dataset_synthetic.csv`, `raw_crm_cms_dataset.csv` (write-only mirrors)
   - `ml_benchmarks_hybrid.json`, `ml_benchmarks_synthetic.json` (reproducible per run; keep `ml_benchmarks.json` combined)
2. **Keep as-is (live or fallback-live):** all `*.parquet` (raw/processed/hybrid/synthetic), `pipeline_telemetry{,_hybrid,_synthetic}.json`, `ml_benchmarks.json`, `analytics_results.json`, `data/rep_master.csv`, `data/doctor_master.csv`, `dashboard/data/*`.
3. **Borderline — decide before touching:** `crm_call_activity.csv` (read only by the untracked demo entrypoint `dynamic_ingestion.py:409`); root `processed_data.{parquet,json}` and `raw_crm_cms_dataset.parquet` (fallback inputs used only if per-mode files are absent — archiving them is safe only if code fallbacks are acceptable or the per-mode files are guaranteed present). Recommend: keep.
4. **Format to keep:** **Parquet** for tables; JSON for analytics/telemetry contracts; CSV only for the two master registry files.
5. **Deployment config:** **open question — you decide the target.** If Docker is the intended deployment, the root-path `COPY` lines are a real bug (Stage 1: 4 pipeline scripts; Stage 2: `index.html/styles.css/app.js/js/`) and must be fixed regardless of cleanup. Netlify/Vercel need a redirect/base-path so the dashboard serves at `/`.
6. **Docs:** `PROJECT_FULL_TECHNICAL_REPORT.md` and `docs/AUDIT.md` document a stale snapshot (749/742, 0.6052/0.5943) that contradicts live data — flag for a future refresh (not cleanup).

---

**Phase 1 complete — no files archived or modified except this report. Awaiting your go-ahead for Phase 2.**