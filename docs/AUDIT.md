# Pre-Refactor Data & Frontend Audit (AUDIT.md)

**Role**: Senior Full-Stack Developer  
**Scope**: Pre-refactor audit of `index.html`, `styles.css`, `app.js`, and existing data pipeline outputs.

---

## 1. Inventory of Hardcoded Data & Static UI Elements

Below is the complete inventory of hardcoded numbers, static arrays, placeholder text, and embedded formulas in the frontend:

### A. HTML Panel Mockups & Hardcoded Elements (`index.html`)

1. **Panel 1: Program Drivers / Primary Driver Attribution Grid (`stat-grid-6`)**:
   - `Actual Calls: 42.8%` ("Eligible Detailing Impact")
   - `Samples Dropped: 28.4%` ("Sample Velocity Effect")
   - `Call Frequency: 14.1%` ("Monthly Cadence")
   - `Target Calls: 8.2%` ("Call Plan Baseline")
   - `Baseline Fills: 4.5%` ("Historical Volume")
   - `Rep Quality: 2.0%` ("Execution Score")
   - *Status*: Hardcoded static HTML numbers inside `index.html`.

2. **Panel 2: ML Tournament Summary (`hero-ml-box` & `ml-ranked-list`)**:
   - Hero Box: `Random Forest Regressor`, `0.6842 Test R²`, `5-Fold CV: 0.6715 ± 0.0210`, `95% CI: [0.6214, 0.7380]`.
   - Ranked Leaderboard:
     - `#2 XGBoost Regressor`: `0.6510 Test R²`
     - `#3 Ridge Regression`: `0.5820 Test R²`
     - `#4 OLS Linear Model`: `0.5794 Test R²`
   - *Status*: Hardcoded static HTML elements in `index.html`.

3. **Panel 3: Today's Tasks / Coaching Queue (`task-list`)**:
   - Hardcoded 5-task rep coaching queue:
     - `REP-101`: `TERR-01`, Needs Intervention (Compliance 72.9%), Priority: Urgent Coaching (`red`)
     - `REP-102`: `TERR-01`, Needs Intervention, Priority: Urgent Coaching (`red`)
     - `REP-104`: `TERR-02`, Low Lift Response, Priority: Monitor (`amber`)
     - `REP-107`: `TERR-04`, Compliance 69.7%, Priority: Monitor (`amber`)
     - `REP-103`: `TERR-02`, Star Performers, Priority: On Track (`green`)
   - *Status*: Hardcoded static list items in `index.html`.

4. **Data Engineering Telemetry Disclosure & Badges**:
   - `820 initial HCP records` (Initial synthesized population)
   - `87 records suppressed` / `Tot_Clms ≥ 11` (CMS small-cell privacy filter threshold)
   - `733 Retained HCP records`
   - `FDA TIRF REMS / Insys Rx Archive` data provenance description text.
   - *Status*: Hardcoded strings in `index.html` and `app.js` `stages` array.

5. **User Profile & Date Controls**:
   - User profile: `John Doe • Provider / Analyst`
   - Date range selector options: `January 2023`, `February 2023`, `Q1 2023 Summary`
   - *Status*: Decorative UI mockup text.

6. **Tab Badge Counter Defaults**:
   - `#tab-count-rep`: `12`
   - `#rep-record-count`: `Showing 12 reps`
   - `#tab-count-pres`: `0`
   - *Status*: Default static text overwritten upon `app.js` load.

---

### B. JavaScript Constants & Embedded Formulas (`app.js`)

1. **Quadrant Classification Thresholds (`classifyQuadrant` & `normQuadrant`)**:
   - Hardcoded 80% compliance threshold (`highComp = compliancePct >= 80`) and median lift split.
   - Hardcoded mapping dictionaries for `Star Performers`, `Efficiency Risk`, `Unrealized Potential`, `Needs Intervention`.

2. **Pipeline Inspector Static Fallbacks (`renderPipelineInspector`)**:
   - Hardcoded fallback object strings when telemetry JSON is absent (`820`, `87`, `733`, `12 Reps`, `6 Territories`, `Rx_Lift_Pct formula`).

3. **What-If Sandbox Baseline Parameters (`renderSandbox`)**:
   - `avgTargetCalls = 6`
   - `avgSamples = 3`
   - Causal formula in JS: `projLift = 0.5 + 2.4 * rq * ln(1 + projCalls) + 1.2 * sqrt(avgSamples)`
   - *Status*: Hardcoded frontend assumptions duplicating backend generator math.

4. **Scatter Chart Axis Bounding**:
   - Hardcoded axis limits: `X [0, 110]`, `Y [-4, 20]`.

5. **ML Feature Importance Palette & Truncation**:
   - Hardcoded color palette array (`COLORS = ['#38bdf8','#10b981',...]`) and `.slice(0, 10)` truncation limit.

---

## 2. Backend Pipeline Module Mapping

Below is the mapping of each frontend data element to its corresponding backend pipeline module:

| Frontend Data Element | Backend Pipeline Source Module | JSON Output Artifact |
|---|---|---|
| Rep Scorecard Table (12 reps, compliance, lift, dominant quadrant, priority) | `analytics_engine.py` (`compute_rep_scorecards`) / `/src/metrics/scorecard.py` | `analytics_results.json` → `reps.json` |
| ML Tournament Leaderboard (Test R², CV, Boot CI, Overfitting Gap) | `ml_models_suite.py` (`benchmark_models`) / `/src/modeling/tournament.py` | `ml_benchmarks.json` → `ml_results.json` |
| Primary Driver Attribution (Feature & SHAP Importance %) | `ml_models_suite.py` (`compute_shap_values`) / `/src/modeling/explainability.py` | `ml_benchmarks.json` → `attribution.json` |
| Compliance vs Rx Lift Scatter Data Points | `data_preprocessing.py` / `analytics_engine.py` | `processed_data.json` → `scatter_points.json` |
| Executive KPIs (Mean Compliance %, Volume Growth, Pearson r, OLS Slope) | `analytics_engine.py` (`compute_kpis`) / `/src/metrics/kpi.py` | `analytics_results.json` |
| Territory Call Plan Re-allocation Engine | `analytics_engine.py` (`compute_call_reallocation`) / `/src/metrics/reallocation.py` | `analytics_results.json` |
| Pipeline Execution Telemetry & Suppression Counts | `data_preprocessing.py` / `/src/validation/telemetry.py` | `pipeline_telemetry.json` |

---

## 3. Flagged Hardcoded Values WITH NO BACKEND MODULE YET

The following frontend elements are currently hardcoded with **NO corresponding backend automated module** in the pipeline:

> [!WARNING]
> 1. **Prioritized Coaching Task Queue (`coaching_queue.json`)**:
>    - **Current State**: Panel 3 ("Today's Tasks") displays 5 static HTML task rows (`REP-101`, `REP-102`, `REP-104`, `REP-107`, `REP-103`) with hardcoded reason text ("Reach out to REP-101", "Review Call Detail Quality").
>    - **Gap**: `analytics_engine.py` assigns a static `coaching_priority` string ("Urgent Coaching", "Monitor", "On Track"), but does **NOT** generate a structured daily task queue array with specific task descriptions, trajectory directions (`improving`, `declining`, `stable`), or sample size flags.
>    - **Required Action**: Create `/src/metrics/coaching_queue.py` backend step to generate `coaching_queue.json`.
>
> 2. **Sandbox Baseline Parameters (`avgTargetCalls` / `avgSamples`)**:
>    - **Current State**: `app.js` hardcodes `avgTargetCalls = 6` and `avgSamples = 3` to evaluate what-if projections.
>    - **Gap**: Baseline target call means and sample velocity baseline should be emitted by `analytics_engine.py` in metadata instead of hardcoded in JS.
>    - **Required Action**: Include `sandbox_baselines` object inside `analytics_results.json`.
>
> 3. **User Profile & Session Metadata**:
>    - **Current State**: `John Doe • Provider / Analyst` static HTML widget.
>    - **Gap**: Frontend decorative element. Needs user context configuration or session state definition.
