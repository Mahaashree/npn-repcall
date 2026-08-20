/**
 * js/charts.js
 * Chart.js scatter plot with dynamic radius scaling, feature importance bar charts, and SHAP charts.
 */

/* global Chart */

import { State, normQuadrant } from './data-loader.js';

export function renderScatter() {
  const hcps = State.filteredHcps;
  const totalCount = hcps.length;
  const isCei = State.matrixMode === 'cei';

  const dynamicRadius = totalCount <= 200 ? 5.5 : totalCount <= 1000 ? 3.5 : 2.5;

  const quad = isCei
    ? { 'Star Performers': [], 'Targeting Risk': [], 'Efficient High-Performers': [], 'Needs Intervention': [] }
    : { 'Star Performers': [], 'Efficiency Risk': [], 'Unrealized Potential': [], 'Needs Intervention': [] };

  hcps.forEach((h) => {
    const x = isCei ? (h.cei_score ?? 75.0) : (h.Compliance_Pct_raw ?? h.Compliance_Pct ?? 0);
    const y = h.Rx_Lift_Pct ?? 0;
    const q = normQuadrant(h._quadrant, State.matrixMode);
    if (quad[q])
      quad[q].push({
        x,
        y,
        label: h.Physician_Name ?? h.Prscrbr_NPI,
        npi: h.Prscrbr_NPI,
        rep: h.Sales_Rep,
        tier: h.HCP_Tier,
        comp: h.Compliance_Pct_raw ?? h.Compliance_Pct ?? 0,
        cei: h.cei_score ?? x,
        lift: y,
      });
  });

  const xVals = hcps.map((h) => (isCei ? (h.cei_score ?? 75.0) : (h.Compliance_Pct_raw ?? 0)));
  const yVals = hcps.map((h) => h.Rx_Lift_Pct ?? 0);
  const n = xVals.length || 1;
  const sumX = xVals.reduce((a, b) => a + b, 0);
  const sumY = yVals.reduce((a, b) => a + b, 0);
  const sumXY = xVals.reduce((a, b, i) => a + b * yVals[i], 0);
  const sumX2 = xVals.reduce((a, b) => a + b * b, 0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX || 1);
  const intercept = (sumY - slope * sumX) / n;

  const xMin = Math.min(...xVals, 0);
  const xMax = Math.max(...xVals, 100);
  const regLine = [
    { x: xMin, y: slope * xMin + intercept },
    { x: xMax, y: slope * xMax + intercept },
  ];

  const datasets = isCei
    ? [
        {
          label: '⭐ Star Performers',
          data: quad['Star Performers'],
          backgroundColor: 'rgba(16, 185, 129, 0.95)',
          borderColor: '#059669',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '🟡 Targeting Risk',
          data: quad['Targeting Risk'],
          backgroundColor: 'rgba(245, 158, 11, 0.95)',
          borderColor: '#d97706',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '⚡ Efficient High-Performers',
          data: quad['Efficient High-Performers'],
          backgroundColor: 'rgba(6, 182, 212, 0.95)',
          borderColor: '#0284c7',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '🔴 Needs Intervention',
          data: quad['Needs Intervention'],
          backgroundColor: 'rgba(239, 68, 68, 0.95)',
          borderColor: '#dc2626',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: 'OLS Fit',
          data: regLine,
          type: 'line',
          borderColor: 'var(--primary)',
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ]
    : [
        {
          label: '⭐ Star Performers',
          data: quad['Star Performers'],
          backgroundColor: 'rgba(16, 185, 129, 0.95)',
          borderColor: '#059669',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '🟡 Efficiency Risk',
          data: quad['Efficiency Risk'],
          backgroundColor: 'rgba(245, 158, 11, 0.95)',
          borderColor: '#d97706',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '🔵 Unrealized Potential',
          data: quad['Unrealized Potential'],
          backgroundColor: 'rgba(6, 182, 212, 0.95)',
          borderColor: '#0284c7',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: '🔴 Needs Intervention',
          data: quad['Needs Intervention'],
          backgroundColor: 'rgba(239, 68, 68, 0.95)',
          borderColor: '#dc2626',
          borderWidth: 0.5,
          pointRadius: dynamicRadius,
          pointHoverRadius: dynamicRadius + 2.5,
        },
        {
          label: 'OLS Fit',
          data: regLine,
          type: 'line',
          borderColor: 'var(--primary)',
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0,
        },
      ];

  if (State.scatterChart) State.scatterChart.destroy();
  const canvas = document.getElementById('scatter-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  State.scatterChart = new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: totalCount > 1000 ? 0 : 300 },
      scales: {
        x: {
          title: {
            display: true,
            text: isCei
              ? `AI Composite Execution Index (CEI %) — ${totalCount} HCPs`
              : `Call Plan Compliance (%) — ${totalCount} HCPs`,
            color: 'var(--text-muted)',
            font: { size: 11 },
          },
          grid: { color: 'rgba(226,232,240,0.6)' },
          ticks: { color: 'var(--text-muted)' },
          min: 0,
          max: 110,
        },
        y: {
          title: {
            display: true,
            text: 'Rx Lift % (Bounded −3% to +18%)',
            color: 'var(--text-muted)',
            font: { size: 11 },
          },
          grid: { color: 'rgba(226,232,240,0.6)' },
          ticks: { color: 'var(--text-muted)' },
          min: -4,
          max: 20,
        },
      },
      plugins: {
        legend: {
          labels: {
            color: 'var(--text-secondary)',
            font: { size: 11 },
            padding: 16,
            filter: (item) => item.datasetIndex < 4,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              if (d.label == null) return `Rx Lift: ${d.y.toFixed(2)}%`;
              return isCei
                ? [
                    `${d.label}`,
                    `NPI: ${d.npi}`,
                    `Rep: ${d.rep}`,
                    `CEI Score: ${d.cei?.toFixed(1) ?? d.x.toFixed(1)}%`,
                    `Rx Lift: ${d.lift.toFixed(3)}%`,
                    `Tier: ${d.tier}`,
                  ]
                : [
                    `${d.label}`,
                    `NPI: ${d.npi}`,
                    `Rep: ${d.rep}`,
                    `Compliance: ${d.comp?.toFixed(1) ?? d.x.toFixed(1)}%`,
                    `Rx Lift: ${d.lift.toFixed(3)}%`,
                    `Tier: ${d.tier}`,
                  ];
            },
          },
          backgroundColor: 'rgba(15,23,42,0.96)',
          titleColor: '#ffffff',
          bodyColor: 'var(--text-secondary)',
          borderColor: 'var(--border)',
          borderWidth: 1,
          padding: 10,
        },
      },
    },
  });

  const pill = document.getElementById('equation-pill');
  if (pill) {
    pill.textContent = isCei
      ? `Rx_Lift_Pct = ${slope.toFixed(4)} × CEI% + ${intercept.toFixed(4)}`
      : `Rx_Lift_Pct = ${slope.toFixed(4)} × Compliance% + ${intercept.toFixed(4)}`;
  }
}
