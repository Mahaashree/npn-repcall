/**
 * app.js — Pharma Analytics Platform Main Entry Point (ES Module)
 * Orchestrates modular components across data loading, charts, tables, filters, modals, and sandbox.
 */

import { State, loadAllData, setDatasetMode, processCustomDataset } from './data-loader.js';
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
import { populateFilters, renderPerformanceMatrix, setPerformanceMatrixMode, bindFilters, initScrollspy } from './filters.js';
import { bindModals, renderPipelineInspector, openModal, closeModal } from './modals.js';

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
}

function updateDrawerStep(stepId, status, detailText) {
  const stepEl = document.getElementById(`step-${stepId}`);
  const statusEl = document.getElementById(`step-${stepId}-status`);
  const detailEl = document.getElementById(`step-${stepId}-detail`);

  if (stepEl) {
    stepEl.classList.remove('pending', 'active', 'completed');
    stepEl.classList.add(status);
  }
  if (statusEl) {
    statusEl.textContent = status === 'completed' ? '✓ Complete' : status === 'active' ? 'In Progress…' : 'Pending';
  }
  if (detailEl && detailText) {
    detailEl.textContent = detailText;
  }
}

function bindDatasetModeToggle() {
  const btnHybrid = document.getElementById('btn-mode-hybrid');
  const btnSynth  = document.getElementById('btn-mode-synthetic');
  const btnCustom = document.getElementById('btn-mode-custom');
  const fileInput = document.getElementById('custom-file-input');
  const drawer = document.getElementById('ingestion-drawer');
  const drawerClose = document.getElementById('ingestion-drawer-close');
  const progressFill = document.getElementById('ingestion-progress-fill');
  const drawerTitle = document.getElementById('ingestion-drawer-status-title');
  const spinner = document.getElementById('ingestion-spinner');
  const filenameBadge = document.getElementById('ingestion-filename');

  if (drawerClose && drawer) {
    drawerClose.addEventListener('click', () => drawer.classList.remove('open'));
  }

  const handleModeChange = (mode) => {
    if (mode === 'custom' && !State.customData) {
      // Trigger file selector if custom data hasn't been uploaded yet
      fileInput?.click();
      return;
    }

    if (State.activeDatasetMode === mode) return;

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

    btnHybrid?.classList.toggle('active', mode === 'hybrid');
    btnSynth?.classList.toggle('active', mode === 'synthetic');
    btnCustom?.classList.toggle('active', mode === 'custom');

    // 2. SET ACTIVE MODE & REASSIGN STATE
    setDatasetMode(mode);

    // 3. TOP-TO-BOTTOM DOM RE-RENDER
    refreshAllViews();
  };

  btnHybrid?.addEventListener('click', () => handleModeChange('hybrid'));
  btnSynth?.addEventListener('click', () => handleModeChange('synthetic'));
  btnCustom?.addEventListener('click', () => handleModeChange('custom'));

  fileInput?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset file input for future uploads
    fileInput.value = '';

    // Show non-blocking drawer in bottom-right corner
    if (drawer) {
      drawer.classList.add('open');
    }
    if (filenameBadge) {
      filenameBadge.textContent = file.name;
    }
    if (drawerTitle) {
      drawerTitle.textContent = 'Dynamic Dataset Ingestion';
    }
    if (spinner) {
      spinner.classList.remove('done');
    }

    // Reset steps to pending
    ['inspect', 'synthesize', 'features', 'ml'].forEach((s) => updateDrawerStep(s, 'pending'));
    if (progressFill) progressFill.style.width = '5%';

    try {
      await processCustomDataset(file, file.name, (event) => {
        if (progressFill && event.progress) {
          progressFill.style.width = `${event.progress}%`;
        }
        if (event.step) {
          updateDrawerStep(event.step, event.status, event.detail);
        }
      });

      // Ingestion complete!
      if (spinner) spinner.classList.add('done');
      if (drawerTitle) drawerTitle.textContent = 'Ingestion Complete (Active)';
      if (progressFill) progressFill.style.width = '100%';

      if (btnCustom) {
        btnCustom.textContent = '📁 Custom Dataset (Active)';
        btnCustom.classList.add('active');
        btnHybrid?.classList.remove('active');
        btnSynth?.classList.remove('active');
      }

      setDatasetMode('custom');
      refreshAllViews();

      // Auto-minimize after 5 seconds
      setTimeout(() => {
        if (drawer) drawer.classList.remove('open');
      }, 5000);
    } catch (err) {
      console.error('Custom ingestion error:', err);
      if (drawerTitle) drawerTitle.textContent = 'Ingestion Failed';
      alert(`Error during dataset ingestion: ${err.message}`);
    }
  });
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
    bindDatasetModeToggle();
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
