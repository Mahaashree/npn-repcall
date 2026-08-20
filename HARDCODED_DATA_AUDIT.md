# HARDCODED DATA AUDIT — frontend hardcoded values vs. live JSON

- **Date:** 2026-08-19
- **Auditor:** opencode (Phase 0 — Hardcoded Data Verification)
- **Scope:** `frontend/index.html` + `frontend/js/*.js` line-by-line inventory of hardcoded values, cross-checked against live payloads in `dashboard/data/*.json` and root `analytics_results.json` / `ml_benchmarks.json` / `pipeline_telemetry.json`.
- **Live data reference:** `dashboard/data/manifest.json` → `data_version 4ac7a09f619fd864`, `generated_at 2026-08-19T08:55:35Z`.
- **Phase status:** Read-only audit. **No files were modified.** Awaiting review before cleanup.

---

## 1. Evidence / commands used

```
read  frontend/index.html
read  frontend/js/app.js
read  frontend/js/data-loader.js
read  frontend/js/charts.js
read  frontend/js/tables.js
read  frontend/js/filters.js
read  frontend/js/modals.js
read  dashboard/data/attribution.json
read  src/export/build_dashboard_data.py (lines 185–299, 340–539)
read  src/analytics/analytics_engine.py (lines 100–259)

python3 - json.load → dashboard/data/ml_results.json        (best_model_summary + tournament_table per mode)
python3 - json.load → dashboard/data/pipeline_telemetry.json (initial/suppressed/retained/execution per mode)
python3 - json.load → dashboard/data/reps.json               (sample record + counts)
python3 - json.load → dashboard/data/scatter_points.json     (comp/lift ranges + median per mode)
python3 - json.load → analytics_results.json                 (KPIs, Pearson r, OLS, quadrant summaries per mode)
python3 - json.load → dashboard/data/coaching_queue.json     (task counts + priority distribution)
python3 - json.load → ml_benchmarks.json                     (metadata: cv_folds=5, best/synthetic winners)

Javascript-free replica of renderKPIs math  → compare JS-computed mean Comp/lift & Pearson r vs analytics_results.json KPIs
(Grep tool) pattern `coaching_queue` across src/ → only src/export/build_dashboard_data.py contains it
(Grep tool) pattern `sandbox|projLift|Math.sqrt` across frontend/ → only leftover CSS + comments, no sandbox module
(Grep tool) pattern `cei|CEI|weights|coaching` in analytics_engine.py
```

---

## 2. Panel-by-panel table

Legend — **Match?** `YES` = value derives from live JSON; `NO` = hardcoded value contradicts live JSON; `N/A` = decorative/placeholder/skeleton (no live equivalent).

| # | Panel | Hardcoded value (HTML/JS) | Live JSON value (dashboard/data || root) | Match? | File:line |
|---|-------|--------------------------|-------------------------------------------|--------|-----------|
| 1 | Executive KPI — Mean Compliance | Computed from `activeReps` mean compliance_pct (69.81 / 70.03 by mode) | analytics_results `kpis.mean_compliance_rate_pct` = **69.2749** (hybrid) / **70.3442** (synthetic) | YES ~(re-derived, slight rounding diff) | tables.js:13 |
| 2 | Executive KPI — Rx Volume Growth | Computed mean lift (5.609 / 5.057) | `kpis.mean_rx_lift_pct` = **5.6445** / **5.0533** | YES ~(re-derived) | tables.js:14 |
| 3 | Executive KPI — Pearson r | Computed client-side `num/den` = 0.2865 / 0.2296 | `kpis.pearson_correlation.r` = **0.286476** / **0.2296** (p=0.0) | YES (identical formula, duplicated) | tables.js:20-30 |
| 4 | Executive KPI — Held-Out Test R² | `State.ml.best_model_summary.test_r2` + `bootstrap_ci` | ml_results hybrid **0.6215** / synth **0.6044**; CI **[0.5220,0.6979]** / **[0.5069,0.6727]** | **YES** (live) | tables.js:16-18,66-67 |
| 5 | Exec KPI badges — thresholds | `meanComp >= 80` "On Target", `testR2 >= 0.5` "Strong Fit", `meanLift/18` bar | constants (no JSON); 80 matches backend split; 18% matches documented lift bound | N/A (consistent) | tables.js:40-42,49,69 |
| 6 | Program Drivers stat grid | Grid fully rendered from `State.attribution.global_importance` (top 6) — displayed **62.6 / 31.5 / 2.0 / 1.5 / 1.2 / 1.1 %** | attribution.json global_importance hybrid = 62.61 / 31.54 / 1.99 / 1.52 / 1.15 / 1.13 (then 0.05) | **YES** (live) | tables.js:97-125, index.html:281-285 |
| 7 | Program Drivers — static subtitle text | `"Primary Driver Attribution (Tree Models Feature Importance %)"` (overwritten at runtime) | replaced live w/ model label | N/A (wired) | index.html:277, tables.js:104-107 |
| 8 | **Rep modal — weight labels** | `"Monthly Cadence (67.6% Weight)"`, `"Sample Drop Volume (24.9% Weight)"`, `"Territory Baseline Volume (3.8% Weight)"` | live attribution: cadence **62.61** (hybrid) / **66.13** (synth); samples **31.54** / **27.26**; Baseline Volume Saturation **1.15** / **0.59** | **NO — STALE (old snapshot)** | tables.js:430,434,442 |
| 9 | **Rep modal — CEI score** | `ceiScore = r.cei_score ?? 75.0` | reps.json has real `cei_score` (75.0..~89); 75.0 is only a null-fallback | YES (live when present) | tables.js:386,445 |
| 10 | Rep modal — compliance target | `targetCompPct = r.target_compliance_pct ?? 80` | reps.json `target_compliance_pct` = **80** | YES | tables.js:385 |
| 11 | Rep modal — baseline fallback | `baselineVol = r.baseline_volume ?? (hcpCount*20)` | reps.json has real `baseline_volume` | YES (fallback-only) | tables.js:381-382 |
| 12 | ML Tournament hero box / leaderboard | **None in current HTML** — the legacy static hero (RF 0.6842, CI [0.6214,0.7380], CV 0.6715±0.0210) and ranked leaderboard are **GONE**. Only live KPI card #4. | ml_results tournament rows (live) | **YES — no stale hero left** | n/a (absent); c.f. docs/AUDIT.md for the old values |
| 13 | Pipeline inspector — best model fallback | `best = isHybrid ? 'Random Forest' : 'XGBoost'` | ml_results **Random Forest** wins BOTH modes (0.6215 / 0.6044 vs XGB 0.5887 / 0.6036) | **NO — dormant fallback wrong for synthetic** | modals.js:203 |
| 14 | Pipeline inspector — best R² fallback | `isHybrid ? '0.6052' : '0.5943'` | live **0.6215** / **0.6044** | **NO — dormant/stale** | modals.js:204 |
| 15 | Pipeline inspector — suppressed fallback | `isHybrid ? 71 : 78` records suppressed | telemetry **58** (hybrid) / **123** (synthetic) | **NO — dormant/stale** | modals.js:148,160 |
| 16 | Pipeline inspector — initial_rows fallback | `tel.initial_rows ?? 820` | 820 matches hybrid; synthetic **1350** | partial — stale for synthetic | modals.js:159 |
| 17 | Pipeline inspector — retained fallback | `isHybrid ? 749 : 742` | retained **762** / **1227** | **NO — dormant/stale** | modals.js:161 |
| 18 | Pipeline inspector — exec time fallback | `'0.161' : '0.087' s` | telemetry exec = **0.093343** / **0.041329** s | **NO — dormant/stale** | modals.js:191 |
| 19 | Pipeline inspector — feature-eng weights | `cadence - 67.6%`, `sample ratio - 24.9%`, `compliance - 1.9%` | live attribution 62.61 / 31.54 / 1.99 (hybrid) | **NO — stale old snapshot** | modals.js:172-174 |
| 20 | Pipeline inspector — 7 features, 5-fold, 4 models | `7 engineered features`, `5-Fold CV`, `4 models` | ml_benchmarks metadata: n_features=7, cv_folds=5, 4 models | **YES** | modals.js:198,203; index.html:69 |
| 21 | Architecture modal — initial rows | `"820 initial HCP records"` (static HTML) | 820 = hybrid telemetry; synthetic = **1350** | **NO for synthetic mode** (static, no mode swap) | index.html:48 |
| 22 | Architecture modal — suppression rule | `"Tot_Clms ≥ 11"` | data_preprocessing.py small-cell rule | YES (text) | index.html:56 |
| 23 | Scatter chart — axis bounds | x `{min:0, max:110}`, y `{min:-4, max:20}` | live comp 0–100 (hybrid) / 20–100 (synth); lift −1.70..14.86 / −3.0..12.99 | YES (bounds contain data, static) | charts.js:179-192 |
| 24 | Scatter chart — documented domain | `"Rx_Lift_Pct bounded [−3%, +18%]"` | live min −3.0 (synth), max **14.86** (hybrid) | partial — +18% is generator cap, live max lower | index.html:298 |
| 25 | Scatter chart — OLS equation pill | slope/intercept re-derived client-side | analytics `ols_regression` slope 0.050995 / 0.03533, intercept 2.1118 / 2.5681 | YES (duplicated formula, matches) | charts.js:42-54,236-244 |
| 26 | Scatter chart — dynamic radius | `<=200 → 5.5, <=1000 → 3.5, else 2.5` | — (styling constant) | N/A | charts.js:15 |
| 27 | Matrix mode — 80/75 split thresholds | `classifyQuadrant` 80.0 (legacy) / 75.0 (CEI); subtitle "80% Compliance Split" / "75% CEI Split" | analytics_engine uses **same** 80/75 constants + median lift (live 5.4732 / 4.9272) | YES (consistent backend/frontend) | data-loader.js:73,80; filters.js:207-209; index.html:317,322 |
| 28 | Matrix quadrant count / % cards | recomputed live from `State.hcps` | matches analytics quadrant_summary distributions | YES (live) | filters.js:103-181 |
| 29 | Coaching Queue panel + "View All" modal | rendered from `State.coachingQueue` (top 5 + full list) | coaching_queue.json: hybrid **288** tasks (urgent 14 / monitor 67 / on_track 207), synthetic **350** | **YES** (live) | tables.js:127-154; modals.js:53-105; index.html:568-569 |
| 30 | Coaching task badges — priority mapping | frontend maps `urgent/monitor/on_track` → red/amber/green | coaching_queue priorities are `urgent/monitor/on_track` | YES (keys match) | tables.js:140-141; modals.js:77-80 |
| 31 | Driver-weight defaults (CEI) | `{cadence:0.676, samples:0.249, tier:0.056, compliance:0.019}` | analytics_engine.py:102 imported **identical** defaults; but live attribution importance differs (62.61…). Weights used only as fallback — reps.json `cei_score` wins. | YES vs backend (dormant)| data-loader.js:209,261,300; analytics_engine.py:102 |
| 32 | Median lift fallback | `?? 3.89` | live median = **5.4732** / **4.9272** | NO — dormant/stale (only used if no HCPs) | data-loader.js:233,285 |
| 33 | Custom-ingest fake ML results | `test_r2 0.6954`, tournament RF 0.6954 / XGB 0.6841, attribution 67.6/24.9/3.8/1.9/1.2/0.6, shap 65.2/26.1/4.5/2.1/1.4/0.7 | no live equivalent — fabricated client-side for uploaded datasets | **NO — simulated backend, not real ML** | data-loader.js:710-766 |
| 34 | Custom-ingest fake reallocation | `calls_to_add +15%`, `free −10%`, `net +5%`, `HCP↑ 35%`, `HCP↓ 25%` | used only in custom mode; live reps.json has real per-rep values | N/A (custom-only) | data-loader.js:638-642 |
| 35 | Sidebar user identity | `JD`, `John Doe`, `Provider / Analyst` | no user model in payloads | N/A (decorative) | index.html:205-208 |
| 36 | Loading placeholders / skeletons | `"Initialising analytics pipeline…"`, `"Loading…"`, skeleton tiles, `"Loading latest pipeline date…"` | overwritten at runtime (health bar, KPIs, date option) | N/A (wired placeholders) | index.html:28,241,259,341-…; app.js:28-48,70-110 |
| 37 | What-If Sandbox (causal Rx-lift formula) | **No sandbox module/HTML exists.** Only leftover `.sandbox-*` CSS + comments | n/a — feature removed | N/A (removed) | styles.css:1263-1322,1536; app.js:3 |

---

## 3. Root-cause diagnosis per mismatch

Every `NO` falls into one of three buckets. Full per-element verdict stands in §4.

**Bucket A — DORMANT STALE FALLBACKS (never displayed because live data loads):**
Rows 13–18, 20 (best model/R² for synthetic, suppressed_rows, initial_rows, retained_rows, exec time), 32 (median 3.89), 31 (weight defaults).
All of these are nullish-coalesced values: `State.telemetry[suppressed_rows] ?? 71`, etc. Live `pipeline_telemetry.json` always loads and provides **58/123** suppressed, **762/1227** retained, **0.093/0.041** s, RF-wins-both. The fallback literals still **contradict the live payload** (they mirror the *previous* run: 749/742 rows, 71/78 suppressed, 0.6052/0.5943 R²). Root cause: **constants copied from the prior data run and never refreshed.** They only surface if a future payload omits a field — at which point the dashboard would silently show numbers that disagree with the rest of the app. Classification: **never wired to a real source (hardcoded), latent risk.**

**Bucket B — STATIC TEXT LOCKED TO AN OLD ATTRIBUTION SNAPSHOT:**
Rows 8, 19 (weight labels 67.6% / 24.9% / 3.8% / 1.9%) and employment in modal/pipeline copy. Live `attribution.json` global importance today is **62.61 / 31.54 / 1.99 / 1.52 / 1.15 / 1.13 / 0.05** (hybrid). The hardcoded labels match the *old* `ml_benchmarks` snapshot (67.6/24.9/3.8/1.9/1.2/0.6) — i.e. the numbers that produced `custom`-mode fake attribution and the old docs. Root cause: **human-authored labels referencing a prior driver-importance run, not the CEI driver weights** (backend CEI weights are 0.676/0.249/0.056/0.019 — different numbers again). Result: a rep's modal shows "67.6% Weight" while the top driver tile on the same page shows 62.6%. Classification: **never wired — static copy.**

**Bucket C — STATIC HTML, MODE-UNAWARE:**
Rows 21 (Architecture modal "820 initial HCP records"). Static HTML in index.html — correct for **hybrid** telemetry (820 initial) but wrong for **synthetic** (1350). No JS swaps this text per mode (only the pipeline-inspector below it is live). Classification: **never wired.**

**Bucket D — FABRICATED BACKEND ("backend module doesn't exist yet"):**
Rows 33–34. `processCustomDataset` (data-loader.js:710-766) **fabricates** ML metrics (test_r2 0.6954), a 2-model tournament, attribution (67.6/24.9/3.8/…) and SHAP values client-side — no Python pipeline runs on the uploaded CSV/Parquet/JSON. The `/data` reveal: these numbers match the old hardcoded snapshot, i.e. they are canned, not derived from the upload. Classification: **backend module doesn't exist yet** (front-end simulation masquerading as results).

---

## 4. Per-panel verdicts

| Panel | Verdict |
|-------|---------|
| Program Drivers / attribution stat grid | **WIRED** — fully rendered from live `attribution.json`. (Static subtitle is overwritten.) |
| ML Tournament hero + leaderboard | **N/A — no hardcoded hero remains.** KPI card #4 is live. Old values from docs/AUDIT.md fully removed. |
| Today's Tasks / Coaching Queue | **WIRED** — rendered from live `coaching_queue.json` (288/350 tasks). Priority plumbing consistent. |
| Rep modal driver-weight labels (67.6/24.9/3.8%) | **NEVER WIRED** — static copy from old attribution snapshot; disagrees with live drivers on the same page. |
| Pipeline inspector telemetry fallbacks | **WIRED-but-latent-broken** — primary values live; fallback constants (Rows 13–18) stale and contradict live telemetry if ever hit. |
| Architecture modal "820 initial HCP records" | **NEVER WIRED** — static HTML correct for hybrid only; wrong for synthetic (1350). |
| Chart axis bounds / radius / domain text | **N/A — static but consistent** (bounds contain live data; +18% is generator cap). |
| Thresholds 80% / 75% / median-lift | **WIRED-consistent** — identical constants on backend (analytics_engine) and frontend; median lift computed live (5.4732 / 4.9272). |
| Custom dataset ingestion "results" | **BACKEND MODULE DOESN'T EXIST YET** — ML/attribution/SHAP numbers fabricated client-side; not computed from the uploaded file. |
| Duplicated formulas (Pearson r, OLS) | **WIRED-consistent** — re-derived client-side; numerically matches analytics_results KPIs (0.2865 vs 0.286476 etc). |
| What-If Sandbox | **REMOVED** — no sandbox.js/HTML; leftover `.sandbox-*` CSS + comment references only. |
| Sidebar user + loading placeholders | **N/A** — decorative / always-overwritten. |

---

## 5. coaching_queue.json provenance (requested check)

**coaching_queue.json IS generated by a Python module — it is NOT hand-authored and NOT a one-off.**

- **Generator:** `src/export/build_dashboard_data.py`
  - `def build_coaching_queue_data(reps_data)` **line 348** — deterministic rule-based task builder (CADENCE_DEFICIT / SAMPLE_RATIO_DEFICIT / EFFICIENCY_SCALING / TOP_PERFORMER / TARGETING_REFINEMENT / DETAILING_QUALITY), thresholds baked in at lines 359/372/383/394 (lift <2.5, ≥4.5, 2.5–4.5 — identical to `tables.js`/`data-loader.js` coaching thresholds, rows 29–30).
  - Called at **lines 505–506** (`coaching_queue_hybrid` from `reps_hybrid`, `coaching_queue_synth` from `reps_synth`).
  - Serialized into the payload dict at **lines 549–554** (`data`, `hybrid`, `synthetic` keys) and written to `dashboard/data/coaching_queue.json` at **lines 587–592** (with SHA-256 registered in `manifest.json`).
- **Input chain:** `reps_hybrid/synth` come from `build_reps_data(analytics_results.json[hybrid|synthetic] rep_scorecards, processed parquet)` (lines 499–500, 132–160). So the queue is ultimately derived from `analytics_engine.py` rep scorecards → not hand-authored.
- **Where it does NOT come from:** there is **no** `src/metrics/*.py` (directory does not exist) and no dedicated "coaching module". Grep across `src/**` finds `coaching_queue` only in `build_dashboard_data.py`. The queue logic lives in the **export layer**, not the analytics pipeline.
- **Consistency check with test suite:** `tests/test_export.py` (9 tests) validates `coaching_queue.json` against `schema/dashboard_data_contract.json` (build_dashboard_data.py:578). Playwright spec asserts the panel renders tasks. Both passed in Phase 1 (13/13 pytest, 11/11 e2e).
- **Caveat:** the queue is always 1 task per rep = **288 hybrid / 350 synthetic** tasks; priority distribution (14 urgent / 67 monitor / 207 on_track hybrid) is a deterministic function of the rule set, not of a separate severity model.

---

## 6. Summary of required fixes (deferred — not applied)

1. Remove / refresh the dormant pipeline-inspector fallbacks (modals.js:148,159–161,191,203–204) so fallback literals match current telemetry, or drop them entirely.
2. Rewrite the static weight labels in the rep modal (tables.js:430,434,442) to read from live `attribution.json` (or remove the % entirely).
3. Make the Architecture-modal "820 initial HCP records" text mode-aware (read `initial_rows` from live telemetry per mode).
4. Replace fabricated custom-ingest ML/attribution/SHAP/results (data-loader.js:710–766) with a real backend step, or visibly label them as simulated.
5. Cosmetic: `mediaLift ?? 3.89` fallback (data-loader.js:233,285) is stale vs live medians.