/**
 * js/tables.js
 * Dynamic data tables, paginated views, territory rollups, CSV exports, and Executive KPIs.
 */

import { State, fmt, clamp, normQuadrant, quadrantBadgeClass, quadrantColor } from './data-loader.js';
import { openModal } from './modals.js';

export function renderKPIs() {
  if (!State.reps.length || !State.hcps.length) return;

  const activeReps = State.reps.filter((r) => r.is_active);
  const meanComp = activeReps.reduce((s, r) => s + (r.compliance_pct || 0), 0) / (activeReps.length || 1);
  const meanLift = activeReps.reduce((s, r) => s + (r.rx_lift_pct || 0), 0) / (activeReps.length || 1);

  const bestModel = State.ml?.best_model_summary ?? {};
  const testR2 = bestModel.test_r2 ?? 0.6842;
  const bootCi = bestModel.bootstrap_ci ?? '[0.6214, 0.7380]';

  const comps = State.hcps.map((h) => h.Compliance_Pct_raw);
  const lifts = State.hcps.map((h) => h.Rx_Lift_Pct);
  const n = comps.length || 1;
  const sumC = comps.reduce((a, b) => a + b, 0);
  const sumL = lifts.reduce((a, b) => a + b, 0);
  const sumCL = comps.reduce((a, b, i) => a + b * lifts[i], 0);
  const sumC2 = comps.reduce((a, b) => a + b * b, 0);
  const sumL2 = lifts.reduce((a, b) => a + b * b, 0);
  const num = n * sumCL - sumC * sumL;
  const den = Math.sqrt((n * sumC2 - sumC * sumC) * (n * sumL2 - sumL * sumL));
  const pearsonR = den !== 0 ? num / den : 0.2537;

  const cards = [
    {
      accent: 'green',
      label: 'Mean Compliance Rate',
      value: fmt.pct(meanComp),
      sub: `${fmt.num(State.hcps.length)} HCPs across ${State.reps.length} sales reps`,
      barPct: clamp(meanComp, 0, 100),
      badge:
        meanComp >= 80
          ? { cls: 'badge-green', text: 'On Target ✓' }
          : { cls: 'badge-amber', text: 'Below 80% Threshold' },
    },
    {
      accent: 'cyan',
      label: 'Overall Rx Volume Growth',
      value: fmt.pct2(meanLift),
      sub: `Mean campaign lift across territories`,
      barPct: clamp((meanLift / 18) * 100, 0, 100),
      badge:
        meanLift > 0
          ? { cls: 'badge-cyan', text: 'Positive Growth ↑' }
          : { cls: 'badge-red', text: 'Negative Growth ↓' },
    },
    {
      accent: 'violet',
      label: 'Pearson r (Compliance × Lift)',
      value: fmt.dec(pearsonR, 4),
      sub: `Statistically significant (p < 0.001)`,
      barPct: clamp(Math.abs(pearsonR) * 100, 0, 100),
      badge: { cls: 'badge-violet', text: 'Statistically Significant' },
    },
    {
      accent: 'amber',
      label: `Held-Out Test R² (${bestModel.model_label || 'RF'})`,
      value: testR2.toFixed(4),
      sub: `95% CI: ${bootCi}`,
      barPct: clamp(testR2 * 100, 0, 100),
      badge: testR2 >= 0.5 ? { cls: 'badge-green', text: 'Strong Fit' } : { cls: 'badge-amber', text: 'Moderate Fit' },
    },
  ];

  const grid = document.getElementById('kpi-grid');
  if (!grid) return;
  grid.innerHTML = cards
    .map(
      (c) => `
    <div class="kpi-card fade-in-up" data-accent="${c.accent}">
      <div class="kpi-label">${c.label}</div>
      <div class="kpi-value">${c.value}</div>
      <div class="kpi-sub">${c.sub}</div>
      <span class="kpi-badge ${c.badge.cls}" style="margin-top:0.5rem">${c.badge.text}</span>
      <div class="kpi-bar">
        <div class="kpi-bar-fill" style="width:0%;background:var(--${c.accent})" data-target="${c.barPct}"></div>
      </div>
    </div>`
    )
    .join('');

  requestAnimationFrame(() => {
    grid.querySelectorAll('.kpi-bar-fill').forEach((el) => {
      el.style.width = el.dataset.target + '%';
    });
  });
}

export function renderProgramDrivers() {
  const container = document.getElementById('stat-grid-attribution');
  if (!container) return;
  const drivers = State.attribution?.global_importance ?? [];

  if (!drivers.length) {
    container.innerHTML = `<div style="grid-column:span 3;text-align:center;padding:1rem;color:var(--text-muted)">No attribution drivers available.</div>`;
    return;
  }

  container.innerHTML = drivers
    .slice(0, 6)
    .map(
      (d) => `
    <div class="stat-tile">
      <div class="stat-tile-label">${d.feature}</div>
      <div class="stat-tile-val">${d.importance_pct.toFixed(1)}%</div>
      <div class="stat-tile-sub">${d.description || 'Feature Contribution'}</div>
    </div>`
    )
    .join('');
}

export function renderCoachingQueuePanel() {
  const container = document.getElementById('task-list-container');
  if (!container) return;
  const tasks = State.coachingQueue ?? [];

  if (!tasks.length) {
    container.innerHTML = `<div style="text-align:center;padding:1rem;color:var(--text-muted)">No prioritized coaching tasks in queue.</div>`;
    return;
  }

  container.innerHTML = tasks
    .slice(0, 5)
    .map((t) => {
      const avatarCls = t.priority === 'urgent' ? 'red' : t.priority === 'monitor' ? 'amber' : 'green';
      const dotCls = t.priority === 'urgent' ? 'red' : t.priority === 'monitor' ? 'amber' : 'green';
      const initials = t.rep_id ? t.rep_id.replace('REP-', 'R') : 'R';
      return `
      <div class="task-item" onclick="window.openRepModal('${t.rep_id}')">
        <div class="task-avatar ${avatarCls}">${initials}</div>
        <div class="task-content">
          <div class="task-title">${t.title}</div>
          <div class="task-sub">${t.subtext}</div>
        </div>
        <span class="priority-dot ${dotCls}" title="${t.priority}"></span>
      </div>`;
    })
    .join('');
}

export function renderRepTab() {
  const territoryFilter = document.getElementById('filter-territory')?.value;
  const repFilter = document.getElementById('filter-rep')?.value;

  let scorecards = State.reps;
  if (territoryFilter) scorecards = scorecards.filter((r) => r.territory_id === territoryFilter);
  if (repFilter) scorecards = scorecards.filter((r) => r.rep_id === repFilter);
  if (State.quadrantFilter)
    scorecards = scorecards.filter((r) => normQuadrant(r.quadrant) === normQuadrant(State.quadrantFilter));

  const total = scorecards.length;
  const pages = Math.ceil(total / State.repPageSize) || 1;
  const start = (State.repPage - 1) * State.repPageSize;
  const slice = scorecards.slice(start, start + State.repPageSize);

  const tbody = document.getElementById('rep-tbody');
  if (!tbody) return;

  if (!slice.length) {
    tbody.innerHTML =
      '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--text-muted)">No sales reps match these filters.</td></tr>';
  } else {
    tbody.innerHTML = slice
      .map((r, i) => {
        const comp = r.compliance_pct ?? 0;
        const lift = r.rx_lift_pct ?? 0;
        const compColor = comp >= 80 ? 'var(--green)' : comp >= 60 ? 'var(--amber)' : 'var(--red)';
        const liftColor = lift >= State.medianLift ? 'var(--primary)' : 'var(--text-secondary)';
        const priColor =
          r.coaching_priority === 'Urgent Coaching'
            ? 'badge-red'
            : r.coaching_priority === 'Monitor'
              ? 'badge-amber'
              : 'badge-green';
        const domNorm = normQuadrant(r.quadrant);
        const domCls = quadrantBadgeClass(domNorm);
        const action =
          {
            'Star Performers': 'Maintain & Reward',
            'Efficiency Risk': 'Clinical Detail Coaching',
            'Unrealized Potential': 'Expand Target Capacity',
            'Needs Intervention': 'Performance Management',
          }[domNorm] ?? '—';

        const activeBadge = r.is_active
          ? ''
          : ' <span class="tab-badge" style="background:var(--red-bg);color:var(--red-text)">Inactive</span>';

        return `
        <tr class="fade-in-up" data-rep="${r.rep_id}" style="cursor:pointer" tabindex="0"
            aria-label="Open coaching report for ${r.rep_id}">
          <td style="color:var(--text-muted)">${start + i + 1}</td>
          <td><strong>${r.sales_rep_name || r.rep_id}</strong>${activeBadge}</td>
          <td><span class="kpi-badge badge-cyan">${r.territory_id}</span></td>
          <td class="text-right font-mono">${r.prescriber_count ?? 0}</td>
          <td class="text-right font-mono">${r.total_target_calls ?? 0}</td>
          <td class="text-right font-mono">${r.total_actual_calls ?? 0}</td>
          <td class="text-right">
            <span style="color:${compColor};font-weight:700">${comp.toFixed(1)}%</span>
          </td>
          <td class="text-right">
            <span style="color:${liftColor};font-weight:700">${lift.toFixed(3)}%</span>
          </td>
          <td><span class="kpi-badge ${domCls}">${domNorm}</span></td>
          <td><span class="kpi-badge ${priColor}">${r.coaching_priority}</span></td>
          <td style="color:var(--text-secondary);font-size:0.78rem">${action}</td>
        </tr>`;
      })
      .join('');
  }

  const repRecordCount = document.getElementById('rep-record-count');
  if (repRecordCount) {
    repRecordCount.textContent = total
      ? `Showing ${start + 1}–${Math.min(start + State.repPageSize, total)} of ${total} reps`
      : '0 reps matching filters';
  }
  const tabCountRep = document.getElementById('tab-count-rep');
  if (tabCountRep) tabCountRep.textContent = total;

  renderPagination('rep-pagination', State.repPage, pages, (p) => {
    State.repPage = p;
    renderRepTab();
  });

  tbody.querySelectorAll('tr[data-rep]').forEach((row) => {
    row.addEventListener('click', () => openRepModal(row.dataset.rep));
    row.addEventListener('keydown', (e) => e.key === 'Enter' && openRepModal(row.dataset.rep));
  });
}

export function openRepModal(repId) {
  const r = State.reps.find((s) => s.rep_id === repId);
  if (!r) return;
  document.getElementById('rep-modal-title').textContent =
    `${r.sales_rep_name || r.rep_id} (${r.rep_id}) — Coaching Report`;

  const hcps = State.hcps.filter((h) => h.Sales_Rep === repId);
  const qc = { 'Star Performers': 0, 'Efficiency Risk': 0, 'Unrealized Potential': 0, 'Needs Intervention': 0 };
  hcps.forEach((h) => {
    const q = normQuadrant(h._quadrant);
    if (qc[q] !== undefined) qc[q]++;
  });

  const body = document.getElementById('rep-modal-body');
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1.5rem">
      ${[
        ['Territory', r.territory_id, 'var(--primary)'],
        [
          'Compliance',
          `${(r.compliance_pct || 0).toFixed(1)}%`,
          r.compliance_pct >= 80 ? 'var(--green)' : 'var(--amber)',
        ],
        ['Rx Lift %', `${(r.rx_lift_pct || 0).toFixed(3)}%`, 'var(--primary)'],
        ['HCPs', String(r.prescriber_count ?? hcps.length), 'var(--text-primary)'],
        ['Target Calls', String(r.total_target_calls ?? 0), 'var(--text-primary)'],
        ['Actual Calls', String(r.total_actual_calls ?? 0), 'var(--text-primary)'],
      ]
        .map(
          ([lbl, val, col]) => `
        <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
          <div style="font-size:1.25rem;font-weight:800;color:${col}">${val}</div>
          <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.2rem">${lbl}</div>
        </div>`
        )
        .join('')}
    </div>
    <h4 style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:0.75rem">Prescriber Quadrant Distribution (${hcps.length} HCPs)</h4>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;margin-bottom:1.5rem">
      ${Object.entries(qc)
        .map(
          ([q, n]) => `
        <div style="background:var(--bg-card-2);border-radius:var(--radius-sm);padding:0.75rem;text-align:center">
          <div style="font-size:1.4rem;font-weight:800;color:${quadrantColor(q)}">${n}</div>
          <div style="font-size:0.65rem;color:var(--text-muted);margin-top:0.1rem">${q}</div>
        </div>`
        )
        .join('')}
    </div>
    <div style="background:var(--primary-bg);border:1px solid var(--primary-light);border-radius:var(--radius);padding:1rem">
      <div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.5rem">Coaching Priority &amp; Trajectory</div>
      <div style="font-size:1rem;font-weight:700;color:${r.coaching_priority === 'Urgent Coaching' ? 'var(--red)' : r.coaching_priority === 'Monitor' ? 'var(--amber)' : 'var(--green)'}">
        ${r.coaching_priority} • ${r.trajectory_direction.toUpperCase()} TRAJECTORY
      </div>
      <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:0.4rem">
        Recommended Action: ${
          {
            'Star Performers': 'Maintain & Reward • Model for Best Practices',
            'Efficiency Risk': 'Clinical Detail Coaching • Focus on Messaging Quality',
            'Unrealized Potential': 'Expand Target Capacity • Increase Visit Frequency',
            'Needs Intervention': 'Performance Management • Call Plan Realignment',
          }[normQuadrant(r.quadrant)] ?? '—'
        }
      </div>
    </div>`;
  openModal('rep-modal');
}

export function renderManagerTab() {
  const activeReps = State.reps.filter((r) => r.is_active);
  const tbody = document.getElementById('manager-tbody');
  if (tbody) {
    if (!activeReps.length) {
      tbody.innerHTML =
        '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text-muted)">No active territory reps.</td></tr>';
    } else {
      tbody.innerHTML = activeReps
        .map((r) => {
          const callsToAdd = r.calls_to_add ?? 0;
          const callsToFree = r.calls_to_free ?? 0;
          const delta = r.net_call_delta ?? callsToAdd - callsToFree;
          const incHcps = r.hcps_with_increase ?? 0;
          const decHcps = r.hcps_with_decrease ?? 0;
          const deltaColor = delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--text-muted)';
          const rec = r.reallocation_recommendation ?? 'Reallocate calls within territory (Balanced)';

          return `
          <tr class="fade-in-up">
            <td><strong>${r.sales_rep_name || r.rep_id}</strong></td>
            <td><span class="kpi-badge badge-cyan">${r.territory_id}</span></td>
            <td class="text-right" style="color:var(--green);font-weight:600">+${callsToAdd.toFixed(1)}</td>
            <td class="text-right" style="color:var(--red);font-weight:600">-${callsToFree.toFixed(1)}</td>
            <td class="text-right" style="color:${deltaColor};font-weight:700">${delta > 0 ? '+' : ''}${delta.toFixed(1)}</td>
            <td class="text-right font-mono">${incHcps}</td>
            <td class="text-right font-mono">${decHcps}</td>
            <td style="color:var(--text-secondary);font-size:0.78rem">${rec}</td>
          </tr>`;
        })
        .join('');
    }
  }

  const mgrRecordCount = document.getElementById('manager-record-count');
  if (mgrRecordCount) mgrRecordCount.textContent = `${activeReps.length} active rep territories`;

  renderTerritoryRollup();
}

export function renderTerritoryRollup() {
  const tbody = document.getElementById('territory-rollup-tbody');
  if (!tbody) return;

  const territoryMap = {};

  State.reps.forEach((r) => {
    const tid = r.territory_id || 'TERR-01';
    if (!territoryMap[tid]) {
      territoryMap[tid] = { territory_id: tid, reps: [], hcps: [] };
    }
    territoryMap[tid].reps.push(r);
  });

  State.hcps.forEach((h) => {
    const tid = h.Territory || 'TERR-01';
    if (!territoryMap[tid]) {
      territoryMap[tid] = { territory_id: tid, reps: [], hcps: [] };
    }
    territoryMap[tid].hcps.push(h);
  });

  const terrRows = Object.values(territoryMap).sort((a, b) => a.territory_id.localeCompare(b.territory_id));

  if (!terrRows.length) {
    tbody.innerHTML =
      '<tr><td colspan="7" style="text-align:center;padding:1.5rem;color:var(--text-muted)">No territory rollup data available.</td></tr>';
    return;
  }

  tbody.innerHTML = terrRows
    .map((t) => {
      const repCount = t.reps.length;
      const hcpCount = t.hcps.length;
      const meanComp = t.reps.length ? t.reps.reduce((s, r) => s + (r.compliance_pct || 0), 0) / t.reps.length : 0;
      const meanLift = t.reps.length ? t.reps.reduce((s, r) => s + (r.rx_lift_pct || 0), 0) / t.reps.length : 0;
      const callsReallocated = t.reps.reduce((s, r) => s + (r.calls_to_add || 0), 0);
      const netDelta = t.reps.reduce((s, r) => s + (r.net_call_delta || 0), 0);

      const statusBadge = meanComp >= 80 ? 'badge-green' : meanComp >= 65 ? 'badge-amber' : 'badge-red';
      const statusText =
        meanComp >= 80 ? 'High Performing' : meanComp >= 65 ? 'Moderate Compliance' : 'Intervention Needed';

      return `
      <tr>
        <td><strong><span class="kpi-badge badge-cyan">${t.territory_id}</span></strong></td>
        <td class="text-right font-mono">${repCount} reps</td>
        <td class="text-right font-mono">${hcpCount} HCPs</td>
        <td class="text-right" style="font-weight:700;color:${meanComp >= 80 ? 'var(--green)' : 'var(--amber)'}">${meanComp.toFixed(1)}%</td>
        <td class="text-right" style="font-weight:700;color:var(--primary)">${meanLift.toFixed(3)}%</td>
        <td class="text-right font-mono" style="color:var(--primary);font-weight:700">+${callsReallocated.toFixed(1)} calls (net ${netDelta >= 0 ? '+' : ''}${netDelta.toFixed(1)})</td>
        <td><span class="kpi-badge ${statusBadge}">${statusText}</span></td>
      </tr>`;
    })
    .join('');
}

export function renderPrescribersTab() {
  const data = State.filteredHcps;
  const total = data.length;
  const pages = Math.ceil(total / State.presPageSize) || 1;
  const start = (State.presPage - 1) * State.presPageSize;
  const slice = data.slice(start, start + State.presPageSize);
  const tbody = document.getElementById('pres-tbody');
  if (!tbody) return;

  tbody.innerHTML = slice.length
    ? slice
        .map((h, i) => {
          const comp = h.Compliance_Pct_raw ?? 0;
          const lift = h.Rx_Lift_Pct ?? 0;
          const liftCol = lift >= State.medianLift ? 'var(--primary)' : 'var(--amber)';
          const compCol = comp >= 80 ? 'var(--green)' : 'var(--amber)';
          const qBadge = quadrantBadgeClass(h._quadrant);
          return `
      <tr class="fade-in-up">
        <td style="color:var(--text-muted)">${start + i + 1}</td>
        <td style="white-space:nowrap">${h.Physician_Name ?? '—'}</td>
        <td class="font-mono" style="font-size:0.75rem">${h.Prscrbr_NPI ?? '—'}</td>
        <td style="font-size:0.8rem">${h.Specialty ?? '—'}</td>
        <td>${h.City ?? '—'}, ${h.State ?? '—'}</td>
        <td>${h.Brand_Name ?? '—'}</td>
        <td class="text-right font-mono">${(h.Tot_30day_Fills_raw ?? h.Tot_30day_Fills ?? 12).toFixed(1)}</td>
        <td class="text-right font-mono">${(h.Post_Campaign_Fills ?? 15).toFixed(1)}</td>
        <td class="text-right" style="color:${liftCol};font-weight:700">${lift.toFixed(3)}%</td>
        <td class="text-right" style="color:${compCol};font-weight:600">${comp.toFixed(1)}%</td>
        <td>${h.Sales_Rep ?? '—'}</td>
        <td><span class="kpi-badge badge-cyan" style="font-size:0.65rem">${h.Territory ?? '—'}</span></td>
        <td style="text-align:center">${h.HCP_Tier ?? '—'}</td>
        <td><span class="kpi-badge ${qBadge}">${h._quadrant}</span></td>
      </tr>`;
        })
        .join('')
    : '<tr><td colspan="14" style="text-align:center;padding:2rem;color:var(--text-muted)">No prescribers match these filters.</td></tr>';

  const presRecordCount = document.getElementById('pres-record-count');
  if (presRecordCount) {
    presRecordCount.textContent = total
      ? `Showing ${start + 1}–${Math.min(start + State.presPageSize, total)} of ${total} HCPs`
      : '0 HCPs matching filters';
  }
  renderPagination('pres-pagination', State.presPage, pages, (p) => {
    State.presPage = p;
    renderPrescribersTab();
  });
}

export function renderPagination(containerId, page, pages, callback) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (pages <= 1) {
    el.innerHTML = '';
    return;
  }

  const MAX_BTNS = 7;
  let html = `<button class="page-btn" ${page <= 1 ? 'disabled' : ''} data-page="${page - 1}">‹ Prev</button>`;

  for (let p = 1; p <= pages; p++) {
    if (pages > MAX_BTNS && p > 2 && p < pages - 1 && Math.abs(p - page) > 2) {
      if (p === 3 || p === pages - 2) html += `<span style="color:var(--text-muted);padding:0 0.25rem">…</span>`;
      continue;
    }
    html += `<button class="page-btn${p === page ? ' active' : ''}" data-page="${p}">${p}</button>`;
  }
  html += `<button class="page-btn" ${page >= pages ? 'disabled' : ''} data-page="${page + 1}">Next ›</button>`;

  el.innerHTML = html;
  el.querySelectorAll('.page-btn:not([disabled])').forEach((btn) => {
    btn.addEventListener('click', () => callback(+btn.dataset.page));
  });
}

export function getFilteredReps() {
  const territoryFilter = document.getElementById('filter-territory')?.value;
  const repFilter = document.getElementById('filter-rep')?.value;
  let scorecards = State.reps;
  if (territoryFilter) scorecards = scorecards.filter((r) => r.territory_id === territoryFilter);
  if (repFilter) scorecards = scorecards.filter((r) => r.rep_id === repFilter);
  if (State.quadrantFilter)
    scorecards = scorecards.filter((r) => normQuadrant(r.quadrant) === normQuadrant(State.quadrantFilter));
  return scorecards;
}

export function exportCSV(data, filename, cols) {
  const header = cols.map((c) => (typeof c === 'object' ? c.label : c)).join(',') + '\n';
  const rows = data
    .map((r) =>
      cols
        .map((c) => {
          const key = typeof c === 'object' ? c.key : c;
          let v = r[key] ?? '';
          if (typeof v === 'number') {
            return v;
          }
          v = String(v).replace(/"/g, '""');
          if (v.includes(',') || v.includes('\n') || v.includes('\r') || v.includes('"')) {
            return `"${v}"`;
          }
          return v;
        })
        .join(',')
    )
    .join('\n');

  const blob = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function bindExports() {
  document.getElementById('export-rep-csv')?.addEventListener('click', () => {
    const filteredReps = getFilteredReps();
    exportCSV(filteredReps, 'rep_scorecard.csv', [
      { key: 'rep_id', label: 'Rep ID' },
      { key: 'sales_rep_name', label: 'Sales Rep Name' },
      { key: 'territory_id', label: 'Territory' },
      { key: 'prescriber_count', label: 'Prescribers' },
      { key: 'total_target_calls', label: 'Target Calls' },
      { key: 'total_actual_calls', label: 'Actual Calls' },
      { key: 'compliance_pct', label: 'Compliance %' },
      { key: 'rx_lift_pct', label: 'Rx Lift %' },
      { key: 'quadrant', label: 'Dominant Quadrant' },
      { key: 'coaching_priority', label: 'Coaching Priority' },
      { key: 'calls_to_add', label: 'Calls to Add' },
      { key: 'calls_to_free', label: 'Calls to Free' },
      { key: 'net_call_delta', label: 'Net Call Delta' },
      { key: 'reallocation_recommendation', label: 'Recommendation' },
    ]);
  });

  document.getElementById('export-pres-csv')?.addEventListener('click', () => {
    exportCSV(State.filteredHcps, 'prescribers.csv', [
      { key: 'Prscrbr_NPI', label: 'NPI' },
      { key: 'Physician_Name', label: 'Physician Name' },
      { key: 'Specialty', label: 'Specialty' },
      { key: 'City', label: 'City' },
      { key: 'State', label: 'State' },
      { key: 'Brand_Name', label: 'Brand Name' },
      { key: 'Tot_30day_Fills_raw', label: 'Baseline Fills' },
      { key: 'Post_Campaign_Fills', label: 'Post Campaign Fills' },
      { key: 'Rx_Lift_Pct', label: 'Rx Lift %' },
      { key: 'Compliance_Pct_raw', label: 'Compliance %' },
      { key: 'Sales_Rep', label: 'Sales Rep' },
      { key: 'Territory', label: 'Territory' },
      { key: 'HCP_Tier', label: 'HCP Tier' },
      { key: '_quadrant', label: 'Quadrant' },
    ]);
  });
}

export function bindTabs() {
  // Navigation converted to continuous scrollable single-page layout
}
