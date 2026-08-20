/**
 * app.js — Pharma Analytics Platform Main Entry Point (ES Module)
 * Orchestrates modular components across data loading, charts, tables, filters, modals, and sandbox.
 */

import { State, loadAllData, setDatasetMode } from './data-loader.js';
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
  bindManagerFilters,
} from './tables.js';
import { populateFilters, renderPerformanceMatrix, setPerformanceMatrixMode, bindFilters } from './filters.js';
import { bindModals, renderPipelineInspector, openModal, closeModal } from './modals.js';
import { initDatasetPicker } from './dataset-picker.js';
import { getDatasetSelection, setDatasetSelection } from './dataset-store.js';

// Expose modal and matrix mode functions on window for inline HTML onclick attributes
window.openRepModal = openRepModal;
window.openModal = openModal;
window.closeModal = closeModal;
window.setPerformanceMatrixMode = setPerformanceMatrixMode;

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

  const modeLabel =
    State.activeDatasetMode === 'custom'
      ? 'Custom Ingested'
      : State.activeDatasetMode === 'synthetic'
        ? 'Synthetic'
        : 'Hybrid CMS';

  if (healthEl) {
    healthEl.textContent = `🟢 Pipeline Active • ${n} ${modeLabel} Prescribers • ${r} Sales Reps • Updated ${dateFormatted}`;
  }

  const dateOption = document.getElementById('manifest-date-option');
  if (dateOption) {
    dateOption.textContent = `${modeLabel} Run (${dateFormatted})`;
  }

  const driversBadge = document.getElementById('program-drivers-badge');
  if (driversBadge) {
    driversBadge.textContent = monthYearFormatted;
  }
}

function refreshAllViews() {
  populateFilters();
  updateHealthText();
  renderPage();
}

const PAGES = {
  overview: {
    section: 'overview',
    title: 'Overview',
    subtitle: 'Executive KPI Summary & Program Drivers',
    render: () => {
      renderKPIs();
      renderProgramDrivers();
    },
  },
  matrix: {
    section: 'matrix',
    title: 'Performance Matrix',
    subtitle: 'Call Plan Compliance vs Rx Lift Correlation & 2x2 Quadrants',
    render: () => {
      renderPerformanceMatrix();
      renderScatter();
    },
  },
  reps: {
    section: 'reps',
    title: 'Reps Scorecard',
    subtitle: 'Individual rep compliance rates, lift metrics, and coaching priorities',
    render: () => renderRepTab(),
  },
  territories: {
    section: 'territories',
    title: 'Territory Engine',
    subtitle: 'Call Plan Re-allocation Engine & Territory Rollup Summary',
    render: () => renderManagerTab(),
  },
  prescribers: {
    section: 'prescribers',
    title: 'Prescribers',
    subtitle: 'Synthesized Prescribers Directory & Monthly Rx',
    render: () => renderPrescribersTab(),
  },
  'coaching-queue': {
    section: 'coaching-queue',
    title: 'Coaching Queue',
    subtitle: "Today's Tasks — Prioritized Rep Coaching Queue",
    render: () => renderCoachingQueuePanel(),
  },
  pipeline: {
    section: 'pipeline',
    title: 'Pipeline Inspector',
    subtitle: 'Data Engineering Pipeline — Execution Telemetry',
    render: () => renderPipelineInspector(),
  },
};

function currentPage() {
  const hash = (window.location.hash || '').replace(/^#\/?/, '');
  return Object.prototype.hasOwnProperty.call(PAGES, hash) ? hash : 'overview';
}

function renderPage() {
  const key = currentPage();
  const page = PAGES[key];

  document.querySelectorAll('.page').forEach((sec) => {
    sec.classList.toggle('active', sec.id === page.section);
  });

  document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
    item.classList.toggle('active', item.getAttribute('data-page') === page.section);
  });

  document.querySelector('.page-title').textContent = page.title;
  document.querySelector('.page-subtitle').textContent = page.subtitle;

  page.render();

  if (typeof window.scrollTo === 'function') window.scrollTo({ top: 0, behavior: 'smooth' });
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebar-backdrop')?.classList.remove('open');
}

/**
 * Apply a dataset selection across the whole app: purge transient UI state,
 * swap the active dataset in State, and re-render top-to-bottom.
 */
function applyDatasetMode(mode, filename) {
  const sameMode = State.activeDatasetMode === mode;

  // Selecting the currently-active built-in mode is a no-op for rendering.
  if (sameMode && mode !== 'custom') return;

  // 1. COMPLETE STATE PURGE
  State.quadrantFilter = null;
  State.sortKey = null;
  State.sortDir = 'asc';
  State.repPage = 1;
  State.presPage = 1;
  State.coachingPage = 1;

  // Destroy active chart instances to prevent canvas memory leaks
  if (State.scatterChart) {
    try { State.scatterChart.destroy(); } catch (_) {}
    State.scatterChart = null;
  }
  if (State.importanceChart) {
    try { State.importanceChart.destroy(); } catch (_) {}
    State.importanceChart = null;
  }
  if (State.shapChart) {
    try { State.shapChart.destroy(); } catch (_) {}
    State.shapChart = null;
  }

  // Reset UI filter form inputs
  const filterIds = [
    'filter-territory', 'filter-rep', 'filter-specialty',
    'filter-tier', 'filter-search'
  ];
  filterIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  // 2. SET ACTIVE MODE & REASSIGN STATE
  setDatasetMode(mode);

  // 3. TOP-TO-BOTTOM DOM RE-RENDER
  refreshAllViews();
}

async function init() {
  try {
    // Restore any persisted dataset selection before the data layer resolves payloads.
    // Uploaded datasets only exist in memory, so a persisted 'custom' mode gracefully
    // falls back to Hybrid CMS on a fresh page load.
    const storedSelection = getDatasetSelection();
    if (storedSelection.mode === 'custom' && !State.customData) {
      State.activeDatasetMode = 'hybrid';
      setDatasetSelection({ mode: 'hybrid', filename: null });
    } else {
      State.activeDatasetMode = storedSelection.mode;
    }

    const loaded = await loadAllData(renderSkeletons, renderErrorState);
    if (!loaded) return;

    populateFilters();
    updateHealthText();

    renderPage();

    bindTabs();
    bindModals();
    bindFilters();
    bindExports();
    bindManagerFilters();
    initDatasetPicker({ onDatasetChange: applyDatasetMode });

    if (!window.location.hash) {
      window.history.replaceState(null, '', '#/overview');
    }
    window.addEventListener('hashchange', renderPage);
  } catch (err) {
    console.error('Dashboard initialisation error:', err);
    renderErrorState(err.message || 'Fatal initialization error');
  } finally {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = 'none';
  }
}

document.addEventListener('DOMContentLoaded', init);
