# CLEANUP_LOG.md — Phase 2 archive

**Date:** 2026-08-19
**Repo:** `/Users/mahaashreeanburaj/Downloads/cts(3 modes)` — pharma sales-ops analytics POC.
**Operation:** `git mv` only — no contents modified, history preserved, moves reversible. Live files (all `*.parquet` raw/processed per-mode, `pipeline_telemetry{,_hybrid,_synthetic}.json`, `analytics_results.json`, `ml_benchmarks.json`, `crm_call_activity.csv`, `data/rep_master.csv`, `data/doctor_master.csv`, `dashboard/data/*`, `netlify.toml`, `frontend/*`, `src/*`, `tests/*`) were **not** touched.
**Pre-move re-verification:** each file was re-grepped (`grep -rn --include="*.py" --include="*.js"`) immediately before moving. Only the pipeline **write** calls reference these files (all reproducible per run); zero downstream reads. `data/output/*` has no source refs at all.

## Files moved to `_archive/pipeline_runs/`

| Original path | New path | Justification |
|---|---|---|
| `synthetic_crm_dataset.csv` | `_archive/pipeline_runs/synthetic_crm_dataset.csv` | orphan — no code reference |
| `processed_data_hybrid.csv` | `_archive/pipeline_runs/processed_data_hybrid.csv` | write-only mirror of the canonical hybrid parquet |
| `processed_data_synthetic.csv` | `_archive/pipeline_runs/processed_data_synthetic.csv` | write-only mirror of the canonical synthetic parquet |
| `processed_data_hybrid.json` | `_archive/pipeline_runs/processed_data_hybrid.json` | write-only debug dump |
| `processed_data_synthetic.json` | `_archive/pipeline_runs/processed_data_synthetic.json` | write-only debug dump |
| `raw_crm_cms_dataset_hybrid.csv` | `_archive/pipeline_runs/raw_crm_cms_dataset_hybrid.csv` | write-only mirror of the raw hybrid parquet |
| `raw_crm_cms_dataset_synthetic.csv` | `_archive/pipeline_runs/raw_crm_cms_dataset_synthetic.csv` | write-only mirror of the raw synthetic parquet |
| `raw_crm_cms_dataset.csv` | `_archive/pipeline_runs/raw_crm_cms_dataset.csv` | write-only mirror (hybrid alias) |
| `ml_benchmarks_hybrid.json` | `_archive/pipeline_runs/ml_benchmarks_hybrid.json` | write-only, reproducible per run (keep combined `ml_benchmarks.json`) |
| `ml_benchmarks_synthetic.json` | `_archive/pipeline_runs/ml_benchmarks_synthetic.json` | write-only, reproducible per run (keep combined `ml_benchmarks.json`) |
| `data/output/analytics_results.json` | `_archive/pipeline_runs/data_output/analytics_results.json` | orphan — legacy output dir, no code refs |
| `data/output/ml_benchmarks.json` | `_archive/pipeline_runs/data_output/ml_benchmarks.json` | orphan — legacy output dir, no code refs |
| `data/output/pipeline_telemetry.json` | `_archive/pipeline_runs/data_output/pipeline_telemetry.json` | orphan — legacy output dir, no code refs |
| `data/output/processed_data.parquet` | `_archive/pipeline_runs/data_output/processed_data.parquet` | orphan — legacy output dir, no code refs |
| `data/output/processed_data.json` | `_archive/pipeline_runs/data_output/processed_data.json` | orphan — legacy output dir, no code refs |
| `data/output/raw_crm_cms_dataset.parquet` | `_archive/pipeline_runs/data_output/raw_crm_cms_dataset.parquet` | orphan — legacy output dir, no code refs |
| `data/output/synthetic_crm_dataset.parquet` | `_archive/pipeline_runs/data_output/synthetic_crm_dataset.parquet` | orphan — legacy output dir, no code refs |

## Files moved to `_archive/deploy_configs/`

| Original path | New path | Justification |
|---|---|---|
| `Dockerfile` | `_archive/deploy_configs/Dockerfile` | non-canonical deploy config — Netlify is the confirmed target (also had a confirmed root-path `COPY` bug) |
| `nginx.conf` | `_archive/deploy_configs/nginx.conf` | non-canonical deploy config — only meaningful for the rejected Docker target |
| `vercel.json` | `_archive/deploy_configs/vercel.json` | non-canonical deploy config — Netlify is the confirmed target |

**Not moved:** `netlify.toml` (live config, left in place at repo root).

## Verification after moves

- `pytest` (cts-venv): **13 passed**
- Playwright e2e (temp install, port 8091): **11 passed**

## Notes

- Files that were untracked at move time (all `_hybrid/_synthetic` mirrors/debug dumps, `synthetic_crm_dataset.csv`) were staged (`git add`) then moved with `git mv` so the relocation is recorded in the index.
- **Staged only — not committed.** Awaiting review before commit.
