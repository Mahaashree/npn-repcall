#!/usr/bin/env python3
"""
scripts/generate_ppt_charts.py
==============================
Generate high-resolution (300 DPI) presentation charts from REAL current
pipeline output. Read-only: reads JSON/parquet artifacts in data/generated/
and dashboard/data/, writes PNGs to docs/ppt_charts/.

Charts:
  01_model_comparison_r2.png      Test R^2, 4 models, hybrid vs synthetic
  02_cv_score_stability.png       CV R^2 mean w/ std error bars, both modes
  03_overfitting_gap.png          Train vs Test R^2 per model, both modes
  04_predicted_vs_actual.png      Best-model regression diagnostic (y=x) per mode
  05_bootstrap_ci.png             Test R^2 point estimate + 95% CI, both modes
  06_feature_importance.png       Top features, best model, both modes
  07_compliance_vs_lift_scatter.png  Compliance vs Rx Lift w/ OLS trendline + Pearson r
  08_rx_lift_distribution.png     Histogram, both modes, mean/std annotated
  09_quadrant_distribution.png    HCP counts per 2x2 business quadrant, both modes

Run with the project venv (full ML stack):
    venv/bin/python scripts/generate_ppt_charts.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats as sp_stats
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Import must come after sys.path setup (isort/E402 suppressed).
from src.models.ml_models_suite import build_feature_matrix  # noqa: E402

ANALYTICS_DIR = BASE_DIR / "data" / "generated" / "analytics"
PROCESSED_DIR = BASE_DIR / "data" / "generated" / "processed"
ARTIFACTS_DIR = BASE_DIR / "src" / "models" / "artifacts"
DASHBOARD_DIR = BASE_DIR / "dashboard" / "data"
OUT_DIR = BASE_DIR / "docs" / "ppt_charts"

MODES = ["hybrid", "synthetic"]
SEED = 42  # matches ml_models_suite.py

# Dashboard palette (frontend/styles.css `:root` tokens) for visual consistency.
TEAL = "#0d9488"
TEAL_DARK = "#115e59"
AMBER = "#f59e0b"
AMBER_DARK = "#b45309"
GREEN = "#10b981"
RED = "#ef4444"
BLUE = "#3b82f6"
PURPLE = "#8b5cf6"
SLATE = "#0f172a"
GRID = "#e2e8f0"

MODEL_COLORS = {
    "Random Forest Regressor": TEAL,
    "Gradient Boosting Regressor": BLUE,
    "OLS Linear Regression": AMBER,
    "Ridge Regression (L2, a=1.0)": PURPLE,
}
MODEL_FAMILIES = {
    "Random Forest Regressor": "Ensemble",
    "Gradient Boosting Regressor": "Gradient Boosting",
    "OLS Linear Regression": "Linear",
    "Ridge Regression (L2, a=1.0)": "Linear",
}
MODE_COLORS = {"hybrid": TEAL, "synthetic": AMBER}

REPORT = []


def log(msg: str) -> None:
    print(msg)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def load_benchmarks(mode: str) -> dict:
    with open(ANALYTICS_DIR / f"ml_benchmarks_{mode}.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_best_model_importance(mode: str) -> list[dict]:
    """Top features for the best model in each mode (global importance)."""
    data = load_benchmarks(mode)
    best_label = data["best_model_summary"]["model_label"]
    for entry in data["benchmarks"]:
        if entry["model_label"] == best_label:
            fi = entry.get("feature_importance", {})
            ranked = fi.get("global_importance_ranked") or fi.get("shap_importance_ranked")
            if ranked:
                return ranked
    return []


def load_quadrant_counts(mode: str) -> dict:
    with open(DASHBOARD_DIR / "scatter_points.json", encoding="utf-8") as fh:
        sc = json.load(fh)
    counts: dict[str, int] = {}
    for p in sc[mode]:
        q = str(p.get("quadrant", "Unknown"))
        counts[q] = counts.get(q, 0) + 1
    return counts


def load_processed(mode: str) -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / f"processed_data_{mode}.parquet")


def predicted_vs_actual_data(mode: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Reproduce the exact train/test partition from ml_models_suite (SEED=42,
    test_size=0.20), score with the persisted best model, return (y_test, preds).
    """
    df = load_processed(mode)
    X, _, df_out = build_feature_matrix(df)
    y = df_out["Rx_Lift_Pct"].astype(float).values
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.20, random_state=SEED)
    model = joblib.load(ARTIFACTS_DIR / f"best_{mode}.joblib")
    preds = model.predict(X_test)
    return y_test, preds


# ---------------------------------------------------------------------------
# Shared cosmetics
# ---------------------------------------------------------------------------
sns.set_theme(style="whitegrid", context="paper")
plt.rcParams.update(
    {
        "font.size": 14,
        "axes.titlesize": 18,
        "axes.labelsize": 15,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "figure.dpi": 300,
    }
)


def tidy_ax(ax, ymax=None):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(color=SLATE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if ymax is not None:
        ax.set_ylim(0, ymax)


def write_fig(fig, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  wrote {path.name}")


def short_label(name: str) -> str:
    return name.replace("Regressor", "Reg").replace(" (L2, a=1.0)", "")


# ---------------------------------------------------------------------------
# Chart 01 — Test R^2 comparison
# ---------------------------------------------------------------------------
def chart_01() -> None:
    log("01_model_comparison_r2")
    benches = {m: load_benchmarks(m)["tournament_table"] for m in MODES}
    models = [b["model_label"] for b in benches["hybrid"]]
    x = np.arange(len(models))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))
    for i, (mode, col) in enumerate(MODE_COLORS.items()):
        vals = [next(b["test_r2"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        offset = (i - 0.5) * width
        rects = ax.bar(x + offset, vals, width, label=f"{mode.title()} mode", color=col,
                       edgecolor="white", linewidth=0.6)
        for r, v in zip(rects, vals):
            ax.text(r.get_x() + r.get_width() / 2, v + 0.01, f"{v:.3f}",
                    ha="center", va="bottom", fontsize=11)

    ax.set_xticks(x)
    ax.set_xticklabels([short_label(m) for m in models])
    ax.set_ylabel("Test R² (held-out test set)")
    ax.set_title("Model Comparison — Test R², Rx-Lift Regression")
    tidy_ax(ax, ymax=max(max(next(b["test_r2"] for b in benches[m]) for m in MODES) + 0.12, 0.75))
    ax.legend(loc="upper left", frameon=False)
    write_fig(fig, "01_model_comparison_r2.png")
    REPORT.append(("01", "Test R²", {m: [next(b["test_r2"] for b in benches[m]) for b in [] ] if False else [(b["model_label"], b["test_r2"]) for b in benches[m]] for m in MODES}))


# ---------------------------------------------------------------------------
# Chart 02 — CV score stability
# ---------------------------------------------------------------------------
def chart_02() -> None:
    log("02_cv_score_stability")
    benches = {m: load_benchmarks(m)["tournament_table"] for m in MODES}
    models = [b["model_label"] for b in benches["hybrid"]]
    x = np.arange(len(models))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))
    for i, (mode, col) in enumerate(MODE_COLORS.items()):
        cv = [next(b["cv_mean_r2"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        sd = [next(b["cv_std_r2"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        offset = (i - 0.5) * width
        ax.bar(x + offset, cv, width, yerr=sd, capsize=4, color=col, edgecolor="white",
               linewidth=0.6, label=f"{mode.title()} mode", error_kw=dict(lw=1.2, ecolor=SLATE))

    ax.set_xticks(x)
    ax.set_xticklabels([short_label(m) for m in models])
    ax.set_ylabel("5-fold CV R² (mean ± std)")
    ax.set_title("Cross-Validation Score Stability")
    tidy_ax(ax, ymax=0.85)
    ax.legend(loc="upper left", frameon=False)
    write_fig(fig, "02_cv_score_stability.png")
    REPORT.append(("02", "CV R² ±std", {m: [(b["model_label"], b["cv_mean_r2"], b["cv_std_r2"]) for b in benches[m]] for m in MODES}))


# ---------------------------------------------------------------------------
# Chart 03 — Overfitting gap
# ---------------------------------------------------------------------------
def chart_03() -> None:
    log("03_overfitting_gap")
    benches = {m: load_benchmarks(m)["tournament_table"] for m in MODES}
    models = [b["model_label"] for b in benches["hybrid"]]
    n = len(models)
    x = np.arange(n)
    width = 0.20

    fig, ax = plt.subplots(figsize=(13, 6.5))
    gap_cols = {"hybrid": [TEAL, AMBER], "synthetic": [BLUE, RED]}
    slot = 0
    for mode in MODES:
        for j, metric in enumerate(("in_sample_train_r2", "test_r2")):
            vals = [next(b[metric] for b in benches[mode] if b["model_label"] == ml) for ml in models]
            offset = (slot - (2 * 2 - 1) / 2) * width
            ax.bar(x + offset, vals, width,
                   label=f"{mode.title()} · {'Train' if j == 0 else 'Test'} R²",
                   color=gap_cols[mode][j], edgecolor="white", linewidth=0.6)
            slot += 1
    ax.set_xticks(x)
    ax.set_xticklabels([short_label(m) for m in models])
    ax.set_ylabel("R²")
    ax.set_title("Generalization Gap — Train vs Test R² per model, both modes")
    tidy_ax(ax, ymax=0.95)
    ax.legend(loc="upper left", frameon=False, ncol=2)
    write_fig(fig, "03_overfitting_gap.png")
    REPORT.append(("03", "Overfit gap", {m: {b["model_label"]: round(b["in_sample_train_r2"] - b["test_r2"], 4) for b in benches[m]} for m in MODES}))


# ---------------------------------------------------------------------------
# Chart 04 — Predicted vs actual (regression diagnostic)
# ---------------------------------------------------------------------------
def chart_04() -> None:
    log("04_predicted_vs_actual")
    best_labels = {}
    r2s = {}
    for mode in MODES:
        b = load_benchmarks(mode)
        best_labels[mode] = b["best_model_summary"]["model_label"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=False, sharey=False)
    for ax, mode in zip(axes, MODES):
        y_test, preds = predicted_vs_actual_data(mode)

        r2 = r2_score(y_test, preds)
        r2s[mode] = round(float(r2), 4)
        ax.scatter(y_test, preds, s=22, alpha=0.55, color=MODE_COLORS[mode], edgecolor="none")
        lo = min(y_test.min(), preds.min())
        hi = max(y_test.max(), preds.max())
        ax.plot([lo, hi], [lo, hi], "--", color=SLATE, lw=1.6, label="y = x (perfect fit)")
        # OLS fit for reference line
        slope, intercept, rv, pv, se = sp_stats.linregress(y_test, preds)
        xs = np.linspace(lo, hi, 100)
        ax.plot(xs, intercept + slope * xs, "-", color=RED, lw=1.4,
                label=f"OLS fit (slope={slope:.2f})")
        ax.text(0.03, 0.94, f"Test R² = {r2:.3f}\nPearson r = {rv:.3f}",
                transform=ax.transAxes, fontsize=13,
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID))
        ax.set_xlabel("Actual Rx Lift (%)")
        ax.set_ylabel("Predicted Rx Lift (%)")
        ax.set_title(f"{best_labels[mode]} — {mode.title()}\n(held-out test set)", fontsize=13)
        ax.legend(loc="lower right", frameon=False, fontsize=11)

    fig.suptitle("Predicted vs Actual Rx-Lift — regression diagnostic\n(regression analog of a confusion matrix)",
                 fontsize=18, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    write_fig(fig, "04_predicted_vs_actual.png")
    REPORT.append(("04", "Pred-vs-actual test R²", r2s))


# ---------------------------------------------------------------------------
# Chart 05 — Bootstrap CI for test R²
# ---------------------------------------------------------------------------
def chart_05() -> None:
    log("05_bootstrap_ci")
    benches = {m: load_benchmarks(m)["tournament_table"] for m in MODES}
    models = [b["model_label"] for b in benches["hybrid"]]
    x = np.arange(len(models))
    width = 0.36

    fig, ax = plt.subplots(figsize=(11, 6))
    for i, (mode, col) in enumerate(MODE_COLORS.items()):
        pts = [next(b["test_r2"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        lo = [next(b["bootstrap_ci_lower"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        hi = [next(b["bootstrap_ci_upper"] for b in benches[mode] if b["model_label"] == ml) for ml in models]
        err = [[pts[j] - lo[j] for j in range(len(pts))], [hi[j] - pts[j] for j in range(len(pts))]]
        offset = (i - 0.5) * width
        ax.errorbar(x + offset, pts, yerr=err, fmt="o", color=col, ms=9, capsize=5,
                    capthick=1.5, lw=1.8, label=f"{mode.title()} mode",
                    markeredgecolor="white")

    ax.axhline(0.0, color=SLATE, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([short_label(m) for m in models])
    ax.set_ylabel("Test R² (point ± 95% bootstrap CI)")
    ax.set_title("Test R² with Bootstrap 95% Confidence Intervals (1000 samples)")
    tidy_ax(ax, ymax=0.85)
    ax.legend(loc="upper left", frameon=False)
    write_fig(fig, "05_bootstrap_ci.png")
    REPORT.append(("05", "CI", {m: [(b["model_label"], b["test_r2"], b["bootstrap_ci_lower"], b["bootstrap_ci_upper"]) for b in benches[m]] for m in MODES}))


# ---------------------------------------------------------------------------
# Chart 06 — Feature importance
# ---------------------------------------------------------------------------
def chart_06() -> None:
    log("06_feature_importance")
    imp = {m: load_best_model_importance(m) for m in MODES}

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax, mode in zip(axes, MODES):
        ranked = imp[mode]
        if not ranked:
            ax.text(0.5, 0.5, "No importance data", ha="center", transform=ax.transAxes)
            continue
        rows = ranked[:7]
        feats = [r["feature"].replace("_raw", "") for r in rows]
        vals = [r["importance_pct"] for r in rows]
        order = np.argsort(vals)
        ax.barh([feats[i] for i in order], [vals[i] for i in order],
                color=MODE_COLORS[mode], edgecolor="white")
        for ypos, v in zip(range(len(order)), [vals[i] for i in order]):
            ax.text(v + 0.5, ypos, f"{v:.1f}%", va="center", fontsize=12)
        ax.set_title(f"{mode.title()} mode —{''}{' Random Forest' if False else ''} feature importance")
        ax.set_xlabel("Importance (%)")
        ax.invert_yaxis()

    fig.suptitle("Top Predictive Features (best-model global importance)",
                 fontsize=18, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    write_fig(fig, "06_feature_importance.png")
    REPORT.append(("06", "Importance", {m: (imp[m][0]["feature"] if imp[m] else None, imp[m][0]["importance_pct"] if imp[m] else None) for m in MODES}))


# ---------------------------------------------------------------------------
# Chart 07 — Compliance vs lift scatter
# ---------------------------------------------------------------------------
def chart_07() -> None:
    log("07_compliance_vs_lift_scatter")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, mode in zip(axes, MODES):
        df = load_processed(mode)
        x = df["Compliance_Pct_raw"].astype(float)
        y = df["Rx_Lift_Pct"].astype(float)
        ax.scatter(x, y, s=22, alpha=0.5, color=MODE_COLORS[mode], edgecolor="none")
        slope, intercept, r, p, se = sp_stats.linregress(x, y)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, intercept + slope * xs, "-", color=RED, lw=2.2, label=f"OLS (r={r:.3f})")
        ax.text(0.03, 0.94, f"Pearson r = {r:.3f}\n(p = {p:.2e})",
                transform=ax.transAxes, fontsize=13,
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID))
        ax.set_xlabel("Call-plan compliance (%)")
        ax.set_ylabel("Rx Lift (%)")
        ax.set_title(f"{mode.title()} mode (n={len(df)})")
        ax.legend(loc="lower right", frameon=False, fontsize=11)

    fig.suptitle("Compliance vs Rx-Lift — OLS trendline with Pearson correlation",
                 fontsize=18, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    write_fig(fig, "07_compliance_vs_lift_scatter.png")
    for mode in MODES:
        df = load_processed(mode)
        r = sp_stats.linregress(df["Compliance_Pct_raw"].astype(float), df["Rx_Lift_Pct"].astype(float))
        REPORT.append(("07", f"Pearson {mode}", round(r.rvalue, 4)))


# ---------------------------------------------------------------------------
# Chart 08 — Rx lift distribution
# ---------------------------------------------------------------------------
def chart_08() -> None:
    log("08_rx_lift_distribution")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, mode in zip(axes, MODES):
        df = load_processed(mode)
        vals = df["Rx_Lift_Pct"].astype(float)
        sns.histplot(vals, bins=40, color=MODE_COLORS[mode], ax=ax, edgecolor="white",
                     alpha=0.85, stat="density")
        ax.axvline(vals.mean(), color=RED, lw=2, ls="--",
                   label=f"mean = {vals.mean():.2f}%")
        ax.axvline(vals.mean() - vals.std(), color=SLATE, lw=1.2, ls=":",
                   label=f"±1σ = {vals.std():.2f}")
        ax.axvline(vals.mean() + vals.std(), color=SLATE, lw=1.2, ls=":")
        ax.set_title(f"{mode.title()} mode\nn={len(vals)}, σ={vals.std():.2f}", fontsize=14)
        ax.set_xlabel("Rx Lift (%)")
        ax.legend(loc="upper right", frameon=False, fontsize=11)

    fig.suptitle("Distribution of Rx-Lift — synthetic campaign effect",
                 fontsize=18, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    write_fig(fig, "08_rx_lift_distribution.png")
    for mode in MODES:
        vals = load_processed(mode)["Rx_Lift_Pct"].astype(float)
        REPORT.append(("08", f"Lift {mode}", {"mean": round(vals.mean(), 3), "std": round(vals.std(), 3)}))


# ---------------------------------------------------------------------------
# Chart 09 — Quadrant distribution (business segmentation)
# ---------------------------------------------------------------------------
def chart_09() -> None:
    log("09_quadrant_distribution")
    counts = {m: load_quadrant_counts(m) for m in MODES}
    all_q = list(dict.fromkeys(list(counts["hybrid"].keys()) + list(counts["synthetic"].keys())))
    order = ["Star Performers", "Efficiency Risk", "Unrealized Potential", "Needs Intervention"]
    ordered = [q for q in order if q in all_q] + [q for q in all_q if q not in order]

    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(ordered))
    width = 0.36
    for i, (mode, col) in enumerate(MODE_COLORS.items()):
        vals = [counts[mode].get(q, 0) for q in ordered]
        offset = (i - 0.5) * width
        rects = ax.bar(x + offset, vals, width, label=f"{mode.title()} mode ({sum(vals):,} HCPs)",
                       color=col, edgecolor="white", linewidth=0.6)
        for r, v in zip(rects, vals):
            ax.text(r.get_x() + r.get_width() / 2, v + max(int(sum(vals) * 0.012), 2),
                    f"{v:,}", ha="center", fontsize=11)

    ax.set_xticks(x)
    ax.set_xticklabels(ordered, rotation=12, ha="right")
    ax.set_ylabel("HCP count")
    ax.set_title("HCP Segmentation Per 2×2 Business Quadrant\n(compliance × lift segmentation — NOT a confusion matrix)")
    tidy_ax(ax, ymax=max(max(counts[m][q] for m in MODES) for q in ordered) * 1.12)
    ax.legend(loc="upper right", frameon=False)
    write_fig(fig, "09_quadrant_distribution.png")
    REPORT.append(("09", "Quadrants", {m: counts[m] for m in MODES}))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Output dir: {OUT_DIR}")
    for fn in [chart_01, chart_02, chart_03, chart_04, chart_05, chart_06, chart_07, chart_08, chart_09]:
        fn()
    log("\n=== Summary of values plotted (from live artifacts) ===")
    for num, label, payload in REPORT:
        log(f"[{num}] {label}")
        log(f"      {payload}")
    log("\nDone. Charts written to docs/ppt_charts/")


if __name__ == "__main__":
    main()