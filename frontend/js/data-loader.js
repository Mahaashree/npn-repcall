/**
 * js/data-loader.js
 * State management, manifest-first data fetching, and Web Crypto SHA-256 validation.
 */

export const State = {
  reps: [], // all rep records from reps.json
  hcps: [], // all HCP records from scatter_points.json
  filteredHcps: [], // after quadrant + filter suite
  ml: null, // ml_results.json
  attribution: null, // attribution.json
  coachingQueue: [], // coaching_queue.json
  telemetry: null, // pipeline_telemetry.json
  manifest: null, // manifest.json
  quadrantFilter: null, // 'Star Performers'|'Efficiency Risk'|'Unrealized Potential'|'Needs Intervention'|null
  sortKey: null,
  sortDir: 'asc',
  repPage: 1,
  repPageSize: 25,
  presPage: 1,
  presPageSize: 25,
  coachingPage: 1,
  coachingPageSize: 10,
  medianLift: 0,
  scatterChart: null,
  importanceChart: null,
  shapChart: null,
  activeModelKey: null,
  showShap: false,
  isLoading: true,
  loadError: null,
};

export const fmt = {
  pct: (v) => (v == null ? '—' : `${(+v).toFixed(1)}%`),
  pct2: (v) => (v == null ? '—' : `${(+v).toFixed(2)}%`),
  num: (v) => (v == null ? '—' : (+v).toLocaleString()),
  dec: (v, d = 4) => (v == null ? '—' : (+v).toFixed(d)),
  r2: (v) => (v == null ? '—' : `${(+v * 100).toFixed(1)}%`),
  money: (v) =>
    v == null ? '—' : `$${(+v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
};

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

export function normQuadrant(q) {
  if (!q) return q;
  const map = {
    Stars: 'Star Performers',
    'Star Performers': 'Star Performers',
    Ineffective: 'Efficiency Risk',
    'Efficiency Risk': 'Efficiency Risk',
    Underserved: 'Unrealized Potential',
    'Unrealized Potential': 'Unrealized Potential',
    'At-Risk': 'Needs Intervention',
    'Needs Intervention': 'Needs Intervention',
  };
  return map[q] || q;
}

export function classifyQuadrant(compliancePct, rxLift, medianLift) {
  const highComp = compliancePct >= 80;
  const highLift = rxLift >= medianLift;
  if (highComp && highLift) return 'Star Performers';
  if (highComp && !highLift) return 'Efficiency Risk';
  if (!highComp && highLift) return 'Unrealized Potential';
  return 'Needs Intervention';
}

export function quadrantColor(q) {
  const n = normQuadrant(q);
  return (
    {
      'Star Performers': 'var(--green)',
      'Efficiency Risk': 'var(--amber)',
      'Unrealized Potential': 'var(--cyan)',
      'Needs Intervention': 'var(--red)',
    }[n] || 'var(--text-muted)'
  );
}

export function quadrantBadgeClass(q) {
  const n = normQuadrant(q);
  return (
    {
      'Star Performers': 'badge-stars',
      'Efficiency Risk': 'badge-ineffective',
      'Unrealized Potential': 'badge-underserved',
      'Needs Intervention': 'badge-at-risk',
    }[n] || ''
  );
}

export async function computeSha256(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function fetchAndVerifyJson(filename, expectedSha256, basePath) {
  const fileUrl = `${basePath}/${filename}`;
  const resp = await fetch(fileUrl);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} - Failed to fetch ${fileUrl}`);
  }
  const text = await resp.text();

  if (expectedSha256) {
    const actualSha256 = await computeSha256(text);
    if (actualSha256.toLowerCase() !== expectedSha256.toLowerCase()) {
      throw new Error(
        `Checksum mismatch for ${filename}: expected ${expectedSha256.slice(0, 8)}..., got ${actualSha256.slice(0, 8)}...`
      );
    }
  }

  return JSON.parse(text);
}

export async function loadAllData(renderSkeletonsCb, renderErrorStateCb) {
  State.isLoading = true;
  State.loadError = null;
  if (renderSkeletonsCb) renderSkeletonsCb();

  try {
    const isFrontendSubdir = window.location.pathname.includes('/frontend/');
    const primaryPath = isFrontendSubdir ? '../dashboard/data' : 'dashboard/data';
    const candidatePaths = [primaryPath, 'dashboard/data', '../dashboard/data', 'data', '.'];
    let manifestData = null;
    let validBasePath = 'dashboard/data';

    for (const path of candidatePaths) {
      try {
        const resp = await fetch(`${path}/manifest.json`);
        if (resp.ok) {
          manifestData = await resp.json();
          validBasePath = path;
          break;
        }
      } catch (_e) {}
    }

    if (!manifestData) {
      throw new Error('Could not locate or fetch manifest.json in dashboard/data/');
    }

    State.manifest = manifestData;
    const fileMap = {};
    (manifestData.files || []).forEach((f) => {
      fileMap[f.filename] = f.sha256;
    });

    const [repsRes, mlRes, attrRes, scatterRes, queueRes, telRes] = await Promise.all([
      fetchAndVerifyJson('reps.json', fileMap['reps.json'], validBasePath),
      fetchAndVerifyJson('ml_results.json', fileMap['ml_results.json'], validBasePath),
      fetchAndVerifyJson('attribution.json', fileMap['attribution.json'], validBasePath),
      fetchAndVerifyJson('scatter_points.json', fileMap['scatter_points.json'], validBasePath),
      fetchAndVerifyJson('coaching_queue.json', fileMap['coaching_queue.json'], validBasePath),
      fetchAndVerifyJson('pipeline_telemetry.json', fileMap['pipeline_telemetry.json'], validBasePath),
    ]);

    State.reps = repsRes.data || repsRes;
    State.ml = mlRes;
    State.attribution = attrRes;
    State.hcps = scatterRes.data || scatterRes;
    State.coachingQueue = queueRes.data || queueRes;
    State.telemetry = telRes;

    const priWeight = { urgent: 1, monitor: 2, on_track: 3 };
    State.coachingQueue.sort((a, b) => (priWeight[a.priority] || 99) - (priWeight[b.priority] || 99));

    const lifts = State.hcps.map((h) => h.rx_lift_pct ?? h.Rx_Lift_Pct ?? 0).sort((a, b) => a - b);
    State.medianLift = lifts.length ? lifts[Math.floor(lifts.length / 2)] : 3.89;

    State.hcps = State.hcps.map((h) => ({
      ...h,
      Physician_Name: h.physician_name ?? h.Physician_Name,
      Prscrbr_NPI: h.npi ?? h.Prscrbr_NPI,
      Specialty: h.specialty ?? h.Specialty,
      City: h.city ?? h.City ?? '—',
      State: h.state ?? h.State ?? '—',
      Brand_Name: h.brand_name ?? h.Brand_Name ?? '—',
      Tot_30day_Fills_raw: h.tot_30day_fills ?? h.Tot_30day_Fills_raw ?? h.Tot_30day_Fills ?? 0,
      Post_Campaign_Fills: h.post_campaign_fills ?? h.Post_Campaign_Fills ?? 0,
      Territory: h.territory_id ?? h.Territory,
      Sales_Rep: h.rep_id ?? h.Sales_Rep,
      HCP_Tier: h.hcp_tier ?? h.HCP_Tier,
      Compliance_Pct_raw: h.compliance_pct ?? h.Compliance_Pct_raw ?? 0,
      Rx_Lift_Pct: h.rx_lift_pct ?? h.Rx_Lift_Pct ?? 0,
      _quadrant: normQuadrant(
        h.quadrant ?? classifyQuadrant(h.compliance_pct ?? 0, h.rx_lift_pct ?? 0, State.medianLift)
      ),
    }));
    State.filteredHcps = [...State.hcps];

    State.isLoading = false;
    return true;
  } catch (err) {
    console.error('Data loading error:', err);
    State.isLoading = false;
    State.loadError = err.message || 'Error fetching dashboard data';
    if (renderErrorStateCb) renderErrorStateCb(State.loadError);
    return false;
  }
}
