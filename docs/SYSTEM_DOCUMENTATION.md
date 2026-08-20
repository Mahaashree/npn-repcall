# Pharma Analytics Platform — End-to-End System Documentation

An enterprise-grade, data-driven pharma analytics platform for evaluating **Sales Rep Call Plan Compliance**, estimating **Rx Volume Lift**, benchmarking **Leakage-Free Machine Learning Models**, and optimizing **Territory Call Reallocations**.

---

## 📐 1. System Overview & Architecture

```
                                  DATA & ML PIPELINE (BACKEND)
 ┌──────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────────┐
 │ Synthetic Data Engine│ ───► │ CMS Small-Cell Privacy  │ ───► │    Feature Engineering      │
 │ (generate_dataset.py)│      │ Filter (Tot_Clms >= 11) │      │ (data_preprocessing.py)     │
 └──────────────────────┘      └─────────────────────────┘      └─────────────────────────────┘
                                                                               │
 ┌──────────────────────┐      ┌─────────────────────────┐                     ▼
 │ Data Contract Export │ ◄─── │ ML Benchmarking Suite   │ ◄─── ┌─────────────────────────────┐
 │(build_dashboard_data)│      │ (ml_models_suite.py)    │      │ Analytics & Segmentation    │
 └──────────┬───────────┘      └─────────────────────────┘      │ (analytics_engine.py)       │
            │                                                   └─────────────────────────────┘
            │ Writes JSON + manifest.json (SHA-256 Checksums)
            ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   DASHBOARD INTERFACE (FRONTEND)                           │
 │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
 │  │ Executive KPIs   │  │ 2x2 Matrix Cards │  │ Rep Scorecard    │  │ Prescribers Table│  │
 │  └──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
 │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
 │  │ Territory Rollup │  │ ML Model Lab     │  │ What-If Sandbox  │  │ Coaching Queue   │  │
 │  └──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 2. Dataset Specifications

The platform processes hybrid datasets structured directly after the official [CMS Medicare Part D Prescribers by Provider and Drug Dataset](https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug/data) combined with exogenous synthetic CRM call detailing logs. **Zero real patient or physician private data is used.**

### A. Master Source Datasets (`/data/`)

1. **`data/rep_master.csv`** (Sales Representative Master):
   - **`rep_id`**: Unique sales representative identifier (`REP-01` to `REP-14`).
   - **`sales_rep_name`**: Sales representative full name.
   - **`territory_id`**: Assigned territory identifier (`TERR-01` to `TERR-06`).
   - **`is_active`**: Boolean status flag (`True` = active, `False` = inactive/departed).

2. **`data/doctor_master.csv`** (Prescriber Master — 820 initial records):
   - **`Prscrbr_NPI`**: 10-digit National Provider Identifier.
   - **`Physician_Name`**: Physician full name.
   - **`Specialty`**: Medical specialty (e.g., *Cardiology*, *Oncology*, *Pain Medicine*, *Neurology*, *Rheumatology*).
   - **`City` & `State`**: Geographic location.
   - **`Brand_Name`**: Primary prescribed pharmaceutical brand.
   - **`Sales_Rep`**: Assigned sales rep ID.
   - **`Territory`**: Territory ID.
   - **`HCP_Tier`**: Priority tier (`1` = Tier 1 Key Accounts, `2` = Tier 2 Mid-Volume, `3` = Tier 3 Target).
   - **`Target_Calls`**: Annual target detailing visits.
   - **`Actual_Calls`**: Actual recorded detailing visits.
   - **`Tot_30day_Fills`**: Pre-campaign baseline 30-day prescription volume.
   - **`Post_Campaign_Fills`**: Post-campaign 30-day prescription volume.

### B. Privacy & Small-Cell Suppression Rules
- **CMS Privacy Rule**: Applies small-cell suppression ($\text{Tot\_30day\_Fills} \ge 11$). Any prescriber record with fewer than 11 annual claims is suppressed to prevent physician re-identification.
- **Suppression Metrics**: 87 out of 820 initial records are suppressed, leaving 733 retained HCP prescribers for downstream analysis.

---

## ⚙️ 3. Pipeline Workflow

```
Step 1: Synthetic Data Generation  ──► Generate 820 HCPs & 14 Reps across 6 Territories
Step 2: CMS Privacy Filter          ──► Suppress claims < 11 (87 suppressed, 733 retained)
Step 3: Feature Engineering         ──► Compliance %, Call Freq, Sample Velocity, Log Fills
Step 4: Analytics & Segmentation    ──► OLS Regression, Pearson r, 2x2 Performance Matrix
Step 5: Leakage-Free ML Suite       ──► 5-Fold CV + Held-Out Test Set (Ridge, RF, XGBoost)
Step 6: Schema Contract Export      ──► Validate against JSON Schema, write JSON + SHA-256 Manifest
```

### Derived Features (`data_preprocessing.py`)
1. **`Compliance_Pct`**: $\min\left(110\%, \frac{\text{Actual\_Calls}}{\max(1, \text{Target\_Calls})} \times 100\right)$
2. **`Monthly_Call_Frequency`**: $\frac{\text{Actual\_Calls}}{3.0}$
3. **`Sample_Velocity`**: $\frac{\text{Samples\_Dropped}}{\max(1, \text{Actual\_Calls})}$
4. **`Log_Baseline_Fills`**: $\ln(1 + \text{Tot\_30day\_Fills})$
5. **`Rx_Lift_Pct`**: $\frac{\text{Post\_Campaign\_Fills} - \text{Tot\_30day\_Fills}}{\text{Tot\_30day\_Fills}} \times 100$

---

## 🐍 4. Backend Architecture (`/src/` & `/schema/`)

The backend is built with Python (3.10+), Pandas, NumPy, Scikit-Learn, and PyTest.

### Directory Structure
```text
/src/
  ├── export/
  │   └── build_dashboard_data.py   # Public export interface with schema validation & --dry-run
  ├── metrics/                      # Statistical calculations (Compliance %, OLS fit, Pearson r)
  ├── modeling/                     # ML training, cross-validation, and held-out evaluation
  └── validation/                   # Schema validation helper routines
/schema/
  └── dashboard_data_contract.json  # JSON Schema specification for frontend data payloads
```

### Export Script Interface (`src/export/build_dashboard_data.py`)
- **Type Annotations**: 100% typed with MyPy compliance (`py -m mypy`).
- **Structured Logging**: Emits formatted UTC logs (`INFO`, `WARNING`, `ERROR`).
- **CLI Options**:
  ```bash
  # Production Export (writes JSON files & manifest.json)
  py src/export/build_dashboard_data.py

  # CI Validation Run (validates schema without disk writes)
  py src/export/build_dashboard_data.py --dry-run
  ```

### Generated JSON Payloads (`/dashboard/data/`)
1. **`manifest.json`**: Contains version hash, UTC timestamp, and SHA-256 checksums of all data files.
2. **`reps.json`**: Complete rep master records (active & inactive), compliance %, lift %, and coaching priority.
3. **`scatter_points.json`**: 733 HCP prescribers for scatter plot visualization.
4. **`ml_results.json`**: Tournament leaderboard (R², MAE, RMSE, Overfit Gap, Bootstrap 95% CIs).
5. **`attribution.json`**: Feature importance & SHAP contribution percentages.
6. **`coaching_queue.json`**: Prioritized sales rep coaching task queue.
7. **`pipeline_telemetry.json`**: Data engineering runtime metrics and row counts.

---

## 🖥️ 5. Frontend Architecture (`/js/` & `index.html`)

The frontend is built using standard HTML5, CSS3, and ES6 JavaScript Modules (zero external build tools required).

### Modular Codebase Structure
```text
pharma-analytics-platform/
  ├── index.html                    # Main HTML5 layout with ARIA accessibility & SVG favicon
  ├── styles.css                    # Responsive CSS theme (WCAG AA compliant contrast)
  ├── app.js                        # Main ES module entry point (<script type="module">)
  └── js/
      ├── data-loader.js            # State store, manifest fetching, Web Crypto SHA-256 verification
      ├── charts.js                 # Chart.js scatter plot (dynamic point radius) & feature bar charts
      ├── tables.js                 # Paginated Rep Scorecard, Prescribers Directory, Territory Rollup, CSV export
      ├── filters.js                # Debounced search (280ms), select filter suite, quadrant toggle
      ├── modals.js                 # Architecture, Pipeline Inspector, Rep Detail, & Coaching Queue modals
      └── sandbox.js                # What-If Call Reallocation simulation sandbox logic
```

### Key Technical Highlights
- **Single-Page Continuous Scroll Layout**: Replaced hidden tab views with one continuous scrollable monitoring dashboard featuring smooth-scroll jump links (`#overview`, `#matrix`, `#reps`, `#territories`, `#prescribers`, `#coaching-queue`) and an `IntersectionObserver` scrollspy for active navigation state highlighting.
- **Manifest-First Fetching**: Fetches `manifest.json` first, then validates SHA-256 checksums of every JSON file using Web Crypto API (`crypto.subtle.digest('SHA-256')`).
- **WCAG AA Compliance**: All badge status pills exceed 6.0:1 contrast ratios (`.badge-green` 8.1:1, `.badge-amber` 6.4:1, `.badge-red` 7.9:1, `.badge-cyan` 7.8:1, `.badge-violet` 9.2:1).
- **ARIA Keyboard Navigation**: Full support for keyboard focus states (`Tab`, `Shift+Tab`, `Enter`, `Space`, `Escape`).
- **Debounced Filters**: 280ms debounce on search inputs prevents table lag at scale.

---

## 💻 6. Continuous Single-Page Dashboard Sections

1. **Executive KPI Summary Header (`#overview`)**: Dynamic KPI cards & primary driver attribution tiles.
2. **2×2 Performance Matrix & Correlation Scatter (`#matrix`)**: Compliance × Rx Lift quadrants with OLS regression fit line and click-to-filter capability.
3. **Sales Rep Performance Scorecard (`#reps`)**: Multi-column table with pagination (10, 25, 50, 100 rows), sorting, and rep coaching modal drill-downs.
4. **Territory Call Plan Re-allocation Engine & Rollup Summary (`#territories`)**:
   - Heuristic call shifts from over-serviced low-lift HCPs to high-growth prescribers (`Calls to Add`, `Calls to Free`, `Net Delta`).
   - Aggregated territory rollup performance table.
5. **Synthesized Prescribers Directory (`#prescribers`)**: Searchable list of all retained HCPs with instant specialty/territory/tier filters and UTF-8 BOM CSV export.
6. **Coaching Queue Priorities (`#coaching-queue`)**: Task cards prioritized by compliance-lift gap with full modal view.

---

## 🧪 7. Testing & Verification Suite

```text
                               VERIFICATION SUITE
 ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
 │   ESLint Code Audit    │   │  Mypy Type Checking    │   │ CLI --dry-run Check    │
 │ (npx eslint js/ app.js)│   │ (py -m mypy src/export)│   │ (py build_dashboard)   │
 └───────────┬────────────┘   └───────────┬────────────┘   └───────────┬────────────┘
             │                            │                            │
             ▼                            ▼                            ▼
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                                   TEST EXECUTION                                 │
 │  ┌──────────────────────────────────┐    ┌──────────────────────────────────┐  │
 │  │ Python Backend Contract Tests    │    │ Playwright Frontend E2E Suite    │  │
 │  │ (pytest tests/test_export.py)    │    │ (npx playwright test)            │  │
 │  │ 10/10 PASSED                     │    │ 9/9 PASSED                       │  │
 │  └──────────────────────────────────┘    └──────────────────────────────────┘  │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

### Automated Commands
```bash
# 1. Run ESLint JavaScript linter
npx eslint js/ app.js

# 2. Run Prettier code formatter check
npx prettier --check js/ app.js index.html styles.css

# 3. Run Mypy Python type checker
py -m mypy src/export/build_dashboard_data.py

# 4. Run Backend Dry-Run Schema Validation
py src/export/build_dashboard_data.py --dry-run

# 5. Run Python Backend Test Suite (PyTest)
py -m pytest tests/test_export.py -v

# 6. Run Playwright Frontend E2E Test Suite
npx playwright test
```

---

## 🚀 8. Quick Start Guide

### Prerequisites
- **Python**: 3.10+ (with `pandas`, `numpy`, `scikit-learn`, `jsonschema`, `pytest`, `mypy`)
- **Node.js**: 18+ (with `@playwright/test`, `eslint`, `prettier`)

### Running Locally
```bash
# 1. Regenerate data contract payload
py generate_dataset.py
py data_preprocessing.py
py analytics_engine.py
py ml_models_suite.py
py src/export/build_dashboard_data.py

# 2. Start local web server
py -m http.server 8085

# 3. Open dashboard in browser
# Navigate to http://localhost:8085/index.html
```

---

## 📦 9. Production Build & Deployment Guide

The application is structured for zero-dependency static serving and multi-stage containerized deployments.

### A. Containerized Production Build (Dockerfile + Nginx)

The repository includes a multi-stage `Dockerfile` that executes the full data pipeline during build and serves the dashboard via an optimized Alpine Nginx web server.

```bash
# 1. Build Docker image (regenerates pipeline data & packages static UI)
docker build -t pharma-analytics-platform .

# 2. Run Nginx container on port 8085
docker run -d -p 8085:80 --name pharma-analytics pharma-analytics-platform

# 3. Access in browser: http://localhost:8085
```

### B. Static Cloud Deployment (Vercel / Netlify / GitHub Pages)

Because all backend outputs write to `/dashboard/data/*.json` alongside `manifest.json`, the repository can be deployed directly to static hosting platforms:

- **Vercel**: Pre-configured with [`vercel.json`](file:///c:/Users/navee/Desktop/CTS.PROJ-main/pharma-analytics-platform/vercel.json) (CORS headers & static asset routing).
- **Netlify**: Pre-configured with [`netlify.toml`](file:///c:/Users/navee/Desktop/CTS.PROJ-main/pharma-analytics-platform/netlify.toml).
- **GitHub Pages**: Set build output path to repository root or `/dashboard/data/`.
