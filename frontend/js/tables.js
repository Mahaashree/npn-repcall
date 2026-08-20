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
  const testR2 = bestModel.test_r2 ?? 0.0;
  const bootCi = bestModel.bootstrap_ci ?? 'N/A';

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
  const pearsonR = den !== 0 ? num / den : 0.0;

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

  const bestModelLabel = State.ml?.best_model_summary?.model_label || 'Random Forest / XGBoost';
  const subtitleEl = document.querySelector('#matrix -previous-sibling-panel-subtitle, .panel-subtitle-attribution');
  const driverHeaderSub = document.getElementById('program-drivers-subtitle');
  if (driverHeaderSub) {
    driverHeaderSub.textContent = `Primary Driver Attribution (${bestModelLabel} Feature Importance)`;
  }

  if (!drivers.length) {
    const reason = State.attribution?.unavailable_reason;
    container.innerHTML = `<div style="grid-column:span 3;text-align:center;padding:1rem;color:var(--text-muted)">${reason || 'No attribution drivers available.'}</div>`;
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

export function getCadenceBadge(actual, target) {
  const actVal = Math.round(Number(actual) || 0);
  if (target !== undefined && target !== null && Number(target) > 0) {
    const tgtVal = Math.round(Number(target));
    const isGood = actVal >= tgtVal;
    const isWarning = !isGood && actVal >= tgtVal * 0.75;
    const cls = isGood ? 'status-pill-green' : isWarning ? 'status-pill-yellow' : 'status-pill-red';
    const dot = isGood ? '🟢' : isWarning ? '🟡' : '🔴';
    return `<span class="status-pill ${cls}">${dot} ${actVal} / ${tgtVal} calls/mo</span>`;
  }

  if (actVal >= 180 || (actVal >= 3.0 && actVal < 50)) {
    const label = actVal >= 50 ? `${actVal} calls/mo` : `${actVal} / mo`;
    return `<span class="status-pill status-pill-green">🟢 ${label}</span>`;
  } else if (actVal >= 120 || (actVal >= 2.0 && actVal < 50)) {
    const label = actVal >= 50 ? `${actVal} calls/mo` : `${actVal} / mo`;
    return `<span class="status-pill status-pill-yellow">🟡 ${label}</span>`;
  } else {
    const label = actVal >= 50 ? `${actVal} calls/mo` : `${actVal} / mo`;
    return `<span class="status-pill status-pill-red">🔴 ${label}</span>`;
  }
}

export function getSampleRatioBadge(actualSamples, totalVisits = 1.0) {
  const actVal = Number(actualSamples) || 0;
  const tgtVal = Number(totalVisits) || 1.0;

  // If totalVisits is > 1.0, it represents total actual visits count
  if (tgtVal > 1.0) {
    const samples = Math.round(actVal);
    const visits = Math.round(tgtVal);
    const isGood = samples >= visits;
    const isWarning = !isGood && samples >= visits * 0.5;
    const cls = isGood ? 'status-pill-green' : isWarning ? 'status-pill-yellow' : 'status-pill-red';
    const dot = isGood ? '🟢' : isWarning ? '🟡' : '🔴';
    return `<span class="status-pill ${cls}">${dot} ${samples} / ${visits} samples dropped</span>`;
  }

  // Fallback for single-visit ratio
  const isGood = actVal >= tgtVal;
  const isWarning = !isGood && actVal >= tgtVal * 0.5;
  const cls = isGood ? 'status-pill-green' : isWarning ? 'status-pill-yellow' : 'status-pill-red';
  const dot = isGood ? '🟢' : isWarning ? '🟡' : '🔴';
  return `<span class="status-pill ${cls}">${dot} ${actVal.toFixed(2)} / ${tgtVal.toFixed(2)} per visit</span>`;
}

export function getBaselineVolumeBadge(actualFills, targetFills = 20.0) {
  const actFills = Math.round(Number(actualFills) || 0);
  const tgtFills = Math.round(Number(targetFills) || 20.0);
  const isGood = actFills >= tgtFills;
  const isWarning = !isGood && actFills >= tgtFills * 0.75;
  const cls = isGood ? 'status-pill-green' : isWarning ? 'status-pill-yellow' : 'status-pill-red';
  const dot = isGood ? '🟢' : isWarning ? '🟡' : '🔴';
  return `<span class="status-pill ${cls}">${dot} ${actFills} / ${tgtFills} total fills</span>`;
}

export function getComplianceBadge(actualPct, targetPct = 80.0) {
  const actVal = Math.round(Number(actualPct) || 0);
  const tgtVal = Math.round(Number(targetPct) || 80.0);
  const isGood = actVal >= tgtVal;
  const isWarning = !isGood && actVal >= 70.0;
  const cls = isGood ? 'status-pill-green' : isWarning ? 'status-pill-yellow' : 'status-pill-red';
  const dot = isGood ? '🟢' : isWarning ? '🟡' : '🔴';
  return `<span class="status-pill ${cls}">${dot} ${actVal}% / ${tgtVal}%</span>`;
}

export function getRxLiftBadge(lift) {
  const val = Number(lift) || 0;
  const sign = val >= 0 ? '+' : '';
  if (val >= 4.5) {
    return `<span class="status-pill status-pill-green">🟢 ${sign}${val.toFixed(2)}%</span>`;
  } else if (val >= 2.5) {
    return `<span class="status-pill status-pill-yellow">🟡 ${sign}${val.toFixed(2)}%</span>`;
  } else {
    return `<span class="status-pill status-pill-red">🔴 ${sign}${val.toFixed(2)}%</span>`;
  }
}

export function renderRepTab() {
  const territoryFilter = document.getElementById('filter-territory')?.value;
  const repFilter = document.getElementById('filter-rep')?.value;
  const isCei = State.matrixMode === 'cei';

  let scorecards = State.reps;
  if (territoryFilter) scorecards = scorecards.filter((r) => r.territory_id === territoryFilter);
  if (repFilter) scorecards = scorecards.filter((r) => r.rep_id === repFilter);
  if (State.quadrantFilter)
    scorecards = scorecards.filter((r) => {
      const q = isCei ? normQuadrant(r.dominant_quadrant_cei || r.quadrant, 'cei') : normQuadrant(r.quadrant, 'legacy');
      return q === normQuadrant(State.quadrantFilter, State.matrixMode);
    });

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
        const lift = r.rx_lift_pct ?? 0;
        const actualCalls = r.total_actual_calls ?? 0;
        const targetCalls = r.total_target_calls ?? 0;
        const samples = r.samples ?? 0;

        // 4 Driver Whole Integer Metrics
        const cadence = Math.round(r.monthly_cadence ?? (actualCalls / 3.0));
        const targetCadence = Math.round(r.target_monthly_cadence ?? (targetCalls / 3.0));

        // Driver-based coaching action & priority
        let priority = r.coaching_priority;
        let actionFlag = r.action_flag;
        let recText = r.driver_recommendation || r.reallocation_recommendation;

        if (!recText || !actionFlag) {
          if (lift >= 4.5 && cadence >= targetCadence) {
            priority = 'On Track';
            actionFlag = '🟢 Maintain & Scale';
            recText = `Top Performer: Exceeding targets (${cadence}/${targetCadence} monthly calls, ${samples}/${actualCalls} samples dropped, +${lift.toFixed(2)}% Rx Lift). Share detailing best practices across territory.`;
          } else if (lift >= 4.5 && cadence < targetCadence) {
            priority = 'Monitor';
            actionFlag = '🟡 Efficiency Optimization';
            recText = `High Return, Low Volume: High prescriber responsiveness. ${r.sales_rep_name || r.rep_id} completed ${cadence} of ${targetCadence} target monthly calls and dropped ${samples} samples across ${actualCalls} visits. Increase visit volume to ${targetCadence} calls/mo and ensure 1 sample per visit to maximize total adoption.`;
          } else if (lift >= 2.5 && lift < 4.5) {
            priority = 'Monitor';
            actionFlag = '🟡 Targeting Refinement';
            recText = `Moderate Lift: On track with ${cadence}/${targetCadence} monthly calls. Refine call planning and sample distribution (${samples}/${actualCalls} samples) toward top-tier physicians.`;
          } else if (lift < 2.5 && (cadence < targetCadence || samples < actualCalls)) {
            priority = 'Urgent Coaching';
            actionFlag = '🔴 Urgent Coaching';
            recText = `Driver Deficit: Falling short of call target (${cadence} vs ${targetCadence} monthly calls) and sample target (${samples} vs ${actualCalls} samples dropped across visits). Prioritize doctor visit cadence.`;
          } else {
            priority = 'Monitor';
            actionFlag = '🟡 Performance Review';
            recText = `Review Detailing Quality: Completed ${cadence}/${targetCadence} monthly calls and ${samples}/${actualCalls} samples dropped. Optimize detailing message and targeting.`;
          }
        }

        const priColor =
          actionFlag?.includes('🔴') || priority === 'Urgent Coaching'
            ? 'badge-red'
            : actionFlag?.includes('🟡') || priority === 'Monitor'
              ? 'badge-amber'
              : 'badge-green';

        const domNorm = isCei
          ? normQuadrant(r.dominant_quadrant_cei || r.quadrant, 'cei')
          : normQuadrant(r.quadrant, 'legacy');
        const domCls = quadrantBadgeClass(domNorm);

        const activeBadge = r.is_active
          ? ''
          : ' <span class="tab-badge" style="background:var(--red-bg);color:var(--red-text)">Inactive</span>';

        return `
        <tr data-rep="${r.rep_id}" style="cursor:pointer" tabindex="0" role="row" aria-label="Sales rep ${r.sales_rep_name || r.rep_id}">
          <td class="font-mono"><strong>${r.rep_id}</strong></td>
          <td><strong>${r.sales_rep_name || r.rep_id}</strong>${activeBadge}</td>
          <td><span class="kpi-badge badge-cyan">${r.territory_id}</span></td>
          <td class="num">${r.prescriber_count ?? 1}</td>
          <td>${getCadenceBadge(cadence, targetCadence)}</td>
          <td>${getSampleRatioBadge(samples, actualCalls)}</td>
          <td>${getRxLiftBadge(lift)}</td>
          <td><span class="kpi-badge ${domCls}">${domNorm}</span></td>
          <td><span class="kpi-badge ${priColor}">${actionFlag || priority}</span></td>
          <td style="max-width:240px;font-size:0.75rem;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${recText}">
            ${recText}
          </td>
          <td>
            <button class="btn-primary" style="padding:0.25rem 0.6rem;font-size:0.72rem" onclick="window.openRepModal('${r.rep_id}')">
              Coaching Report
            </button>
          </td>
        </tr>`;
      })
      .join('');
  }

  const recCount = document.getElementById('rep-record-count');
  if (recCount) {
    recCount.textContent = `Showing ${start + 1}–${Math.min(start + State.repPageSize, total)} of ${total} reps`;
  }

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
  const isCei = State.matrixMode === 'cei';
  document.getElementById('rep-modal-title').textContent =
    `${r.sales_rep_name || r.rep_id} (${r.rep_id}) — Explainable AI Coaching Report`;

  // Driver weights: look up by the SAME exact feature key the Program Drivers
  // panel uses (State.attribution.global_importance), never by array position.
  const importanceOf = (featureKey) => {
    const found = (State.attribution?.global_importance || []).find((d) => d.feature === featureKey);
    return found && typeof found.importance_pct === 'number' ? found.importance_pct : null;
  };
  const wCadence = importanceOf('Monthly Call Frequency');
  const wSamples = importanceOf('Sample Call Ratio');
  const wBaseline = importanceOf('Baseline Volume Saturation');
  const withWeight = (label, w) =>
    w == null ? label : `${label} (${w.toFixed(1)}% Weight)`;

  const hcps = State.hcps.filter((h) => h.Sales_Rep === repId);
  const qc = isCei
    ? { 'Star Performers': 0, 'Efficient High-Performers': 0, 'Targeting Risk': 0, 'Needs Intervention': 0 }
    : { 'Star Performers': 0, 'Efficiency Risk': 0, 'Unrealized Potential': 0, 'Needs Intervention': 0 };

  hcps.forEach((h) => {
    const q = normQuadrant(h._quadrant, State.matrixMode);
    if (qc[q] !== undefined) qc[q]++;
  });

  const actualCalls = r.total_actual_calls ?? 0;
  const targetCalls = r.total_target_calls ?? 0;
  const hcpCount = r.prescriber_count ?? hcps.length ?? 1;
  const samples = r.samples ?? 0;

  const cadence = Math.round(r.monthly_cadence ?? (actualCalls / 3.0));
  const targetCadence = Math.round(r.target_monthly_cadence ?? (targetCalls / 3.0));

  const baselineVol = Math.round(r.baseline_volume ?? (hcpCount * 20.0));
  const targetBaselineVol = Math.round(r.target_baseline_volume ?? (hcpCount * 20.0));

  const compPct = Math.round(r.compliance_pct ?? (actualCalls / Math.max(1, targetCalls) * 100.0));
  const targetCompPct = Math.round(r.target_compliance_pct ?? 80);
  const ceiScore = r.cei_score ?? 75.0;

  const lift = r.rx_lift_pct ?? 0;

  // Balanced Driver-based coaching logic
  let actionFlag = r.action_flag;
  let recText = r.driver_recommendation || r.reallocation_recommendation;
  let priorityCls = 'var(--amber)';

  if (!recText || !actionFlag) {
    if (lift >= 4.5 && cadence >= targetCadence) {
      actionFlag = '🟢 Maintain & Scale';
      recText = `Top Performer: Exceeding targets (${cadence}/${targetCadence} monthly calls, ${samples}/${actualCalls} samples dropped, +${lift.toFixed(2)}% Rx Lift). Share detailing best practices across territory.`;
      priorityCls = 'var(--green)';
    } else if (lift >= 4.5 && cadence < targetCadence) {
      actionFlag = '🟡 Efficiency Optimization';
      recText = `High Return, Low Volume: High prescriber responsiveness. ${r.sales_rep_name || r.rep_id} completed ${cadence} of ${targetCadence} target monthly calls and dropped ${samples} samples across ${actualCalls} visits. Increase visit volume to ${targetCadence} calls/mo and ensure 1 sample per visit to maximize total adoption.`;
      priorityCls = 'var(--amber)';
    } else if (lift >= 2.5 && lift < 4.5) {
      actionFlag = '🟡 Targeting Refinement';
      recText = `Moderate Lift: On track with ${cadence}/${targetCadence} monthly calls. Refine call planning and sample distribution (${samples}/${actualCalls} samples) toward top-tier physicians.`;
      priorityCls = 'var(--amber)';
    } else if (lift < 2.5 && (cadence < targetCadence || samples < actualCalls)) {
      actionFlag = '🔴 Urgent Coaching';
      recText = `Driver Deficit: Falling short of call target (${cadence} vs ${targetCadence} monthly calls) and sample target (${samples} vs ${actualCalls} samples dropped across visits). Prioritize doctor visit cadence.`;
      priorityCls = 'var(--red)';
    } else {
      actionFlag = '🟡 Performance Review';
      recText = `Review Detailing Quality: Completed ${cadence}/${targetCadence} monthly calls and ${samples}/${actualCalls} samples dropped. Optimize detailing message and targeting.`;
      priorityCls = 'var(--amber)';
    }
  } else {
    priorityCls = actionFlag.includes('🟢') ? 'var(--green)' : actionFlag.includes('🔴') ? 'var(--red)' : 'var(--amber)';
  }

  const body = document.getElementById('rep-modal-body');
  body.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1.5rem">
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.1rem;font-weight:800;color:var(--primary)"><span class="kpi-badge badge-cyan">${r.territory_id}</span></div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">Assigned Territory</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.0rem;font-weight:800">${getCadenceBadge(cadence, targetCadence)}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">${withWeight('Monthly Cadence', wCadence)}</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.0rem;font-weight:800">${getSampleRatioBadge(samples, actualCalls)}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">${withWeight('Sample Drop Volume', wSamples)}</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.0rem;font-weight:800">${getRxLiftBadge(lift)}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">Rx Lift % (Primary Outcome)</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.0rem;font-weight:800">${getBaselineVolumeBadge(baselineVol, targetBaselineVol)}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">${withWeight('Territory Baseline Volume', wBaseline)}</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.0rem;font-weight:800"><span class="status-pill status-pill-green">⚡ ${ceiScore.toFixed(1)}%</span></div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.3rem">AI Composite Execution Index (CEI)</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center">
        <div style="font-size:1.25rem;font-weight:800;color:var(--text-primary)">${String(hcpCount)}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.2rem">Assigned HCPs</div>
      </div>
      <div style="background:var(--bg-card-2);border-radius:var(--radius);padding:1rem;text-align:center;grid-column:span 2">
        <div style="font-size:1.25rem;font-weight:800;color:var(--text-primary)">${String(actualCalls)} / ${String(targetCalls)} Total Campaign Calls</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.2rem">Campaign Call Plan Progress (${compPct}% Attainment)</div>
      </div>
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
    <div style="background:var(--primary-bg);border:1px solid var(--primary-light);border-radius:var(--radius);padding:1.2rem">
      <div style="font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.4rem">Explainable AI Coaching Recommendation</div>
      <div style="font-size:1.05rem;font-weight:800;color:${priorityCls};display:flex;align-items:center;gap:0.5rem">
        <span>${actionFlag}</span> • <span style="font-size:0.85rem;text-transform:uppercase">${(r.trajectory_direction || 'stable').toUpperCase()} TRAJECTORY</span>
      </div>
      <div style="font-size:0.88rem;color:var(--text-primary);margin-top:0.6rem;font-weight:600">
        ${recText}
      </div>
      <div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.4rem">
        Key Bottleneck Driver: ${r.driver_bottleneck || (cadence < targetCadence ? `Monthly call cadence (${cadence} calls/mo) below ${targetCadence} target` : `Sample drop deficit (${samples} vs ${actualCalls} visits)`)}
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
      { key: 'monthly_cadence', label: 'Monthly Cadence (Visits/Mo)' },
      { key: 'sample_ratio', label: 'Sample Drop Ratio (Samples/Visit)' },
      { key: 'rx_lift_pct', label: 'Rx Lift %' },
      { key: 'quadrant', label: 'Dominant Quadrant' },
      { key: 'action_flag', label: 'Coaching Status' },
      { key: 'driver_bottleneck', label: 'Driver Bottleneck' },
      { key: 'driver_recommendation', label: 'Action Recommendation' },
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
  // Navigation handled by SPA hash routing in app.js (renderPage)
}
