/**
 * app.js — Pharma Analytics Platform Main Entry Point (ES Module)
 * Orchestrates modular components across data loading, charts, tables, filters, modals, and sandbox.
 */

import { State, loadAllData } from './data-loader.js';
import { renderScatter } from './charts.js';
import {
  renderKPIs,
  renderProgramDrivers,
  renderCoachingQueuePanel,
  renderRepTab,
  renderManagerTab,
  renderPrescribersTab,
  openRepModal,
  bindTabs,
  bindExports,
} from './tables.js';
import { populateFilters, renderPerformanceMatrix, bindFilters, initScrollspy } from './filters.js';
import { bindModals, renderPipelineInspector, openModal, closeModal } from './modals.js';

// Expose modal functions on window for inline HTML onclick attributes
window.openRepModal = openRepModal;
window.openModal = openModal;
window.closeModal = closeModal;

function renderSkeletons() {
  const kpiGrid = document.getElementById('kpi-grid');
  if (kpiGrid) {
    kpiGrid.innerHTML = Array(4)
      .fill(0)
      .map(
        () => `
      <div class="kpi-card">
        <div style="background:var(--bg-hover);height:14px;width:60%;border-radius:4px;margin-bottom:0.5rem"></div>
        <div style="background:var(--bg-hover);height:28px;width:40%;border-radius:4px;margin-bottom:0.4rem"></div>
        <div style="background:var(--bg-hover);height:12px;width:80%;border-radius:4px"></div>
      </div>`
      )
      .join('');
  }

  const attrGrid = document.getElementById('stat-grid-attribution');
  if (attrGrid) {
    attrGrid.innerHTML = `<div style="grid-column:span 3;text-align:center;padding:1.5rem;color:var(--text-muted)">⚡ Verifying manifest &amp; loading drivers…</div>`;
  }
}

function renderErrorState(errorMessage) {
  const containers = [
    document.getElementById('kpi-grid'),
    document.getElementById('stat-grid-attribution'),
    document.getElementById('task-list-container'),
  ];

  const errorHtml = `
    <div style="background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;border-radius:var(--radius-sm);padding:1rem;text-align:center;width:100%">
      <div style="font-weight:700;font-size:0.9rem">⚠️ Data Loading Failed</div>
      <div style="font-size:0.78rem;margin:0.3rem 0">${errorMessage}</div>
      <button id="retry-load-btn" class="btn-primary" style="margin-top:0.4rem;padding:0.35rem 0.85rem;font-size:0.78rem">Retry Data Loading</button>
    </div>`;

  containers.forEach((c) => {
    if (c) c.innerHTML = errorHtml;
  });
  document.getElementById('retry-load-btn')?.addEventListener('click', () => init());
}

function updateHealthText() {
  const n = State.hcps.length;
  const r = State.reps.length;
  const healthEl = document.getElementById('health-text');
  const genAt = State.manifest?.generated_at;

  const dateObj = genAt ? new Date(genAt) : new Date();
  const dateFormatted = dateObj.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
  const monthYearFormatted = dateObj.toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  });

  if (healthEl) {
    healthEl.textContent = `🟢 Pipeline Active • ${n} Synthetic Prescribers • ${r} Sales Reps • Updated ${dateFormatted}`;
  }

  const dateOption = document.getElementById('manifest-date-option');
  if (dateOption) {
    dateOption.textContent = `Live Pipeline Run (${dateFormatted})`;
  }

  const driversBadge = document.getElementById('program-drivers-badge');
  if (driversBadge) {
    driversBadge.textContent = monthYearFormatted;
  }
}

async function init() {
  try {
    const loaded = await loadAllData(renderSkeletons, renderErrorState);
    if (!loaded) return;

    renderPipelineInspector();
    populateFilters();
    renderKPIs();
    renderProgramDrivers();
    renderCoachingQueuePanel();
    renderScatter();
    renderPerformanceMatrix();
    renderRepTab();
    renderManagerTab();
    renderPrescribersTab();
    updateHealthText();

    bindTabs();
    bindModals();
    bindFilters();
    bindExports();
    initScrollspy();
  } catch (err) {
    console.error('Dashboard initialisation error:', err);
    renderErrorState(err.message || 'Fatal initialization error');
  } finally {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = 'none';
  }
}

document.addEventListener('DOMContentLoaded', init);
