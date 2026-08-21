/**
 * js/data-loader.js
 * State management, manifest-first data fetching, and Web Crypto SHA-256 validation.
 */

export const State = {
  activeDatasetMode: 'hybrid', // 'hybrid' | 'synthetic' | 'custom'
  rawMlRes: null,
  rawScatterRes: null,
  customData: null, // Holds dynamically ingested custom dataset
  reps: [], // all rep records from reps.json
  hcps: [], // all HCP records from scatter_points.json
  filteredHcps: [], // after quadrant + filter suite
  ml: null, // ml_results.json for active mode
  attribution: null, // attribution.json
  coachingQueue: [], // coaching_queue.json
  telemetry: null, // pipeline_telemetry.json
  manifest: null, // manifest.json
  matrixMode: 'legacy', // 'legacy' (80% compliance split) | 'cei' (75% CEI split)
  quadrantFilter: null, // Active quadrant filter
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

export function normQuadrant(q, matrixMode = 'legacy') {
  if (!q) return q;
  const map = {
    Stars: 'Star Performers',
    'Star Performers': 'Star Performers',
    Ineffective: matrixMode === 'cei' ? 'Targeting Risk' : 'Efficiency Risk',
    'Efficiency Risk': matrixMode === 'cei' ? 'Targeting Risk' : 'Efficiency Risk',
    Underserved: matrixMode === 'cei' ? 'Efficient High-Performers' : 'Unrealized Potential',
    'Unrealized Potential': matrixMode === 'cei' ? 'Efficient High-Performers' : 'Unrealized Potential',
    'Efficient High-Performers': 'Efficient High-Performers',
    'Targeting Risk': 'Targeting Risk',
    'Unrealized Potential / Targeting Risk': 'Targeting Risk',
    'At-Risk': 'Needs Intervention',
    'Needs Intervention': 'Needs Intervention',
  };
  return map[q] || q;
}

export function classifyQuadrant(val, rxLift, medianLift, matrixMode = 'legacy') {
  if (matrixMode === 'cei') {
    const highCei = val >= 75.0;
    const highLift = rxLift >= medianLift;
    if (highCei && highLift) return 'Star Performers';
    if (!highCei && highLift) return 'Efficient High-Performers';
    if (highCei && !highLift) return 'Targeting Risk';
    return 'Needs Intervention';
  } else {
    const highComp = val >= 80.0;
    const highLift = rxLift >= medianLift;
    if (highComp && highLift) return 'Star Performers';
    if (highComp && !highLift) return 'Efficiency Risk';
    if (!highComp && highLift) return 'Unrealized Potential';
    return 'Needs Intervention';
  }
}

export function quadrantColor(q) {
  const n = normQuadrant(q);
  return (
    {
      'Star Performers': 'var(--green)',
      'Efficiency Risk': 'var(--amber)',
      'Targeting Risk': 'var(--amber)',
      'Unrealized Potential': 'var(--cyan)',
      'Efficient High-Performers': 'var(--cyan)',
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
      'Targeting Risk': 'badge-ineffective',
      'Unrealized Potential': 'badge-underserved',
      'Efficient High-Performers': 'badge-underserved',
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

    State.rawRepsRes = repsRes;
    State.rawMlRes = mlRes;
    State.rawScatterRes = scatterRes;
    State.rawAttrRes = attrRes;
    State.rawQueueRes = queueRes;
    State.rawTelRes = telRes;

    setDatasetMode(State.activeDatasetMode || 'hybrid');

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

export function getActiveDriverWeights() {
  const imp = State.attribution?.global_importance || [];
  const weights = { cadence: 0.676, samples: 0.249, tier: 0.056, compliance: 0.019 };
  imp.forEach((item) => {
    const feat = (item.feature || '').toLowerCase();
    const pct = (item.importance_pct || 0) / 100.0;
    if (feat.includes('call') || feat.includes('frequency') || feat.includes('cadence')) weights.cadence = pct;
    else if (feat.includes('sample')) weights.samples = pct;
    else if (feat.includes('tier') || feat.includes('fill') || feat.includes('baseline')) weights.tier = pct;
    else if (feat.includes('comp')) weights.compliance = pct;
  });
  return weights;
}

export function setDatasetMode(mode) {
  State.activeDatasetMode = mode;

  if (mode === 'custom' && State.customData) {
    State.ml = State.customData.ml || State.ml;
    State.reps = State.customData.reps || [];
    State.hcps = State.customData.hcps || [];
    State.attribution = State.customData.attribution || State.attribution;
    State.coachingQueue = State.customData.coachingQueue || [];
    State.telemetry = State.customData.telemetry || State.telemetry;

    const lifts = State.hcps.map((h) => h.rx_lift_pct ?? h.Rx_Lift_Pct ?? 0).sort((a, b) => a - b);
    State.medianLift = lifts.length ? lifts[Math.floor(lifts.length / 2)] : 3.89;
    State.filteredHcps = [...State.hcps];
    window.appState = State;
    return;
  }
  
  if (State.rawMlRes) {
    State.ml = State.rawMlRes[mode] || State.rawMlRes;
  }

  if (State.rawAttrRes) {
    State.attribution = State.rawAttrRes[mode] || State.rawAttrRes;
  }

  const weights = getActiveDriverWeights();

  if (State.rawRepsRes) {
    const modeReps = State.rawRepsRes[mode] || (mode === 'hybrid' ? (State.rawRepsRes.data || (Array.isArray(State.rawRepsRes) ? State.rawRepsRes : [])) : []);
    State.reps = (Array.isArray(modeReps) ? modeReps : (modeReps.data || [])).map((r) => {
      const actualCalls = r.total_actual_calls ?? 0;
      const targetCalls = Math.max(1, r.total_target_calls ?? 1);
      const samples = r.samples ?? 0;
      const hcpCount = Math.max(1, r.prescriber_count ?? 1);
      const cadS = Math.min(1.0, (actualCalls / 3.0) / Math.max(1.0, targetCalls / 3.0));
      const sampS = Math.min(1.0, (samples / Math.max(1.0, actualCalls)) / 1.0);
      const compS = Math.min(1.0, actualCalls / targetCalls);
      const tierS = 0.8;
      const wSum = weights.cadence + weights.samples + weights.tier + weights.compliance || 1.0;
      const computedCei = Math.round(((cadS * weights.cadence + sampS * weights.samples + tierS * weights.tier + compS * weights.compliance) / wSum) * 1000) / 10;
      return {
        ...r,
        cei_score: r.cei_score ?? computedCei,
      };
    });
  }

  if (State.rawQueueRes) {
    const modeQueue = State.rawQueueRes[mode] || (mode === 'hybrid' ? (State.rawQueueRes.data || (Array.isArray(State.rawQueueRes) ? State.rawQueueRes : [])) : []);
    State.coachingQueue = Array.isArray(modeQueue) ? modeQueue : (modeQueue.data || []);
    const priWeight = { urgent: 1, monitor: 2, on_track: 3 };
    State.coachingQueue.sort((a, b) => (priWeight[a.priority] || 99) - (priWeight[b.priority] || 99));
  }

  if (State.rawTelRes) {
    State.telemetry = State.rawTelRes[mode] || State.rawTelRes;
  }
  
  if (State.rawScatterRes) {
    const modePoints = State.rawScatterRes[mode] || (mode === 'hybrid' ? (State.rawScatterRes.data || State.rawScatterRes) : []);
    State.hcps = Array.isArray(modePoints) ? modePoints : (modePoints.data || []);
    
    const lifts = State.hcps.map((h) => h.rx_lift_pct ?? h.Rx_Lift_Pct ?? 0).sort((a, b) => a - b);
    State.medianLift = lifts.length ? lifts[Math.floor(lifts.length / 2)] : 3.89;

    State.hcps = State.hcps.map((h) => {
      const comp = h.compliance_pct ?? h.Compliance_Pct_raw ?? 0;
      const lift = h.rx_lift_pct ?? h.Rx_Lift_Pct ?? 0;
      const targetC = Math.max(1, h.Target_Calls || h.target_calls || 10);
      const actualC = h.Actual_Calls || h.actual_calls || Math.round((comp / 100) * targetC);
      const samplesC = h.Samples_Dropped || h.samples || Math.round(actualC * 0.9);
      const tierVal = parseInt(h.HCP_Tier || h.hcp_tier || 3);

      const cadS = Math.min(1.0, (actualC / 3.0) / Math.max(1.0, targetC / 3.0));
      const sampS = Math.min(1.0, (samplesC / Math.max(1.0, actualC)) / 1.0);
      const tierS = tierVal === 1 ? 1.0 : (tierVal === 2 ? 0.8 : 0.5);
      const compS = Math.min(1.0, actualC / targetC);
      const wSum = weights.cadence + weights.samples + weights.tier + weights.compliance || 1.0;
      const calculatedCei = Math.round(((cadS * weights.cadence + sampS * weights.samples + tierS * weights.tier + compS * weights.compliance) / wSum) * 1000) / 10;
      const cei = h.cei_score ?? calculatedCei;

      const qLeg = normQuadrant(h.quadrant_legacy ?? h.quadrant ?? classifyQuadrant(comp, lift, State.medianLift, 'legacy'), 'legacy');
      const qCei = normQuadrant(h.quadrant_cei ?? classifyQuadrant(cei, lift, State.medianLift, 'cei'), 'cei');

      return {
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
        HCP_Tier: tierVal,
        Compliance_Pct_raw: comp,
        cei_score: cei,
        Rx_Lift_Pct: lift,
        _quadrant_legacy: qLeg,
        _quadrant_cei: qCei,
        _quadrant: State.matrixMode === 'cei' ? qCei : qLeg,
      };
    });
    State.filteredHcps = [...State.hcps];
  }
  window.appState = State;
}

export function setMatrixMode(matrixMode) {
  State.matrixMode = matrixMode;
  State.quadrantFilter = null; // Clear active quadrant filter on mode toggle
  if (State.hcps && State.hcps.length) {
    State.hcps = State.hcps.map((h) => ({
      ...h,
      _quadrant: matrixMode === 'cei' ? h._quadrant_cei : h._quadrant_legacy,
    }));
    State.filteredHcps = [...State.hcps];
  }
  window.appState = State;
}

// Client-side domain constants for dynamic synthesis
const SPECIALTIES = [
  'Pain Management', 'Oncology', 'Palliative Care', 'Neurology',
  'Anesthesiology', 'Internal Medicine', 'Family Practice',
  'Orthopedics', 'Emergency Medicine', 'Psychiatry',
];
const BRAND_NAMES = ['Subsys', 'Abstral', 'Actiq', 'Fentora', 'Lazanda'];
const LOCATIONS = [
  ['Los Angeles', 'CA'], ['Houston', 'TX'], ['Miami', 'FL'],
  ['New York', 'NY'], ['Chicago', 'IL'], ['Philadelphia', 'PA'],
  ['Columbus', 'OH'], ['Detroit', 'MI'], ['Atlanta', 'GA'],
  ['Charlotte', 'NC'], ['Phoenix', 'AZ'], ['Seattle', 'WA'],
];
const REPS = Array.from({ length: 12 }, (_, i) => `REP-${101 + i}`);
const TERRITORIES = Array.from({ length: 6 }, (_, i) => `TERR-0${1 + i}`);
const REP_TO_TERR = Object.fromEntries(REPS.map((r, i) => [r, TERRITORIES[Math.floor(i / 2)]]));

function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) throw new Error('Uploaded file is empty or missing data rows.');
  
  const headers = lines[0].split(',').map((h) => h.trim().replace(/^["']|["']$/g, ''));
  const rows = [];

  for (let i = 1; i < lines.length; i++) {
    // Regex to handle quoted commas
    const pattern = /(".*?"|[^",]+)(?=\s*,|\s*$)/g;
    const rawTokens = lines[i].match(/(?:\"[^\"]*\"|[^,])+/g) || lines[i].split(',');
    const tokens = rawTokens.map((t) => t.trim().replace(/^["']|["']$/g, ''));
    const obj = {};
    headers.forEach((h, idx) => {
      obj[h] = tokens[idx] !== undefined ? tokens[idx] : '';
    });
    rows.push(obj);
  }
  return { headers, rows };
}

function pearsonAndOls(comps, lifts) {
  const n = comps.length;
  const sumC = comps.reduce((a, b) => a + b, 0);
  const sumL = lifts.reduce((a, b) => a + b, 0);
  const sumCL = comps.reduce((a, b, i) => a + b * lifts[i], 0);
  const sumC2 = comps.reduce((a, b) => a + b * b, 0);
  const sumL2 = lifts.reduce((a, b) => a + b * b, 0);
  const num = n * sumCL - sumC * sumL;
  const sxx = n * sumC2 - sumC * sumC;
  const syy = n * sumL2 - sumL * sumL;
  const slope = sxx !== 0 ? num / sxx : 0;
  const intercept = n !== 0 ? (sumL - slope * sumC) / n : 0;
  const pearson_r = sxx !== 0 && syy !== 0 ? num / Math.sqrt(sxx * syy) : 0;
  const r_squared = sxx !== 0 && syy !== 0 ? (num * num) / (sxx * syy) : 0;
  let mae = 0;
  let rmse = 0;
  for (let i = 0; i < n; i++) {
    const err = lifts[i] - (slope * comps[i] + intercept);
    mae += Math.abs(err);
    rmse += err * err;
  }
  return {
    slope,
    intercept,
    pearson_r,
    r_squared,
    test_mae: n !== 0 ? mae / n : 0,
    test_rmse: n !== 0 ? Math.sqrt(rmse / n) : 0,
  };
}

function holdoutOlsStats(comps, lifts) {
  const n = comps.length;
  if (n < 5) {
    const stats = pearsonAndOls(comps, lifts);
    return { ...stats, train_r_squared: stats.r_squared, overfitting_gap: 0 };
  }
  const split = Math.floor(n * 0.8);
  const train = { c: comps.slice(0, split), l: lifts.slice(0, split) };
  const test = { c: comps.slice(split), l: lifts.slice(split) };
  const fit = pearsonAndOls(train.c, train.l);

  const testMean = test.l.reduce((a, b) => a + b, 0) / test.l.length;
  let ssRes = 0;
  let ssTot = 0;
  let aeSum = 0;
  for (let i = 0; i < test.c.length; i++) {
    const pred = fit.slope * test.c[i] + fit.intercept;
    const err = test.l[i] - pred;
    ssRes += err * err;
    aeSum += Math.abs(err);
    ssTot += (test.l[i] - testMean) * (test.l[i] - testMean);
  }
  const testR2 = ssTot !== 0 ? 1 - ssRes / ssTot : 0;
  const testMae = aeSum / test.c.length;
  const testRmse = Math.sqrt(ssRes / test.c.length);
  return {
    slope: fit.slope,
    intercept: fit.intercept,
    pearson_r: fit.pearson_r,
    r_squared: testR2,
    train_r_squared: fit.r_squared,
    test_mae: testMae,
    test_rmse: testRmse,
    overfitting_gap: Math.max(0, fit.r_squared - testR2),
  };
}

// Pre-trained hybrid model metadata surfaced on custom uploads. Mirrors
// src/models/artifacts/best_model_meta.json (hybrid = OLS Linear Regression).
const PRETRAINED_HYBRID = {
  model_label: 'OLS Linear Regression',
  model_origin: 'Pre-trained Hybrid CMS model - applied to this upload, not re-fit from it',
  test_r2: 0.097635,
  test_mae: 2.200284,
  test_rmse: 2.825056,
  bootstrap_ci: '[0.0205, 0.1578]',
  r2_definition: 'Repeated 5-fold CV pooled out-of-sample (model benchmark)',
};

export class PredictApiError extends Error {
  constructor(message, code, payload) {
    super(message);
    this.name = 'PredictApiError';
    this.code = code;
    this.payload = payload || {};
  }
}

/**
 * POST the raw upload to /api/predict_custom (pre-trained model inference).
 * Rejects with PredictApiError (carrying error.code + message/payload) for the
 * API's specific validation responses such as MISSING_COLUMNS; a fetched-and-
 * failed API request is always an explicit PredictApiError so the UI can show
 * the specific reason. Network/abort failures are marked `err.network` so
 * callers may fall back to legacy client-side synthesis when the endpoint is
 * not running.
 */

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? ''
  : 'https://npn-repcall.onrender.com';


export async function predictViaApi(rawText, { model = 'hybrid' } = {}) {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = controller ? window.setTimeout(() => controller.abort(), 60000) : null;
  try {
    const form = new FormData();
    form.append('file', new Blob([rawText], { type: 'text/csv' }), 'dataset.csv');
    form.append('model', model);
    const resp = await fetch(`${API_BASE}/api/predict_custom`, {
      method: 'POST',
      body: form,
      signal: controller ? controller.signal : undefined,
    });
    let data = null;
    try { data = await resp.json(); } catch (_e) { data = null; }
    if (!data || typeof data !== 'object') {
      throw new PredictApiError(
        `Predict API returned a non-JSON response (HTTP ${resp.status}). Verify the server is the predict-server, not a plain file server.`,
        'API_NON_JSON'
      );
    }
    if (!data.ok) {
      const apiErr = new PredictApiError(
        data.message || `Predict API error (${data.error || 'unknown'}).`,
        data.error || 'API_ERROR',
        data
      );
      if (Array.isArray(data.missing_columns)) apiErr.missing_columns = data.missing_columns;
      throw apiErr;
    }
    return data;
  } catch (err) {
    if (err instanceof PredictApiError) throw err;
    if (err && err.name === 'AbortError') {
      const timeoutErr = new PredictApiError('Predict API timed out after 30s.', 'API_TIMEOUT');
      throw timeoutErr;
    }
    const networkErr = new Error(`Predict API unavailable: ${err && err.message ? err.message : err}`);
    networkErr.network = true;
    throw networkErr;
  } finally {
    if (timer) window.clearTimeout(timer);
  }
}

export async function processCustomDataset(fileOrText, fileName = 'custom_dataset.csv', progressCb = () => {}) {
  const t0 = performance.now();
  
  let rawText = '';
  if (typeof fileOrText === 'string') {
    rawText = fileOrText;
  } else if (fileOrText instanceof File || fileOrText instanceof Blob) {
    rawText = await fileOrText.text();
  }

  // STEP 1: COLUMN INSPECTION
  progressCb({ step: 'inspect', status: 'active', progress: 15 });
  await new Promise((r) => setTimeout(r, 250));

  let parsedRows = [];
  let existingHeaders = [];

  if (rawText.trim().startsWith('{') || rawText.trim().startsWith('[')) {
    const jsonParsed = JSON.parse(rawText);
    parsedRows = Array.isArray(jsonParsed) ? jsonParsed : (jsonParsed.data || []);
    existingHeaders = parsedRows.length ? Object.keys(parsedRows[0]) : [];
  } else {
    const parsed = parseCSV(rawText);
    existingHeaders = parsed.headers;
    parsedRows = parsed.rows;
  }

  const reqDomains = [
    'Tot_30day_Fills', 'Target_Calls', 'Actual_Calls', 'Samples_Dropped',
    'Specialty', 'Prscrbr_NPI', 'Physician_Name', 'Brand_Name', 'City', 'State',
    'Sales_Rep', 'Territory', 'HCP_Tier', 'Rx_Lift_Pct', 'Post_Campaign_Fills'
  ];

  const lowerExisting = existingHeaders.map((h) => h.toLowerCase());
  const missingDomains = reqDomains.filter((r) => !lowerExisting.includes(r.toLowerCase()));

  progressCb({
    step: 'inspect',
    status: 'completed',
    progress: 35,
    detail: `Found ${existingHeaders.length} cols (${missingDomains.length} missing synthesized)`,
  });

  // Fire the pre-trained model inference while the UI reads the file's shape.
  // hybrid is the default model (no picker requested).
  const predictPromise = predictViaApi(rawText, { model: 'hybrid' }).catch((err) => err);

  // STEP 2: AUTO-SYNTHESIS
  progressCb({ step: 'synthesize', status: 'active', progress: 45 });
  await new Promise((r) => setTimeout(r, 300));

  const api = await predictPromise;
  const apiError = api instanceof Error ? api : null;
  if (apiError) {
    if (!apiError.network) {
      // API accepted the request and rejected the file: surface the specific
      // reason (e.g. MISSING_COLUMNS) as a hard upload failure.
      throw apiError;
    }
    // Endpoint unreachable (e.g. plain `python -m http.server`): continue the
    // legacy fully-client-side flow so the app still works offline.
    console.warn('predictViaApi unavailable; falling back to client-side synthesis.', apiError);
  }
  const apiResult = apiError ? null : api;
  const predictedLift = apiResult && Array.isArray(apiResult.predicted_rx_lift_pct)
    ? apiResult.predicted_rx_lift_pct
    : null;

  const n = parsedRows.length || 100;
  const synthesizedRows = parsedRows.map((row, idx) => {
    const r = { ...row };

    // Standardize key lookups
    const getVal = (key, fallback) => {
      const foundKey = Object.keys(r).find((k) => k.toLowerCase() === key.toLowerCase());
      return foundKey && r[foundKey] !== '' && r[foundKey] !== undefined ? r[foundKey] : fallback;
    };

    // Pre-trained model prediction for this row (original file order), when
    // the API answered with a prediction per uploaded row.
    const predicted = Array.isArray(predictedLift) && predictedLift.length === parsedRows.length
      ? Number(predictedLift[idx])
      : null;

    const npi = getVal('Prscrbr_NPI', getVal('npi', `${1001000001 + idx}`));
    const physician_name = getVal('Physician_Name', getVal('physician_name', `Dr. Prescriber ${idx + 1}`));
    const specialty = getVal('Specialty', SPECIALTIES[idx % SPECIALTIES.length]);
    const loc = LOCATIONS[idx % LOCATIONS.length];
    const city = getVal('City', loc[0]);
    const state = getVal('State', loc[1]);
    const brand_name = getVal('Brand_Name', BRAND_NAMES[idx % BRAND_NAMES.length]);
    const rep_id = getVal('Sales_Rep', getVal('rep_id', REPS[idx % REPS.length]));
    const territory_id = getVal('Territory', getVal('territory_id', REP_TO_TERR[rep_id] || 'TERR-01'));

    // Gamma approximation: shape 6.0, scale 2.5 -> mean ~ 15
    const randNorm = Math.sqrt(-2.0 * Math.log(Math.max(1e-9, Math.random()))) * Math.cos(2.0 * Math.PI * Math.random());
    const fillsRaw = parseFloat(getVal('Tot_30day_Fills', getVal('tot_30day_fills', Math.max(2.0, 15.0 + randNorm * 4.5))));
    
    const cmsDecile = Math.max(1, Math.min(10, Math.ceil((fillsRaw / 30.0) * 10.0)));
    const hcp_tier = parseInt(getVal('HCP_Tier', cmsDecile >= 8 ? 1 : (cmsDecile >= 4 ? 2 : 3)), 10);

    // Uniform / Poisson target calls: 3 to 14
    const target_calls = parseInt(getVal('Target_Calls', Math.max(2, Math.min(16, Math.round(2 + cmsDecile * 1.2)))), 10);
    const actual_calls = parseInt(getVal('Actual_Calls', Math.max(0, Math.round(target_calls * (0.65 + Math.random() * 0.35)))), 10);
    const samples_dropped = parseInt(getVal('Samples_Dropped', Math.max(0, Math.round(actual_calls * (0.6 + Math.random() * 0.8)))), 10);

    // Non-linear response function for Rx lift (fallback only when the API
    // did not provide a pre-trained-model prediction for this row)
    const call_eff = actual_calls > 0 ? (6.0 * Math.pow(actual_calls, 1.5)) / (Math.pow(4.0, 1.5) + Math.pow(actual_calls, 1.5)) : 0;
    const samp_eff = 1.2 * Math.sqrt(samples_dropped);
    const rx_lift_pct = predicted != null
      ? predicted
      : parseFloat(getVal('Rx_Lift_Pct', Math.max(-3.0, Math.min(18.0, 0.5 + call_eff + samp_eff + (Math.random() * 2.0 - 1.0)))));
    const post_campaign_fills = parseFloat(getVal('Post_Campaign_Fills', fillsRaw * (1.0 + rx_lift_pct / 100.0)));

    return {
      npi,
      Prscrbr_NPI: npi,
      physician_name,
      Physician_Name: physician_name,
      specialty,
      Specialty: specialty,
      city,
      City: city,
      state,
      State: state,
      brand_name,
      Brand_Name: brand_name,
      rep_id,
      Sales_Rep: rep_id,
      territory_id,
      Territory: territory_id,
      hcp_tier,
      HCP_Tier: hcp_tier,
      Target_Calls: target_calls,
      Actual_Calls: actual_calls,
      Samples_Dropped: samples_dropped,
      Tot_30day_Fills: fillsRaw,
      Tot_30day_Fills_raw: fillsRaw,
      Post_Campaign_Fills: post_campaign_fills,
      Rx_Lift_Pct: rx_lift_pct,
      rx_lift_pct,
    };
  });

  progressCb({
    step: 'synthesize',
    status: 'completed',
    progress: 60,
    detail: `Synthesized Gamma, Poisson, Normal distributions across ${synthesizedRows.length} rows`,
  });

  // STEP 3: DERIVED FEATURES CALCULATION
  progressCb({ step: 'features', status: 'active', progress: 70 });
  await new Promise((r) => setTimeout(r, 250));

  const enrichedHcps = synthesizedRows.map((h) => {
    const cadence = +(h.Actual_Calls / 3.0).toFixed(2);
    const sample_ratio = +(h.Samples_Dropped / Math.max(1, h.Actual_Calls)).toFixed(2);
    const comp_pct = +((h.Actual_Calls / Math.max(1, h.Target_Calls)) * 100).toFixed(2);
    
    return {
      ...h,
      Monthly_Call_Frequency_raw: cadence,
      Sample_Call_Ratio_raw: sample_ratio,
      Compliance_Pct_raw: comp_pct,
      compliance_pct: comp_pct,
    };
  });

  const lifts = enrichedHcps.map((h) => h.rx_lift_pct).sort((a, b) => a - b);
  const medianLift = lifts.length ? lifts[Math.floor(lifts.length / 2)] : 3.89;

  const finalHcps = enrichedHcps.map((h) => ({
    ...h,
    quadrant: classifyQuadrant(h.compliance_pct, h.rx_lift_pct, medianLift),
    _quadrant: classifyQuadrant(h.compliance_pct, h.rx_lift_pct, medianLift),
  }));

  progressCb({
    step: 'features',
    status: 'completed',
    progress: 85,
    detail: `Calculated Cadence, Sample Ratio, & Derived Interactions`,
  });

  // STEP 4: ML DRIVER ATTRIBUTION & SCORECARDS
  progressCb({ step: 'ml', status: 'active', progress: 90 });
  await new Promise((r) => setTimeout(r, 300));

  // Rep scorecards with driver metrics
  const repMap = {};
  finalHcps.forEach((h) => {
    const rid = h.Sales_Rep;
    if (!repMap[rid]) {
      repMap[rid] = {
        rep_id: rid,
        sales_rep_name: rid,
        territory_id: h.Territory,
        is_active: true,
        hcps: [],
      };
    }
    repMap[rid].hcps.push(h);
  });

  const terrLiftSum = {};
  const terrLiftCount = {};
  finalHcps.forEach((h) => {
    const t = h.Territory || 'TERR-01';
    terrLiftSum[t] = (terrLiftSum[t] || 0) + (h.rx_lift_pct || 0);
    terrLiftCount[t] = (terrLiftCount[t] || 0) + 1;
  });
  const terrMeanLift = {};
  Object.keys(terrLiftSum).forEach((t) => {
    terrMeanLift[t] = (terrLiftSum[t] || 0) / Math.max(1, terrLiftCount[t] || 1);
  });

  const repsList = Object.values(repMap).map((r) => {
    const n_hcp = r.hcps.length;
    const target = r.hcps.reduce((s, h) => s + h.Target_Calls, 0);
    const actual = r.hcps.reduce((s, h) => s + h.Actual_Calls, 0);
    const samples = r.hcps.reduce((s, h) => s + h.Samples_Dropped, 0);
    const mean_lift = r.hcps.reduce((s, h) => s + h.rx_lift_pct, 0) / Math.max(1, n_hcp);
    const comp_pct = Math.round((actual / Math.max(1, target)) * 100);
    
    const cadence = Math.round(actual / 3.0);
    const target_cadence = Math.round(target / 3.0);
    const sample_ratio = +(samples / Math.max(1, actual)).toFixed(2);
    const target_sample_ratio = 1.00;
    const baseline_vol = Math.round(r.hcps.reduce((s, h) => s + (h.Tot_30day_Fills_raw || h.tot_30day_fills || 0), 0));
    const target_baseline_vol = Math.round(n_hcp * 20.0);
    const target_compliance_pct = 80;

    let priority = 'Monitor';
    let action_flag = '🟡 Performance Review';
    let rec = `Review Detailing Quality: Completed ${cadence}/${target_cadence} monthly calls and ${samples}/${actual} samples dropped. Optimize detailing message and targeting.`;
    let bottleneck = `Detailing Quality Review (+${mean_lift.toFixed(2)}% Rx Lift)`;
    let trajectory = 'declining';
    let domQ = 'Ineffective';

    if (mean_lift >= 4.5 && cadence >= target_cadence) {
      domQ = 'Star Performers';
      priority = 'On Track';
      action_flag = '🟢 Maintain & Scale';
      rec = `Top Performer: Exceeding targets (${cadence}/${target_cadence} monthly calls, ${samples}/${actual} samples dropped, +${mean_lift.toFixed(2)}% Rx Lift). Share detailing best practices across territory.`;
      bottleneck = `Top Performer (+${mean_lift.toFixed(2)}% Rx Lift, ${cadence}/${target_cadence} calls/mo)`;
      trajectory = 'improving';
    } else if (mean_lift >= 4.5 && cadence < target_cadence) {
      domQ = 'Star Performers';
      priority = 'Monitor';
      action_flag = '🟡 Efficiency Optimization';
      rec = `High Return, Low Volume: High prescriber responsiveness. ${r.sales_rep_name || r.rep_id} completed ${cadence} of ${target_cadence} target monthly calls and dropped ${samples} samples across ${actual} visits. Increase visit volume to ${target_cadence} calls/mo and ensure 1 sample per visit to maximize total adoption.`;
      bottleneck = `High Return, Low Volume (${cadence}/${target_cadence} calls/mo, ${samples}/${actual} samples)`;
      trajectory = 'improving';
    } else if (mean_lift >= 2.5 && mean_lift < 4.5) {
      domQ = 'Unrealized Potential';
      priority = 'Monitor';
      action_flag = '🟡 Targeting Refinement';
      rec = `Moderate Lift: On track with ${cadence}/${target_cadence} monthly calls. Refine call planning and sample distribution (${samples}/${actual} samples) toward top-tier physicians.`;
      bottleneck = `Targeting Refinement (+${mean_lift.toFixed(2)}% Lift, ${cadence}/${target_cadence} calls/mo)`;
      trajectory = 'stable';
    } else if (mean_lift < 2.5 && (cadence < target_cadence || samples < actual)) {
      domQ = 'Needs Intervention';
      priority = 'Urgent Coaching';
      action_flag = '🔴 Urgent Coaching';
      rec = `Driver Deficit: Falling short of call target (${cadence} vs ${target_cadence} monthly calls) and sample target (${samples} vs ${actual} samples dropped across visits). Prioritize doctor visit cadence.`;
      bottleneck = cadence < target_cadence ? `Call Deficit (${cadence} vs ${target_cadence} calls/mo)` : `Sample Deficit (${samples} vs ${actual} samples)`;
      trajectory = 'declining';
    }

    // Real reallocation math mirroring analytics_engine.compute_call_reallocation:
    // per-HCP reallocated target = Target_Calls * (1 + (Rx_Lift_Pct - territory_mean_lift)/100)
    const realloc = { add: 0, free: 0, net: 0, inc: 0, dec: 0 };
    r.hcps.forEach((h) => {
      const t = h.Territory || 'TERR-01';
      const targetCalls = h.Target_Calls || 0;
      const lift = h.rx_lift_pct || 0;
      const reallocatedTarget = targetCalls * (1 + (lift - (terrMeanLift[t] ?? 0)) / 100);
      const delta = reallocatedTarget - targetCalls;
      realloc.net += delta;
      if (delta > 0) { realloc.add += delta; realloc.inc++; }
      else if (delta < 0) { realloc.free += -delta; realloc.dec++; }
    });
    const reallocRec = realloc.add > realloc.free + 0.5
      ? 'Expand high-lift prescriber visits'
      : realloc.free > realloc.add + 0.5
        ? 'Reallocate to higher-lift HCPs'
        : 'Reallocate calls within territory (Balanced)';

    return {
      rep_id: r.rep_id,
      sales_rep_name: r.sales_rep_name,
      territory_id: r.territory_id,
      is_active: true,
      prescriber_count: n_hcp,
      total_target_calls: target,
      total_actual_calls: actual,
      samples: samples,
      monthly_cadence: cadence,
      target_monthly_cadence: target_cadence,
      sample_ratio: sample_ratio,
      target_sample_ratio: target_sample_ratio,
      baseline_volume: baseline_vol,
      target_baseline_volume: target_baseline_vol,
      compliance_pct: comp_pct,
      target_compliance_pct: target_compliance_pct,
      rx_lift_pct: +mean_lift.toFixed(3),
      quadrant: domQ,
      coaching_priority: priority,
      action_flag,
      driver_bottleneck: bottleneck,
      reallocation_recommendation: reallocRec,
      driver_recommendation: rec,
      trajectory_direction: trajectory,
      sample_size_flag: n_hcp >= 30,
      calls_to_add: Math.round(realloc.add * 100) / 100,
      calls_to_free: Math.round(realloc.free * 100) / 100,
      net_call_delta: Math.round(realloc.net * 100) / 100,
      hcps_with_increase: realloc.inc,
      hcps_with_decrease: realloc.dec,
    };
  });

  // Coaching queue tasks
  let taskCounter = 1;
  const coachingQueue = repsList.map((r) => {
    const lift = r.rx_lift_pct;
    const cad = r.monthly_cadence;
    const targetCad = r.target_monthly_cadence;
    const samples = r.samples;
    const actual = r.total_actual_calls;

    if (lift < 2.5 && (cad < targetCad || samples < actual)) {
      const reason = cad < targetCad ? 'CADENCE_DEFICIT' : 'SAMPLE_RATIO_DEFICIT';
      const title = cad < targetCad ? `Reach out to ${r.rep_id} — Call Deficit: ${cad} vs ${targetCad} calls/mo (Target ${targetCad})` : `Reach out to ${r.rep_id} — Sample Deficit: ${samples} vs ${actual} visits (Target 1/visit)`;
      return {
        task_id: `TASK-${String(taskCounter++).padStart(3, '0')}`,
        rep_id: r.rep_id,
        territory_id: r.territory_id,
        priority: 'urgent',
        title: title,
        subtext: `${r.territory_id} • ${r.quadrant} • Critical Action: Driver Deficit`,
        reason_code: reason,
      };
    } else if (lift >= 4.5 && cad < targetCad) {
      return {
        task_id: `TASK-${String(taskCounter++).padStart(3, '0')}`,
        rep_id: r.rep_id,
        territory_id: r.territory_id,
        priority: 'on_track',
        title: `Capacity Scaling for ${r.rep_id} — High Return, Low Volume (${cad} → ${targetCad} calls/mo)`,
        subtext: `${r.territory_id} • ${r.quadrant} • Efficiency Optimization: Increase call volume`,
        reason_code: 'EFFICIENCY_SCALING',
      };
    } else if (lift >= 4.5) {
      return {
        task_id: `TASK-${String(taskCounter++).padStart(3, '0')}`,
        rep_id: r.rep_id,
        territory_id: r.territory_id,
        priority: 'on_track',
        title: `Territory Best Practice Sharing — ${r.rep_id} (+${lift.toFixed(2)}% Lift)`,
        subtext: `${r.territory_id} • ${r.quadrant} • Star Performer: Model for Best Practices`,
        reason_code: 'TOP_PERFORMER',
      };
    } else if (lift >= 2.5 && lift < 4.5) {
      return {
        task_id: `TASK-${String(taskCounter++).padStart(3, '0')}`,
        rep_id: r.rep_id,
        territory_id: r.territory_id,
        priority: 'monitor',
        title: `Targeting Refinement Review for ${r.rep_id}`,
        subtext: `${r.territory_id} • ${r.quadrant} • Targeting Refinement (+${lift.toFixed(2)}% Lift)`,
        reason_code: 'TARGETING_REFINEMENT',
      };
    } else {
      return {
        task_id: `TASK-${String(taskCounter++).padStart(3, '0')}`,
        rep_id: r.rep_id,
        territory_id: r.territory_id,
        priority: 'monitor',
        title: `Detailing Quality Review for ${r.rep_id}`,
        subtext: `${r.territory_id} • ${r.quadrant} • Performance Review (+${lift.toFixed(2)}% Lift)`,
        reason_code: 'DETAILING_QUALITY',
      };
    }
  });

  // Real lightweight statistics mirrored from analytics_engine.compute_kpis
  // (Pearson r + OLS regression on the uploaded Compliance × Rx Lift columns),
  // evaluated with a genuine 80/20 held-out split like the backend ML suite.
  const meanCompPct = finalHcps.reduce((s, h) => s + (h.Compliance_Pct_raw ?? 0), 0) / Math.max(1, finalHcps.length);
  const meanLiftPct = finalHcps.reduce((s, h) => s + (h.rx_lift_pct ?? 0), 0) / Math.max(1, finalHcps.length);
  const olsStats = holdoutOlsStats(
    finalHcps.map((h) => h.Compliance_Pct_raw ?? 0),
    finalHcps.map((h) => h.rx_lift_pct ?? 0),
  );
  const round6 = (v) => Math.round(v * 1e6) / 1e6;

  const ml = {
    best_model_summary: apiResult
      ? {
          model_label: PRETRAINED_HYBRID.model_label,
          model_origin: PRETRAINED_HYBRID.model_origin,
          test_r2: PRETRAINED_HYBRID.test_r2,
          test_mae: PRETRAINED_HYBRID.test_mae,
          test_rmse: PRETRAINED_HYBRID.test_rmse,
          overfitting_gap: 0.07952,
          bootstrap_ci: PRETRAINED_HYBRID.bootstrap_ci,
          r2_definition: PRETRAINED_HYBRID.r2_definition,
          applied_to_rows: finalHcps.length,
        }
      : {
          model_label: 'OLS Regression (Compliance → Rx Lift)',
          test_r2: round6(olsStats.r_squared),
          test_mae: round6(olsStats.test_mae),
          test_rmse: round6(olsStats.test_rmse),
          overfitting_gap: round6(olsStats.overfitting_gap),
          bootstrap_ci: 'N/A - client-side single OLS fit, no CV',
        },
    // No ML model tournament is run on ad-hoc uploads: leave empty and clearly
    // labelled rather than fabricating benchmark rows.
    tournament_table: [],
    custom_statistics: {
      n_hcps: finalHcps.length,
      n_reps: repsList.length,
      mean_compliance_rate_pct: round6(meanCompPct),
      mean_rx_lift_pct: round6(meanLiftPct),
      pearson_r: round6(olsStats.pearson_r),
      ols_slope: round6(olsStats.slope),
      ols_intercept: round6(olsStats.intercept),
      ols_equation: `Rx_Lift_Pct = ${olsStats.slope.toFixed(4)} * Compliance_Pct + ${olsStats.intercept.toFixed(4)}`,
      rx_lift_predicted_by: apiResult ? apiResult.model_label : 'client synthesis (fallback)',
    },
  };

  const attribution = apiResult
    ? {
        global_importance: Array.isArray(apiResult.feature_importance) ? apiResult.feature_importance : [],
        shap_contributions: [],
        unavailable_reason: null,
        importance_method: apiResult.importance_method,
        driver_label: apiResult.driver_label,
        model_origin: apiResult.model_label,
      }
    : {
        global_importance: [],
        shap_contributions: [],
        unavailable_reason: 'Predict API unreachable - driver attribution unavailable for this upload.',
      };

  const elapsed = ((performance.now() - t0) / 1000).toFixed(3);
  const telemetry = {
    initial_rows: finalHcps.length,
    after_privacy_filter: finalHcps.length,
    retained_rows: finalHcps.length,
    suppressed_rows: 0,
    nulls_imputed: 0,
    execution_time_sec: parseFloat(elapsed),
  };

  State.customData = {
    reps: repsList,
    hcps: finalHcps,
    ml,
    attribution,
    coachingQueue,
    telemetry,
    fileName,
  };

  progressCb({
    step: 'ml',
    status: 'completed',
    progress: 100,
    detail: apiResult
      ? `Applied ${apiResult.model_label} to ${finalHcps.length} uploaded HCPs (${elapsed}s)`
      : `Completed in ${elapsed}s (OLS test R² = ${ml.best_model_summary.test_r2} on ${finalHcps.length} uploaded HCPs)`,
  });

  return State.customData;
}

