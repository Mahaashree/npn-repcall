/**
 * js/modals.js
 * Architecture modal, Data Engineering pipeline inspector modal, Rep coaching detail modal, and Coaching queue modal.
 */

import { State } from './data-loader.js';

export function openModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

export function closeModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('open');
    document.body.style.overflow = '';
  }
}

export function bindModals() {
  const closeMap = {
    'arch-modal-close': 'arch-modal',
    'pipeline-modal-close': 'pipeline-modal',
    'rep-modal-close': 'rep-modal',
    'coaching-modal-close': 'coaching-modal',
  };
  Object.entries(closeMap).forEach(([btnId, modalId]) => {
    document.getElementById(btnId)?.addEventListener('click', () => closeModal(modalId));
  });
  document.querySelectorAll('.modal-overlay').forEach((mo) => {
    mo.addEventListener('click', (e) => {
      if (e.target === mo) closeModal(mo.id);
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach((m) => closeModal(m.id));
    }
  });
  document.getElementById('arch-btn')?.addEventListener('click', () => {
    renderArchTelemetryGrid();
    openModal('arch-modal');
  });
  document.getElementById('coaching-queue-view-all-btn')?.addEventListener('click', () => {
    openCoachingQueueModal();
  });
}

export function openCoachingQueueModal() {
  const tasks = State.coachingQueue ?? [];
  document.getElementById('coaching-modal-title').textContent =
    `📋 Full Prioritized Coaching Queue (${tasks.length} Total Priority Tasks)`;

  const body = document.getElementById('coaching-modal-body');
  body.innerHTML = `
    <div style="overflow-x:auto">
      <table class="data-table" aria-label="Full Coaching Queue Table">
        <thead>
          <tr>
            <th>Priority</th>
            <th>Task ID</th>
            <th>Target Rep</th>
            <th>Territory</th>
            <th>Action Item</th>
            <th>Reason Code</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${tasks
            .map((t) => {
              const priBadge =
                t.priority === 'urgent' ? 'badge-red' : t.priority === 'monitor' ? 'badge-amber' : 'badge-green';
              return `
              <tr>
                <td><span class="kpi-badge ${priBadge}">${t.priority.toUpperCase()}</span></td>
                <td class="font-mono">${t.task_id}</td>
                <td><strong>${t.rep_id}</strong></td>
                <td><span class="kpi-badge badge-cyan">${t.territory_id}</span></td>
                <td>${t.title}</td>
                <td style="font-size:0.75rem;color:var(--text-muted)"><code>${t.reason_code}</code></td>
                <td><span class="kpi-badge badge-violet">${t.status || 'Pending'}</span></td>
                <td>
                  <button class="btn-primary" style="padding:0.25rem 0.6rem;font-size:0.72rem" onclick="window.closeModal('coaching-modal');window.openRepModal('${t.rep_id}')">
                    Inspect Rep
                  </button>
                </td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>
    </div>`;
  openModal('coaching-modal');
}

export function renderPipelineInspector() {
  const tel = State.telemetry ?? {};
  const stages = [
    {
      icon: '🧪',
      label: 'Synthetic Data Engine',
      stat: `${tel.initial_rows ?? 820} initial HCP records`,
      detail: {
        title: '🧪 Synthetic Data Engine (generate_dataset.py)',
        stats: [
          ['Script', 'generate_dataset.py'],
          ['Dataset', 'FDA TIRF REMS-inspired structure (fully synthetic)'],
          ['HCPs generated', String(tel.initial_rows ?? 820)],
          [
            'Reps / Territories',
            `${State.reps.length || 14} Reps / ${new Set(State.reps.map((r) => r.territory_id)).size || 6} Territories`,
          ],
        ],
      },
    },
    {
      icon: '🔒',
      label: 'CMS Privacy Filter',
      stat: `${tel.suppressed_rows ?? 87} records suppressed`,
      detail: {
        title: '🔒 CMS Small-Cell Suppression (data_preprocessing.py)',
        stats: [
          ['Filter applied', 'Tot_Clms ≥ 11 (mirrors public dataset disclosure rules)'],
          ['Initial rows', String(tel.initial_rows ?? 820)],
          ['Suppressed rows', String(tel.suppressed_rows ?? 87)],
          ['Retained after suppression', String(tel.after_privacy_filter ?? 733)],
        ],
      },
    },
    {
      icon: '⚙️',
      label: 'Feature Engineering',
      stat: `4 engineered features`,
      detail: {
        title: '⚙️ Feature Engineering (data_preprocessing.py)',
        stats: [
          ['Compliance_Pct', 'Actual_Calls / max(1, Target_Calls) × 100'],
          ['Monthly_Call_Frequency', 'Actual_Calls / 3.0'],
          ['Sample_Velocity', 'Samples_Dropped / max(1, Actual_Calls)'],
          ['Log_Baseline_Fills', 'ln(1 + Tot_30day_Fills)'],
        ],
      },
    },
    {
      icon: '📊',
      label: 'Analytics Engine',
      stat: `${tel.retained_rows ?? 733} HCPs segmented`,
      detail: {
        title: '📊 Analytics Engine (analytics_engine.py)',
        stats: [
          ['Total HCPs', String(tel.retained_rows ?? 733)],
          ['Sales Reps', String(State.reps.length || 14)],
          ['Execution time', `${tel.execution_time_sec ?? 0.24}s`],
        ],
      },
    },
    {
      icon: '🤖',
      label: 'ML Suite',
      stat: `${State.ml?.tournament_table?.length ?? 4} models benchmarked`,
      detail: {
        title: '🤖 ML Benchmarking Suite (ml_models_suite.py)',
        stats: [
          ['Models', 'Ridge, OLS, Random Forest, XGBoost'],
          ['Best model', State.ml?.best_model_summary?.model_label ?? '—'],
          ['Best Test R²', State.ml?.best_model_summary?.test_r2?.toFixed(4) ?? '—'],
        ],
      },
    },
  ];

  const container = document.getElementById('pipeline-nodes');
  if (!container) return;
  container.innerHTML = '';
  stages.forEach((s, i) => {
    const node = document.createElement('div');
    node.className = 'pipeline-node';
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    node.setAttribute('aria-label', `Pipeline stage: ${s.label}`);
    node.innerHTML = `
      <span class="node-icon">${s.icon}</span>
      <div>
        <div class="node-label">${s.label}</div>
        <div class="node-stat">${s.stat}</div>
      </div>`;
    node.addEventListener('click', () => openPipelineModal(s.detail));
    node.addEventListener('keydown', (e) => (e.key === 'Enter' || e.key === ' ') && openPipelineModal(s.detail));
    container.appendChild(node);
    if (i < stages.length - 1) {
      const arrow = document.createElement('span');
      arrow.className = 'pipeline-arrow';
      arrow.textContent = '›';
      container.appendChild(arrow);
    }
  });
}

export function openPipelineModal(detail) {
  document.getElementById('pipeline-modal-title').textContent = detail.title;
  const body = document.getElementById('pipeline-modal-body');
  body.innerHTML = `
    <table style="width:100%;border-collapse:collapse">
      ${detail.stats
        .map(
          ([k, v]) => `
        <tr>
          <td style="padding:0.55rem 1rem 0.55rem 0;font-size:0.78rem;color:var(--text-muted);width:40%;vertical-align:top">${k}</td>
          <td style="padding:0.55rem 0;font-size:0.82rem;color:var(--text-primary);font-family:monospace">${v}</td>
        </tr>`
        )
        .join('')}
    </table>`;
  openModal('pipeline-modal');
}

export function renderArchTelemetryGrid() {
  const t = State.telemetry ?? {};
  const el = document.getElementById('arch-telemetry-grid');
  if (!el) return;
  const stats = [
    ['Initial Records', String(t.initial_rows ?? '—')],
    ['After Privacy Filter', String(t.after_privacy_filter ?? '—')],
    ['Final Retained Records', String(t.retained_rows ?? '—')],
    ['Suppressed Records', String(t.suppressed_rows ?? '—')],
    ['Nulls Imputed', String(t.nulls_imputed ?? 0)],
    ['Pipeline Execution', `${t.execution_time_sec ?? '—'}s`],
    ['Data Version', State.manifest?.data_version ?? '—'],
    ['Manifest Files', `${State.manifest?.files?.length ?? 6} verified JSON payloads`],
  ];
  el.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:0.75rem">
      ${stats
        .map(
          ([k, v]) => `
        <div style="background:var(--bg-card-2);border-radius:var(--radius-sm);padding:0.75rem">
          <div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.07em">${k}</div>
          <div style="font-size:0.9rem;font-weight:700;color:var(--text-primary);margin-top:0.2rem;font-family:monospace">${v}</div>
        </div>`
        )
        .join('')}
    </div>`;
}
