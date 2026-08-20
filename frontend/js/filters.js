/**
 * js/filters.js
 * Debounced search inputs, dropdown populators, 2x2 performance matrix quadrant toggles.
 */

import { State, normQuadrant, setMatrixMode } from './data-loader.js';
import { renderScatter } from './charts.js';
import { renderPrescribersTab, renderRepTab, renderManagerTab } from './tables.js';

export function debounce(fn, delay = 280) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

export function populateFilters() {
  const hcps = State.hcps;
  const reps = State.reps;
  const specialties = [...new Set(hcps.map((h) => h.Specialty).filter(Boolean))].sort();
  const territories = [...new Set(reps.map((r) => r.territory_id).filter(Boolean))].sort();
  const repNames = [...new Set(reps.map((r) => r.rep_id).filter(Boolean))].sort();

  fillSelect('filter-specialty', specialties);
  fillSelect('filter-territory', territories);
  fillSelect('filter-rep', repNames);

  const tabCountPres = document.getElementById('tab-count-pres');
  if (tabCountPres) tabCountPres.textContent = hcps.length;
}

function fillSelect(id, options) {
  const el = document.getElementById(id);
  if (!el) return;
  const currentVal = el.value;
  el.innerHTML = `<option value="">All ${id.replace('filter-', '').replace(/^\w/, (c) => c.toUpperCase())}s</option>`;
  options.forEach((v) => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  });
  el.value = currentVal;
}

export function applyFilters() {
  const specialty = document.getElementById('filter-specialty')?.value;
  const territory = document.getElementById('filter-territory')?.value;
  const rep = document.getElementById('filter-rep')?.value;
  const tier = document.getElementById('filter-tier')?.value;
  const search = document.getElementById('filter-search')?.value.toLowerCase().trim();

  State.filteredHcps = State.hcps.filter((h) => {
    if (State.quadrantFilter && normQuadrant(h._quadrant) !== normQuadrant(State.quadrantFilter)) return false;
    if (specialty && h.Specialty !== specialty) return false;
    if (territory && h.Territory !== territory) return false;
    if (rep && h.Sales_Rep !== rep) return false;
    if (tier && String(h.HCP_Tier) !== tier) return false;
    if (search) {
      const name = (h.Physician_Name ?? '').toLowerCase();
      const npi = (h.Prscrbr_NPI ?? '').toLowerCase();
      if (!name.includes(search) && !npi.includes(search)) return false;
    }
    return true;
  });

  State.presPage = 1;
  State.repPage = 1;
  renderScatter();
  renderPerformanceMatrix();
  renderPrescribersTab();
  renderRepTab();
  renderManagerTab();

  const presCount = document.getElementById('tab-count-pres');
  if (presCount) presCount.textContent = State.filteredHcps.length;
}

export function renderPerformanceMatrix() {
  const grid = document.getElementById('perf-matrix');
  if (!grid) return;

  const specialty = document.getElementById('filter-specialty')?.value;
  const territory = document.getElementById('filter-territory')?.value;
  const rep = document.getElementById('filter-rep')?.value;
  const tier = document.getElementById('filter-tier')?.value;
  const search = document.getElementById('filter-search')?.value.toLowerCase().trim();

  const baseHcps = State.hcps.filter((h) => {
    if (specialty && h.Specialty !== specialty) return false;
    if (territory && h.Territory !== territory) return false;
    if (rep && h.Sales_Rep !== rep) return false;
    if (tier && String(h.HCP_Tier) !== tier) return false;
    if (search) {
      const name = (h.Physician_Name ?? '').toLowerCase();
      const npi = (h.Prscrbr_NPI ?? '').toLowerCase();
      if (!name.includes(search) && !npi.includes(search)) return false;
    }
    return true;
  });

  const total = baseHcps.length || 1;
  const isCei = State.matrixMode === 'cei';
  const quadMap = isCei
    ? { 'Star Performers': 0, 'Efficient High-Performers': 0, 'Targeting Risk': 0, 'Needs Intervention': 0 }
    : { 'Star Performers': 0, 'Efficiency Risk': 0, 'Unrealized Potential': 0, 'Needs Intervention': 0 };

  baseHcps.forEach((h) => {
    const nq = normQuadrant(h._quadrant, State.matrixMode);
    if (quadMap[nq] !== undefined) quadMap[nq]++;
  });

  const cfg = isCei
    ? {
        'Star Performers': {
          cls: 'q-stars',
          icon: '⭐',
          action: 'High Execution & High Return • Model Best Practices',
        },
        'Efficient High-Performers': {
          cls: 'q-underserved',
          icon: '⚡',
          action: 'High Responsiveness Despite Deficits • Scale Detailing Capacity',
        },
        'Targeting Risk': {
          cls: 'q-ineffective',
          icon: '🟡',
          action: 'High Effort, Low Return • Reallocate Doctor Tiers',
        },
        'Needs Intervention': {
          cls: 'q-at-risk',
          icon: '🔴',
          action: 'Shortfalls Across Calls & Samples • Performance Realignment',
        },
      }
    : {
        'Star Performers': {
          cls: 'q-stars',
          icon: '⭐',
          action: 'Maintain & Reward • Model Best Practices',
        },
        'Efficiency Risk': {
          cls: 'q-ineffective',
          icon: '🟡',
          action: 'Clinical Detail Coaching • Messaging Quality',
        },
        'Unrealized Potential': {
          cls: 'q-underserved',
          icon: '🔵',
          action: 'Expand Target Capacity • Increase Visit Frequency',
        },
        'Needs Intervention': {
          cls: 'q-at-risk',
          icon: '🔴',
          action: 'Performance Management • Plan Realignment',
        },
      };

  grid.innerHTML = '';
  const order = isCei
    ? ['Star Performers', 'Efficient High-Performers', 'Targeting Risk', 'Needs Intervention']
    : ['Star Performers', 'Efficiency Risk', 'Unrealized Potential', 'Needs Intervention'];

  order.forEach((q) => {
    const c = cfg[q];
    const n = quadMap[q] || 0;
    const pct = ((n / total) * 100).toFixed(1);
    const div = document.createElement('div');
    const isActive = normQuadrant(State.quadrantFilter, State.matrixMode) === q;
    div.className = `quadrant-card ${c.cls}${isActive ? ' q-active' : ''}`;
    div.setAttribute('role', 'button');
    div.setAttribute('tabindex', '0');
    div.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    div.setAttribute('aria-label', `${q} quadrant: ${n} HCPs (${pct}%)`);
    div.innerHTML = `
      <span class="q-filter-hint" aria-hidden="true">${isActive ? '✓ Active filter' : 'Click to filter'}</span>
      <div class="q-icon">${c.icon}</div>
      <div class="q-name">${q}</div>
      <div class="q-count">${n}</div>
      <div class="q-pct">${pct}% of visible HCPs</div>
      <div class="q-action">${c.action}</div>`;
    div.addEventListener('click', () => toggleQuadrantFilter(q));
    div.addEventListener('keydown', (e) => (e.key === 'Enter' || e.key === ' ') && toggleQuadrantFilter(q));
    grid.appendChild(div);
  });
}

export function toggleQuadrantFilter(q) {
  State.quadrantFilter = State.quadrantFilter === q ? null : q;
  applyFilters();
}

export function setPerformanceMatrixMode(mode) {
  const normMode = (mode || '').toUpperCase() === 'CEI' || (mode || '').toLowerCase() === 'cei' ? 'cei' : 'legacy';
  setMatrixMode(normMode);

  // Update all toggle button active classes
  const legacyButtons = document.querySelectorAll('#btn-compliance-mode, #btn-matrix-legacy, [data-matrix-mode="legacy"], [data-mode="COMPLIANCE"]');
  const ceiButtons = document.querySelectorAll('#btn-cei-mode, #btn-matrix-cei, [data-matrix-mode="cei"], [data-mode="CEI"]');

  legacyButtons.forEach((btn) => btn.classList.toggle('active', normMode === 'legacy'));
  ceiButtons.forEach((btn) => btn.classList.toggle('active', normMode === 'cei'));

  const matrixSubtitle = document.getElementById('matrix-card-subtitle');
  if (matrixSubtitle) {
    matrixSubtitle.textContent = normMode === 'cei'
      ? 'AI Composite Execution (CEI) × Rx Lift Quadrants (75% CEI Split)'
      : 'Compliance × Rx Lift Quadrants (80% Compliance Split)';
  }

  applyFilters();
  renderRepTab();
}

window.setPerformanceMatrixMode = setPerformanceMatrixMode;

export function bindFilters() {
  ['filter-specialty', 'filter-territory', 'filter-rep', 'filter-tier'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', applyFilters);
  });
  document.getElementById('filter-search')?.addEventListener('input', debounce(applyFilters, 280));
  document.getElementById('reset-filters')?.addEventListener('click', () => {
    ['filter-specialty', 'filter-territory', 'filter-rep', 'filter-tier'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const s = document.getElementById('filter-search');
    if (s) s.value = '';
    State.quadrantFilter = null;
    applyFilters();
  });

  // Explicit click listeners for Performance Matrix dual-mode switcher
  document.getElementById('btn-cei-mode')?.addEventListener('click', () => setPerformanceMatrixMode('CEI'));
  document.getElementById('btn-compliance-mode')?.addEventListener('click', () => setPerformanceMatrixMode('COMPLIANCE'));
  document.getElementById('btn-matrix-cei')?.addEventListener('click', () => setPerformanceMatrixMode('CEI'));
  document.getElementById('btn-matrix-legacy')?.addEventListener('click', () => setPerformanceMatrixMode('COMPLIANCE'));

  document.querySelectorAll('.matrix-toggle-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetMode = btn.dataset.mode || btn.dataset.matrixMode || (btn.id.includes('cei') ? 'CEI' : 'COMPLIANCE');
      setPerformanceMatrixMode(targetMode);
    });
  });

  document.getElementById('rep-page-size')?.addEventListener('change', (e) => {
    State.repPageSize = +e.target.value;
    State.repPage = 1;
    renderRepTab();
  });
  document.getElementById('pres-page-size')?.addEventListener('change', (e) => {
    State.presPageSize = +e.target.value;
    State.presPage = 1;
    renderPrescribersTab();
  });
}

export function initScrollspy() {
  // Deprecated: navigation now uses SPA hash routing (see app.js renderPage).
}
