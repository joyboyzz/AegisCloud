/* =========================================================================
   AegisCloud console — vanilla JS single page app (no build step, no CDN)
   ========================================================================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const STATE = {
  user: null,
  view: 'overview',
  overview: null,
  model: null,
  stream: { on: false, timer: null, speed: 1100, items: [], stats: { allow: 0, stepup: 0, review: 0, block: 0 } },
  vault: { files: [], selected: new Set(), lastSplit: null },
  risk: { last: null, payload: null },
};

const DC = { allow: '#34d399', stepup: '#fbbf24', review: '#fb923c', block: '#f43f5e' };
const RES_SENS = { finance_db: 5, hr_records: 4, k8s_prod: 5, ci_pipeline: 3,
                   object_store: 2, analytics: 2, log_archive: 1 };

/* ------------------------------- plumbing ------------------------------- */
async function req(url, opts = {}) {
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = '/'; throw new Error('auth'); }
  return r.json().catch(() => ({}));
}
const GET = u => req(u);
const POST = (u, b) => req(u, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(b || {}) });
const DEL = u => req(u, { method: 'DELETE' });

function toast(msg, kind = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = esc(msg);
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 4600);
}

const fmtPct = v => (v == null ? '—' : (v * 100).toFixed(1) + '%');
const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fmtAgo = ts => { const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  return s < 60 ? s + 's ago' : s < 3600 ? Math.floor(s / 60) + 'm ago' : Math.floor(s / 3600) + 'h ago'; };
const fmtNum = v => (v == null ? '—' : Number(v).toLocaleString());
const fmtBytes = b => b > 1048576 ? (b / 1048576).toFixed(2) + ' MB'
  : b > 1024 ? (b / 1024).toFixed(1) + ' KB' : b + ' B';

/* --------------------------------- charts -------------------------------- */
function gauge(score, decision, size = 190) {
  const R = size / 2 - 16, cx = size / 2, cy = size / 2 + 6;
  const a = Math.PI * (1 - Math.min(score, 100) / 100);
  const x = cx + R * Math.cos(a), y = cy - R * Math.sin(a);
  const big = score >= 80 ? 1 : 0;
  const col = DC[decision] || '#22d3ee';
  const arc = `M ${cx - R} ${cy} A ${R} ${R} 0 1 1 ${cx + R} ${cy}`;
  const len = Math.PI * R;
  return `<svg viewBox="0 0 ${size} ${size * 0.68}" width="${size}" height="${size * 0.68}">
    <path d="${arc}" fill="none" stroke="#101c2f" stroke-width="13" stroke-linecap="round"/>
    <path d="${arc}" fill="none" stroke="${col}" stroke-width="13" stroke-linecap="round"
      stroke-dasharray="${(len * Math.min(score, 100) / 100).toFixed(1)} ${len}"/>
    <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6.5" fill="${col}" stroke="#060a13" stroke-width="2"/>
    <text x="${cx}" y="${cy - 16}" text-anchor="middle" fill="#e8eefc"
      font-family="ui-monospace,monospace" font-size="${size * 0.19}" font-weight="700">${score.toFixed(0)}</text>
    <text x="${cx}" y="${cy + 2}" text-anchor="middle" fill="#64789b" font-size="11">RISK / 100</text>
  </svg>`;
}

function donut(items, size = 148, thickness = 17) {
  const total = items.reduce((s, i) => s + i.value, 0) || 1;
  const r = size / 2 - thickness / 2 - 2, c = size / 2, circ = 2 * Math.PI * r;
  let off = 0, seg = '';
  items.forEach(i => {
    const frac = i.value / total;
    seg += `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${i.color}" stroke-width="${thickness}"
      stroke-dasharray="${(circ * frac).toFixed(2)} ${circ}" stroke-dashoffset="${(-circ * off).toFixed(2)}"
      transform="rotate(-90 ${c} ${c})" stroke-linecap="butt"/>`;
    off += frac;
  });
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${seg}
    <text x="${c}" y="${c - 2}" text-anchor="middle" fill="#e8eefc" font-size="20"
      font-family="ui-monospace,monospace" font-weight="700">${total}</text>
    <text x="${c}" y="${c + 15}" text-anchor="middle" fill="#64789b" font-size="10">SESSIONS</text></svg>`;
}

function spark(series, w = 520, h = 130, key = 'c') {
  if (!series.length) return `<div class="tiny">no data yet</div>`;
  const max = Math.max(...series.map(s => s[key]), 1);
  const step = series.length > 1 ? w / (series.length - 1) : w;
  const pts = series.map((s, i) => [i * step, h - 14 - (s[key] / max) * (h - 30)]);
  const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const area = `${path} L ${w} ${h - 8} L 0 ${h - 8} Z`;
  const dots = pts.filter((_, i) => i % Math.ceil(pts.length / 24) === 0)
    .map(p => `<circle cx="${p[0]}" cy="${p[1]}" r="2.4" fill="#22d3ee"/>`).join('');
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="height:${h}px">
    <defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="rgba(34,211,238,.35)"/><stop offset="1" stop-color="rgba(34,211,238,0)"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#ga)"/><path d="${path}" fill="none" stroke="#22d3ee" stroke-width="2"/>
    ${dots}</svg>`;
}

function rocSvg(curve, auc) {
  if (!curve || !curve.length) return '<div class="tiny">no curve</div>';
  const w = 260, h = 260, pad = 26;
  const X = v => pad + v * (w - pad - 8), Y = v => h - pad - v * (h - pad - 8);
  const path = curve.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join(' ');
  return `<svg class="chart" viewBox="0 0 ${w} ${h}" style="max-width:270px">
    <rect x="${pad}" y="8" width="${w - pad - 8}" height="${h - pad - 8}" fill="rgba(16,28,47,.35)" rx="6"/>
    <line x1="${pad}" y1="${h - pad}" x2="${w - 8}" y2="${h - pad}" stroke="#24344f"/>
    <line x1="${pad}" y1="8" x2="${pad}" y2="${h - pad}" stroke="#24344f"/>
    <line x1="${pad}" y1="${h - pad}" x2="${w - 8}" y2="8" stroke="#24344f" stroke-dasharray="4 4"/>
    <path d="${path}" fill="none" stroke="#8b5cf6" stroke-width="2.4"/>
    <text x="${w / 2}" y="${h - 6}" text-anchor="middle" fill="#64789b" font-size="10">false positive rate</text>
    <text x="10" y="${h / 2}" fill="#64789b" font-size="10" transform="rotate(-90 14 ${h / 2})" text-anchor="middle">true positive rate</text>
    <text x="${w - 14}" y="26" text-anchor="end" fill="#d6c8ff" font-family="ui-monospace,monospace" font-size="12">AUC ${auc}</text>
  </svg>`;
}

function heatmap(cm) {
  const cells = [['TN', cm.tn, '#34d399'], ['FP', cm.fp, '#fb923c'], ['FN', cm.fn, '#f43f5e'], ['TP', cm.tp, '#22d3ee']];
  const max = Math.max(cm.tn, cm.fp, cm.fn, cm.tp, 1);
  const order = [0, 1, 2, 3];
  return `<div style="display:grid;grid-template-columns:70px 1fr 1fr;gap:6px;align-items:center">
    <div></div>
    <div class="tiny" style="text-align:center">pred failure</div>
    <div class="tiny" style="text-align:center">pred success</div>
    <div class="tiny">true<br>failure</div>
    ${[cm.tn, cm.fp].map((v, i) => cell(v, ['#34d399', '#fb923c'][i])).join('')}
    <div class="tiny">true<br>success</div>
    ${[cm.fn, cm.tp].map((v, i) => cell(v, ['#f43f5e', '#22d3ee'][i])).join('')}
  </div>`;
  function cell(v, col) {
    const a = 0.10 + 0.55 * (v / max);
    return `<div class="hm-cell" style="background:${col}22;border:1px solid ${col}55;border-radius:10px;
      padding:16px 0;text-align:center;color:${col}">${fmtNum(v)}</div>`;
  }
}

/* --------------------------------- modal --------------------------------- */
function modal(title, html, mount) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'position:fixed;inset:0;z-index:80;background:rgba(3,7,14,.72);' +
    'display:grid;place-items:center;backdrop-filter:blur(6px);padding:20px';
  wrap.innerHTML = `<div class="card" style="max-width:560px;width:100%;max-height:86vh;overflow:auto">
      <div class="hd"><h3>${esc(title)}</h3><button class="btn sm ghost" data-close>Close</button></div>
      <div id="modal-body">${html}</div></div>`;
  document.body.appendChild(wrap);
  wrap.querySelector('[data-close]').onclick = () => wrap.remove();
  wrap.addEventListener('click', e => { if (e.target === wrap) wrap.remove(); });
  if (mount) mount(wrap);
  return wrap;
}

/* ------------------------------ navigation ------------------------------ */
const VIEW_META = {
  overview: ['Overview', 'Synthetic sessions · recommendations, not enforcement'],
  risk: ['Risk console', 'Score a synthetic session and inspect the recommendation'],
  monitor: ['Synthetic replay', 'Replaying generated sessions through the decision engine'],
  vault: ['Crypto vault', 'AES-256-GCM envelope encryption · Shamir secret sharing'],
  model: ['Model lab', 'Metrics, thresholding, drift and champion promotion'],
  audit: ['Audit & alerts', 'Hash-chained event log, analyst queue'],
  admin: ['Administration', 'Users, roles, sessions and approvals'],
};

function go(view) {
  STATE.view = view;
  $$('.nav-item').forEach(n => n.classList.toggle('on', n.dataset.view === view));
  $$('.view').forEach(v => v.classList.toggle('on', v.id === 'v-' + view));
  const [t, s] = VIEW_META[view] || ['', ''];
  $('#page-title').textContent = t; $('#page-sub').textContent = s;
  const renderers = { overview: renderOverview, risk: renderRisk, monitor: renderMonitor,
                      vault: renderVault, model: renderModel, audit: renderAudit, admin: renderAdmin };
  (renderers[view] || (() => {}))();
  location.hash = view;
}

/* =============================== OVERVIEW =============================== */
async function renderOverview() {
  const root = $('#v-overview');
  if (!STATE.overview) root.innerHTML = `<div class="card">Loading metrics…</div>`;
  const d = STATE.overview = await GET('/api/overview');
  if (!d.success) { root.innerHTML = `<div class="card">Unable to load overview</div>`; return; }
  const k = d.kpis, m = d.model.metrics || {};
  const mix = [
    { label: 'Allow', value: k.sessions - k.blocked - k.stepup - k.review, color: DC.allow },
    { label: 'Step-up', value: k.stepup, color: DC.stepup },
    { label: 'Review', value: k.review, color: DC.review },
    { label: 'Block', value: k.blocked, color: DC.block }];
  const bucketMax = Math.max(...d.buckets.map(b => b.c), 1);
  const order = ['0-20', '20-40', '40-60', '60-80', '80-100'];
  const bucketColors = ['#34d399', '#22d3ee', '#fbbf24', '#fb923c', '#f43f5e'];

  root.innerHTML = `
  <div class="grid g-4">
    ${kpi('Sessions scored', fmtNum(k.sessions), `${k.last_hour} in the last hour`, '')}
    ${kpi('Block suggested', fmtNum(k.blocked), `${k.block_rate}% of simulated sessions`, 'bad')}
    ${kpi('Step-up suggested', fmtNum(k.stepup), 'recommendation only', 'warn')}
    ${kpi('Average risk', k.avg_risk + '/100', 'blended across decisions', 'ok')}
  </div>

  <div class="grid g-23">
    <div class="card">
      <div class="hd"><h3>Simulated recommendations</h3>
        <span class="pill violet">${fmtNum(k.sessions)} total</span></div>
      <div style="display:flex;gap:26px;align-items:center;flex-wrap:wrap">
        ${donut(mix)}
        <div style="flex:1;min-width:190px">
          ${mix.map(x => `<div class="stat-line"><span><i style="display:inline-block;width:9px;height:9px;
            border-radius:3px;background:${x.color};margin-right:8px"></i>${x.label}</span>
            <b>${fmtNum(x.value)}</b></div>`).join('')}
        </div>
      </div>
      <hr class="sep">
      <div class="tiny" style="margin-bottom:8px">Risk distribution</div>
      ${order.map((o, i) => {
        const row = d.buckets.find(b => b.b === o) || { c: 0 };
        return `<div style="margin-bottom:7px">
          <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink-2)">
            <span class="mono-sm">${o}</span><span class="mono-sm">${row.c}</span></div>
          <div class="bar-mini"><i style="width:${(row.c / bucketMax * 100).toFixed(1)}%;
            background:${bucketColors[i]}"></i></div></div>`;
      }).join('')}
    </div>

    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="card">
        <div class="hd"><h3>Registered model</h3><span class="pill cyan">${esc(d.model.champion || '—')}</span></div>
        <div class="stat-line"><span>Version</span><b>${esc(d.model.version || '—')}</b></div>
        <div class="stat-line"><span>Synthetic holdout accuracy</span><b>${fmtPct(m.accuracy)}</b></div>
        <div class="stat-line"><span>Success F1 / ROC-AUC</span><b>${m.f1 ?? '—'} / ${m.roc_auc ?? '—'}</b></div>
        <div class="stat-line"><span>Decision threshold</span><b>${m.threshold ?? '—'}</b></div>
        <div class="row" style="margin-top:14px">
          <button class="btn sm" onclick="go('model')">Open model lab</button>
          <button class="btn sm ghost" onclick="go('monitor')">Replay traffic</button>
        </div>
      </div>
      <div class="card">
        <div class="hd"><h3>Open alerts</h3><span class="pill bad">${d.alerts.length}</span></div>
        ${d.frontend_alerts || ''}
        <div id="ov-alerts">${d.alerts.length ? d.alerts.map(a => `
          <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid rgba(23,35,60,.6)">
            <span class="pill ${a.severity === 'critical' ? 'bad' : a.severity === 'warning' ? 'warn' : 'cyan'}">${a.severity}</span>
            <div><div style="font-size:13px">${esc(a.title)}</div>
              <div class="tiny">${esc(a.detail || '')}</div></div></div>`).join('')
          : '<div class="tiny">No open alerts — the policy engine is quiet.</div>'}</div>
      </div>
    </div>
  </div>

  <div class="grid g-2">
    <div class="card">
      <div class="hd"><h3>Demo activity over the last 6 hours</h3>
        <span class="pill ok"><i class="live-dot"></i>${fmtNum(k.last_hour)} / h</span></div>
      ${spark(d.series, 560, 140, 'c')}
      <div class="legend"><span><i style="background:#22d3ee"></i>sessions per 5-minute bucket</span></div>
    </div>
    <div class="card">
      <div class="hd"><h3>Highest-risk identities</h3><span class="tiny">avg risk · sessions</span></div>
      <table class="tbl"><tbody>
        ${d.top_users.map(u => `<tr><td class="mono-sm">${esc(u.actor)}</td>
          <td style="width:45%"><div class="bar-mini"><i style="width:${Math.min(100, u.r)}%;
            background:${u.r > 60 ? DC.block : u.r > 40 ? DC.stepup : DC.allow}"></i></div></td>
          <td class="num" style="text-align:right">${(u.r || 0).toFixed(0)}</td>
          <td class="num tiny" style="text-align:right">${u.n}</td></tr>`).join('')}
      </tbody></table>
    </div>
  </div>

  <div class="card">
    <div class="hd"><h3>Recent decisions</h3><button class="btn sm ghost" onclick="go('audit')">Full audit trail</button></div>
    <div class="scroll"><table class="tbl">
      <thead><tr><th>#</th><th>Time</th><th>Identity</th><th>P(success)</th><th>Risk</th>
        <th>Decision</th><th>Source</th></tr></thead><tbody>
      ${d.recent.map(r => `<tr>
        <td class="num tiny">${r.id}</td>
        <td class="mono-sm">${fmtTime(r.ts)}</td>
        <td class="mono-sm">${esc(r.actor)}</td>
        <td class="num">${(r.ml_probability ?? 0).toFixed(3)}</td>
        <td class="num">${r.risk_score.toFixed(0)}</td>
        <td><span class="tag ${r.decision}">${r.decision}</span></td>
        <td class="tiny">${r.source}</td></tr>`).join('')}
      </tbody></table></div>
  </div>`;
  refreshAlertBadge(d.alerts.length);
}

function kpi(k, v, d, cls) {
  return `<div class="kpi ${cls}"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
}

function refreshAlertBadge(n) {
  const b = $('#nav-alert-badge');
  b.style.display = n ? '' : 'none'; b.textContent = n;
}

/* ============================== RISK CONSOLE ============================= */
const RISK_FIELDS = [
  ['user_id', 'Identity', 'text'],
  ['cloud_provider', 'Cloud provider', ['aws', 'azure', 'gcp', 'oci']],
  ['auth_method', 'Auth method', ['password', 'certificate', 'mfa', 'biometric', 'hardware_key']],
  ['session_type', 'Session type', ['web', 'api', 'cli', 'mobile']],
  ['resource_accessed', 'Resource', Object.keys(RES_SENS)],
  ['session_duration_sec', 'Duration (s)', 'number'],
  ['failed_attempts', 'Failed attempts', 'number'],
  ['request_rate_per_min', 'Requests / min', 'number'],
  ['hour_of_day', 'Hour of day', 'number'],
  ['anomaly_flag', 'Anomaly flags', 'number'],
];

async function renderRisk() {
  const root = $('#v-risk');
  const presets = await GET('/api/risk/presets');
  const p = STATE.risk.payload || {
    user_id: 'user_017', cloud_provider: 'aws', auth_method: 'password',
    session_type: 'web', resource_accessed: 'finance_db', resource_sensitivity: 5,
    session_duration_sec: 1800, failed_attempts: 1, request_rate_per_min: 6,
    hour_of_day: 11, anomaly_flag: 0, is_new_device: 0, geo_mismatch: 0, country: 'IN',
  };
  STATE.risk.payload = p;

  root.innerHTML = `
  <div class="card">
    <div class="hd"><h3>Attack presets</h3><span class="tiny">one click fills the form, then scores it</span></div>
    <div class="row" style="gap:9px">
      ${Object.entries(presets.presets).map(([k, v]) =>
        `<button class="chip" data-preset="${k}">${esc(v.label)}</button>`).join('')}
    </div>
  </div>

  <div class="grid g-23">
    <div class="card">
      <div class="hd"><h3>Session features</h3><span class="pill cyan">simulated policy</span></div>
      <div class="row">
        ${RISK_FIELDS.map(([name, label, kind]) => {
          const val = p[name];
          if (Array.isArray(kind)) return `<label class="field" style="flex:1 1 150px"><span>${label}</span>
            <select class="input" data-f="${name}">${kind.map(o =>
              `<option ${o === val ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
          return `<label class="field" style="flex:1 1 150px"><span>${label}</span>
            <input class="input" data-f="${name}" type="${kind}" value="${val}"></label>`;
        }).join('')}
        <label class="field" style="flex:1 1 150px"><span>New device</span>
          <select class="input" data-f="is_new_device">
            <option value="0" ${!p.is_new_device ? 'selected' : ''}>no</option>
            <option value="1" ${p.is_new_device ? 'selected' : ''}>yes</option></select></label>
        <label class="field" style="flex:1 1 150px"><span>Geo mismatch</span>
          <select class="input" data-f="geo_mismatch">
            <option value="0" ${!p.geo_mismatch ? 'selected' : ''}>no</option>
            <option value="1" ${p.geo_mismatch ? 'selected' : ''}>yes</option></select></label>
      </div>
      <div class="row" style="margin-top:6px">
        <button class="btn primary" id="score-btn">Score session</button>
        <button class="btn" id="record-btn">Score &amp; record decision</button>
      </div>
      <div class="tiny" style="margin-top:10px">Recording a decision writes it to the audit chain and, for
        <b>review</b>/<b>block</b>, opens an item in the analyst approval queue.</div>
    </div>

    <div id="risk-result" class="card">
      <div class="hd"><h3>Decision</h3></div>
      <div class="tiny">Score a session to see the verdict, the risk gauge and the exact point
        contribution of every signal.</div>
    </div>
  </div>`;

  $$('[data-f]', root).forEach(inp => inp.onchange = () => {
    const k = inp.dataset.f;
    p[k] = inp.type === 'number' ? Number(inp.value) : inp.value;
    if (k === 'resource_accessed') p.resource_sensitivity = RES_SENS[inp.value] || 3;
  });
  $$('[data-preset]', root).forEach(b => b.onclick = () => {
    const preset = presets.presets[b.dataset.preset].payload;
    STATE.risk.payload = Object.assign({}, p, preset);
    renderRisk().then(() => score(false));
  });
  $('#score-btn').onclick = () => score(false);
  $('#record-btn').onclick = () => score(true);
  if (STATE.risk.last) paintRisk(STATE.risk.last);
}

async function score(record) {
  const padding = STATE.risk.payload;
  const res = await POST('/api/risk/score', { session: padding, persist: record, source: 'manual' });
  if (!res.success) { toast(res.error || 'scoring failed', 'err'); return; }
  STATE.risk.last = res;
  paintRisk(res);
  if (record) toast(`Decision #${res.decision_id} recorded · ${res.decision.toUpperCase()}`, 'ok');
}

function paintRisk(r) {
  const el = $('#risk-result');
  const maxPts = Math.max(...r.factors.map(f => Math.abs(f.points)), 1);
  el.innerHTML = `
    <div class="hd"><h3>Decision</h3><span class="decision-badge ${r.decision}">${r.decision}</span></div>
    <div class="gauge-wrap">${gauge(r.risk_score, r.decision)}
      <div style="flex:1;min-width:170px">
        <div class="stat-line"><span>Model P(success)</span><b>${r.ml_probability.toFixed(3)}</b></div>
        <div class="stat-line"><span>Distance from 0.5</span><b>${r.ml_confidence}</b></div>
        <div class="stat-line"><span>Window (adapts)</span><b>${r.thresholds.allow} / ${r.thresholds.stepup} / ${r.thresholds.review}</b></div>
        <div class="stat-line"><span>Policy offset</span><b>${r.policy_offset > 0 ? '+' : ''}${r.policy_offset}</b></div>
      </div></div>
    <div class="tiny" style="margin:12px 0 14px;line-height:1.55">${esc(r.narrative)}</div>
    <div class="tiny" style="margin-bottom:4px">Point contributions (they sum to the score)</div>
    ${r.factors.map(f => `
      <div class="fact-row">
        <div><div>${esc(f.factor)}</div><div class="tiny">${esc(f.detail)}</div></div>
        <div><div class="bar"><i style="width:${Math.abs(f.points) / maxPts * 48}%;
          left:${f.points >= 0 ? '50%' : (50 - Math.abs(f.points) / maxPts * 48) + '%'};
          background:${f.points > 0 ? 'linear-gradient(90deg,#fb7185,#f43f5e)' : 'linear-gradient(90deg,#34d399,#22d3ee)'}"></i></div>
          <div class="pts ${f.points > 0 ? 'pos' : 'neg'}" style="text-align:right">${f.points > 0 ? '+' : ''}${f.points.toFixed(1)}</div>
        </div>
      </div>`).join('')}
    ${r.decision_id ? `<div class="row" style="margin-top:14px">
      <button class="btn sm" id="fb-correct">Prediction was correct</button>
      <button class="btn sm ghost" id="fb-wrong">It was wrong</button></div>
      <div class="tiny" id="fb-note" style="margin-top:8px">Feedback is stored for review; current retraining does not ingest it.</div>` : ''}
  `;
  const c = $('#fb-correct'), w = $('#fb-wrong');
  if (c) c.onclick = () => sendFeedback(r.decision_id, 'correct');
  if (w) w.onclick = () => sendFeedback(r.decision_id, 'incorrect');
}

async function sendFeedback(id, label) {
  const res = await POST('/api/risk/feedback', { decision_id: id, label });
  if (res.success) {
    toast(`Feedback stored — inferred outcome: ${res.recorded.actual_outcome}`);
    $('#fb-note').textContent = 'Feedback stored for decision #' + id + ' · retraining does not yet ingest feedback.';
    STATE.overview = null;
  } else toast(res.error || 'failed', 'err');
}

/* =============================== MONITOR =============================== */
function renderMonitor() {
  const s = STATE.stream;
  $('#v-monitor').innerHTML = `
  <div class="grid g-4">
    ${kpi('Streamed', fmtNum(s.items.length), 'sessions replayed', '')}
    ${kpi('Block suggested', fmtNum(s.stats.block), 'not enforced', 'bad')}
    ${kpi('Step-up suggested', fmtNum(s.stats.stepup), 'not enforced', 'warn')}
    ${kpi('Allow suggested', fmtNum(s.stats.allow), 'not enforced', 'ok')}
  </div>
  <div class="card">
    <div class="hd"><h3>Replay controls</h3>
      <div class="row" style="flex:0 0 auto;gap:8px;align-items:center">
        <div class="seg" id="speed-seg">
          <button data-sp="2200">slow</button><button data-sp="1100" class="on">normal</button>
          <button data-sp="350">fast</button><button data-sp="90">turbo</button>
        </div>
        <button class="btn primary sm" id="mon-toggle">${s.on ? 'Pause' : 'Start'}</button>
        <button class="btn sm ghost" id="mon-reset">Reset</button>
      </div></div>
    <div class="tiny">This feed is the <b>drifted</b> corpus: geo-mismatches, faster request rates and new
      devices are over-represented relative to training data, so you can watch the policy react and the
      drift monitor flag it in the model lab.</div>
  </div>
  <div class="card">
    <div class="hd"><h3>Decision feed</h3><span class="pill ok"><i class="live-dot"></i> streaming</span></div>
    <div class="feed" id="mon-feed">
      ${s.items.length ? s.items.map(feedRow).join('') : '<div class="tiny" id="feed-empty">Press Start to replay sessions.</div>'}
    </div>
  </div>`;
  $('#mon-toggle').onclick = () => { s.on ? stopStream() : startStream(); renderMonitor(); };
  $('#mon-reset').onclick = async () => {
    stopStream(); await POST('/api/stream/reset', {});
    s.items = []; s.stats = { allow: 0, stepup: 0, review: 0, block: 0 };
    renderMonitor();
  };
  $$('#speed-seg button').forEach(b => b.onclick = () => {
    s.speed = Number(b.dataset.sp);
    $$('#speed-seg button').forEach(x => x.classList.toggle('on', x === b));
    if (s.on) { stopStream(); startStream(); }
  });
}

function feedRow(it) {
  const hi = it.decision === 'block' || it.decision === 'review';
  return `<div class="feed-row ${hi ? 'hi' : ''}">
    <span class="when">${esc((it.timestamp || '').slice(11, 19))}</span>
    <span class="who">${esc(it.user_id)} <span class="tiny">· ${esc(it.provider)} · ${esc(it.auth)} · ${esc(it.resource)}</span></span>
    <span class="tiny">${esc(it.top_factor || '')}</span>
    <span class="num" style="text-align:right">${it.risk_score.toFixed(0)}</span>
    <span class="tag ${it.decision}">${it.decision}</span></div>`;
}

function startStream() {
  const s = STATE.stream;
  s.on = true;
  s.timer = setInterval(async () => {
    const res = await GET('/api/stream/next?n=1');
    if (!res.success) return;
    res.items.forEach(it => {
      s.items.unshift(it);
      if (s.items.length > 70) s.items.pop();
      s.stats[it.decision] = (s.stats[it.decision] || 0) + 1;
    });
    if (STATE.view === 'monitor') {
      const feed = $('#mon-feed');
      if (feed) {
        const placeholder = document.getElementById('feed-empty');
        if (placeholder) placeholder.remove();
        const html = res.items.map(feedRow).join('');
        feed.insertAdjacentHTML('afterbegin', html);
        while (feed.children.length > 70) feed.lastElementChild.remove();
        const row = feed.firstElementChild;
        if (row) row.classList.add('new');
      }
      const kpis = $$('#v-monitor .kpi .v');
      if (kpis.length === 4) {
        kpis[0].textContent = fmtNum(s.items.length);
        kpis[1].textContent = fmtNum(s.stats.block);
        kpis[2].textContent = fmtNum(s.stats.stepup);
        kpis[3].textContent = fmtNum(s.stats.allow);
      }
    }
  }, s.speed);
}
function stopStream() { STATE.stream.on = false; clearInterval(STATE.stream.timer); }

/* ================================ VAULT ================================ */
async function renderVault() {
  const root = $('#v-vault');
  const d = await GET('/api/vault/files');
  STATE.vault.files = d.files || [];
  root.innerHTML = `
  <div class="grid g-23">
    <div class="card">
      <div class="hd"><h3>Encrypted file vault</h3>
        <span class="pill cyan">master key ${esc(d.key_id || '—')}</span></div>
      <div class="dropzone" id="drop">Drop a file here or click to choose
        <div class="tiny" style="margin-top:6px">AES-256-GCM · per-file data key wrapped by the master key · max 25 MB</div>
        <input type="file" id="file-input" style="display:none"></div>
      <div class="row" style="margin-top:12px">
        <label class="field" style="margin:0"><span>Tags</span>
          <input class="input" id="file-tags" placeholder="audit, q3"></label>
      </div>
      <div class="scroll" style="margin-top:14px"><table class="tbl">
        <thead><tr><th>File &amp; actions</th><th>Size</th><th>SHA-256</th><th>Links</th></tr></thead><tbody>
        ${STATE.vault.files.length ? STATE.vault.files.map(f => `<tr>
          <td>${esc(f.filename)}<div class="tiny">${fmtAgo(f.created_at)} · ${esc(f.tags || '')}</div>
            <div style="display:flex;gap:5px;margin-top:7px;flex-wrap:wrap">
              <button class="btn sm ghost" data-dl="${f.id}">Download</button>
              <button class="btn sm ghost" data-share="${f.id}">Share link</button>
              <button class="btn sm ghost" data-tamper="${f.id}">Tamper test</button>
              <button class="btn sm danger" data-del="${f.id}">Delete</button>
            </div></td>
          <td class="num" style="white-space:nowrap">${fmtBytes(f.size_bytes)}</td>
          <td class="mono-sm" style="white-space:nowrap">${esc(f.sha256.slice(0, 10))}…</td>
          <td class="num">${f.links}</td></tr>`).join('')
        : '<tr><td colspan="4" class="tiny">Vault is empty — upload something.</td></tr>'}
      </tbody></table></div>
      ${document.body.dataset.role === 'admin' ? `<div class="row" style="margin-top:14px">
        <button class="btn sm" id="rotate-btn">Rotate master key</button>
        <span class="tiny" style="align-self:center">Re-wraps every file DEK without touching ciphertext.</span>
      </div>` : ''}
    </div>

    <div class="card">
      <div class="hd"><h3>Shamir secret sharing</h3><span class="pill violet">GF(2⁸)</span></div>
      <div class="tiny" style="margin-bottom:10px">Split a secret into <b>n</b> shares with threshold <b>k</b>:
        any k shares reconstruct it. This demo is not linked to the vault key.</div>
      <label class="field"><span>Secret</span>
        <input class="input" id="ss-secret" value="sample-phrase-for-demo"></label>
      <div class="row">
        <label class="field"><span>Threshold (k)</span><input class="input" id="ss-k" type="number" value="3" min="2" max="10"></label>
        <label class="field"><span>Shares (n)</span><input class="input" id="ss-n" type="number" value="5" min="2" max="10"></label>
      </div>
      <button class="btn primary sm" id="ss-split" style="width:100%">Generate shares</button>
      <div id="ss-out" style="margin-top:14px"></div>
    </div>
  </div>`;

  const drop = $('#drop'), input = $('#file-input');
  drop.onclick = () => input.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over');
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); };
  input.onchange = () => input.files[0] && uploadFile(input.files[0]);

  $$('[data-dl]', root).forEach(b => b.onclick = () => {
    window.location = '/api/vault/download/' + b.dataset.dl; });
  $$('[data-del]', root).forEach(b => b.onclick = async () => {
    if (!confirm('Delete this file permanently?')) return;
    await DEL('/api/vault/files/' + b.dataset.del); toast('File deleted'); renderVault(); });
  $$('[data-tamper]', root).forEach(b => b.onclick = async () => {
    const r = await POST('/api/vault/tamper/' + b.dataset.tamper, {});
    modal('Tamper detection test',
      `<p class="tiny">One byte of the stored ciphertext was flipped, the file was read back, and the
        original byte restored.</p>
       <div class="card" style="margin-top:12px;padding:14px">
         <div class="stat-line"><span>Tampering detected</span>
           <b style="color:${r.detected ? DC.allow : DC.block}">${r.detected ? 'YES' : 'NO'}</b></div>
         <div class="tiny" style="margin-top:8px">${esc(r.detail)}</div></div>`);
  });
  $$('[data-share]', root).forEach(b => b.onclick = () => shareDialog(b.dataset.share));
  if ($('#rotate-btn')) $('#rotate-btn').onclick = async () => {
    const r = await POST('/api/vault/rotate', {});
    toast(r.success ? `Master key rotated · ${r.files_rewrapped} DEKs re-wrapped` : (r.error || 'failed'),
      r.success ? 'ok' : 'err');
    renderVault();
  };
  $('#ss-split').onclick = async () => {
    const r = await POST('/api/vault/split', { secret: $('#ss-secret').value,
      threshold: Number($('#ss-k').value), shares: Number($('#ss-n').value) });
    if (!r.success) return toast(r.error, 'err');
    STATE.vault.lastSplit = r;
    $('#ss-out').innerHTML = `
      <div class="tiny" style="margin-bottom:6px">${esc(r.hint)}</div>
      <div class="scroll" style="max-height:300px"><table class="tbl"><thead>
        <tr><th></th><th>#</th><th>share y (base64)</th></tr></thead><tbody>
        ${r.share_list.map(s => `<tr><td><input type="checkbox" class="ss-pick" data-x="${s.x}"
          data-y="${esc(s.y)}" checked></td><td class="num">${s.x}</td>
          <td class="mono-sm">${esc(s.y)}</td></tr>`).join('')}
      </tbody></table></div>
      <button class="btn sm primary" id="ss-combine" style="width:100%;margin-top:10px">
        Reconstruct from selected</button>
      <div class="tiny" style="margin-top:6px">Below the threshold, output can be incorrect without an explicit error.</div>
      <div id="ss-result" style="margin-top:10px"></div>`;
    $('#ss-combine').onclick = async () => {
      const picked = $$('.ss-pick:checked').map(c => ({ x: Number(c.dataset.x), y: c.dataset.y }));
      const res = await POST('/api/vault/combine', { share_list: picked });
      $('#ss-result').innerHTML = res.success
        ? `<div class="demo-code" style="border-color:rgba(52,211,153,.5);background:rgba(52,211,153,.08);color:#adf5da">
             <div>Reconstructed (${picked.length} shares)<br><b style="letter-spacing:0">${esc(res.text)}</b></div></div>`
        : `<div class="err" style="display:block">${esc(res.error)} — this is the intended behaviour.</div>`;
    };
  };
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('tags', $('#file-tags') ? $('#file-tags').value : '');
  const r = await fetch('/api/vault/upload', { method: 'POST', body: fd });
  const d = await r.json();
  if (d.success) { toast(`${d.filename} encrypted (${fmtBytes(d.size_bytes)})`); renderVault(); }
  else toast(d.error || 'upload failed', 'err');
}

async function shareDialog(fid) {
  const w = modal('Create expiring share link', `
    <div class="row">
      <label class="field"><span>Valid for (minutes)</span>
        <input class="input" id="sh-ttl" type="number" value="60" min="1"></label>
      <label class="field"><span>Max downloads</span>
        <input class="input" id="sh-max" type="number" value="1" min="1"></label>
    </div>
    <button class="btn primary" id="sh-go" style="width:100%">Generate link</button>
    <div id="sh-out" style="margin-top:14px"></div>`, wrap => {
      $('#sh-go', wrap).onclick = async () => {
        const r = await POST('/api/vault/share/' + fid,
          { ttl_minutes: Number($('#sh-ttl', wrap).value), max_downloads: Number($('#sh-max', wrap).value) });
        if (!r.success) return toast(r.error, 'err');
        $('#sh-out', wrap).innerHTML = `
          <div class="kv"><dt>URL</dt><dd>${esc(location.origin + r.url)}</dd>
            <dt>Expires</dt><dd>${new Date(r.expires_at * 1000).toLocaleString()}</dd>
            <dt>Downloads</dt><dd>${r.max_downloads} (one-time by default)</dd></div>
          <button class="btn sm" id="sh-copy" style="margin-top:10px">Copy link</button>`;
        $('#sh-copy', wrap).onclick = () => {
          navigator.clipboard.writeText(location.origin + r.url); toast('Link copied'); };
      };
    });
}

/* =============================== MODEL LAB =============================== */
async function renderModel() {
  const root = $('#v-model');
  root.innerHTML = `<div class="card">Loading model telemetry…</div>`;
  const [info, versions, drift] = await Promise.all(
    [GET('/api/model/info'), GET('/api/model/versions'), GET('/api/model/drift')]);
  const m = info.model || {}, t = m.test_metrics || {};
  STATE.model = m;
  const scan = m.threshold_scan || [];
  const sel = scan.length ? scan.reduce((a, b) => Math.abs(b.threshold - (t.threshold || 0.5)) <
    Math.abs(a.threshold - (t.threshold || 0.5)) ? b : a) : {};

  root.innerHTML = `
  <div class="grid g-4">
    ${kpi('Holdout accuracy', fmtPct(t.accuracy), `${m.champion}`, 'ok')}
    ${kpi('F1 (success class)', t.f1 ?? '—', `precision ${t.precision} · recall ${t.recall}`, '')}
    ${kpi('ROC-AUC', t.roc_auc ?? '—', `avg precision ${t.avg_precision}`, 'warn')}
    ${kpi('Brier score', t.brier ?? '—', 'lower is better; check reliability too', 'bad')}
  </div>

  <div class="grid g-3">
    <div class="card">
      <div class="hd"><h3>Confusion matrix</h3><span class="tiny">holdout block</span></div>
      ${heatmap(t.confusion || { tn: 0, fp: 0, fn: 0, tp: 0 })}
      <hr class="sep">
      <div class="stat-line"><span>Train rows</span><b>${fmtNum(m.train_rows)}</b></div>
      <div class="stat-line"><span>Test rows</span><b>${fmtNum(m.test_rows)}</b></div>
      <div class="stat-line"><span>Features</span><b>${m.features}</b></div>
      <div class="stat-line"><span>Decision threshold</span><b>${m.threshold}</b></div>
    </div>
    <div class="card">
      <div class="hd"><h3>ROC curve</h3></div>
      ${rocSvg(t.roc_curve, t.roc_auc)}
    </div>
    <div class="card">
      <div class="hd"><h3>Threshold tuning</h3><span class="pill cyan" id="thr-pill">${sel.threshold ?? '—'}</span></div>
      <input type="range" class="slider" id="thr" min="10" max="95" step="5"
        value="${Math.round((sel.threshold || 0.5) * 100)}">
      <div class="tiny" style="margin:4px 0 12px">Sweep the operating point on the validation split;
        threshold chosen for success-class recall ≥ 0.80; slider is exploratory only.</div>
      <div class="stat-line"><span>Precision</span><b id="thr-p">${sel.precision ?? '—'}</b></div>
      <div class="stat-line"><span>Recall</span><b id="thr-r">${sel.recall ?? '—'}</b></div>
      <div class="stat-line"><span>F1</span><b id="thr-f">${sel.f1 ?? '—'}</b></div>
      <div class="stat-line"><span>False positives / negatives</span><b id="thr-e">${sel.fp ?? '—'} / ${sel.fn ?? '—'}</b></div>
      <div id="thr-bars" style="margin-top:12px">
        <div class="tiny">precision</div><div class="bar-mini"><i style="width:${(sel.precision || 0) * 100}%"></i></div>
        <div class="tiny" style="margin-top:8px">recall</div><div class="bar-mini"><i style="width:${(sel.recall || 0) * 100}%"></i></div>
      </div>
    </div>
  </div>

  <div class="grid g-2">
    <div class="card">
      <div class="hd"><h3>Candidate models</h3><span class="tiny">time-ordered split · validation at threshold 0.50</span></div>
      <div class="scroll"><table class="tbl"><thead><tr><th>Model</th><th>Acc</th><th>F1</th><th>AUC</th><th>Recall</th><th>Train</th></tr></thead>
      <tbody>${Object.entries(m.candidates || {}).map(([name, v]) => `<tr>
        <td>${esc(name)} ${name === m.champion ? '<span class="pill ok" style="margin-left:6px">champion</span>' : ''}</td>
        <td class="num">${v.accuracy}</td><td class="num">${v.f1}</td><td class="num">${v.roc_auc}</td>
        <td class="num">${v.recall}</td><td class="num tiny">${v.train_seconds}s</td></tr>`).join('')}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="hd"><h3>Feature importance</h3><span class="tiny">validation permutation importance</span></div>
      ${(m.importance || []).map(f => `<div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;font-size:12px">
          <span class="mono-sm">${esc(f.feature)}</span><span class="mono-sm">${(f.importance * 100).toFixed(1)}%</span></div>
        <div class="bar-mini"><i style="width:${Math.min(100, f.importance * 100)}%"></i></div></div>`).join('')}
    </div>
  </div>

  <div class="grid g-23">
    <div class="card">
      <div class="hd"><h3>Drift monitor</h3>
        <span class="pill ${drift.drifted ? 'bad' : drift.watching ? 'warn' : 'ok'}">
          ${esc(drift.recommendation)}</span></div>
      <div class="tiny" style="margin-bottom:10px">PSI between the reference corpus
        (${fmtNum(drift.reference_rows)} rows) and the synthetic replay corpus (${fmtNum(drift.current_rows)} rows).
        <b>&lt;0.10</b> stable · <b>&lt;0.25</b> watch · <b>≥0.25</b> investigate retraining.</div>
      <div class="scroll"><table class="tbl"><thead><tr><th>Feature</th><th>PSI</th><th></th><th>Status</th></tr></thead>
      <tbody>${(drift.features || []).map(f => `<tr>
        <td class="mono-sm">${esc(f.feature)}</td><td class="num">${f.psi}</td>
        <td style="width:34%"><div class="bar-mini"><i style="width:${Math.min(100, f.psi * 250)}%;
          background:${f.status === 'drift' ? DC.block : f.status === 'watch' ? DC.stepup : DC.allow}"></i></div></td>
        <td><span class="pill ${f.status === 'drift' ? 'bad' : f.status === 'watch' ? 'warn' : 'ok'}">${f.status}</span></td>
      </tr>`).join('')}</tbody></table></div>
    </div>
    <div class="card">
      <div class="hd"><h3>Retrain &amp; promote</h3><span class="pill violet">registry</span></div>
      <button class="btn primary sm" id="retrain-btn" style="width:100%">Retrain champion model</button>
      <pre class="code" id="retrain-log" style="margin-top:12px">idle — the last run logs appear here</pre>
      <hr class="sep">
      <div class="tiny" style="margin-bottom:6px">Version history</div>
      <div class="scroll" style="max-height:210px"><table class="tbl"><thead>
        <tr><th>Version</th><th>Engine</th><th>Acc</th><th></th></tr></thead><tbody>
        ${(versions.versions || []).map(v => {
          const mm = (v.metrics || {}).test || {};
          const deprecated = (v.notes || '').includes('[Deprecated:');
          return `<tr><td class="mono-sm">${esc(v.version)}
            ${v.active ? '<span class="pill ok" style="margin-left:6px">active</span>' : ''}
            ${deprecated ? '<span class="pill warn" style="margin-left:6px">deprecated</span>' : ''}</td>
            <td class="tiny">${esc(v.engine)}</td><td class="num">${mm.accuracy ?? '—'}</td>
            <td style="text-align:right">${v.active || deprecated ? '' :
              `<button class="btn sm ghost" data-act="${v.id}">Promote</button>`}</td></tr>`;
        }).join('')}
      </tbody></table></div>
    </div>
  </div>`;

  const thr = $('#thr');
  if (thr) thr.oninput = () => {
    const val = Number(thr.value) / 100;
    const near = scan.reduce((a, b) => Math.abs(b.threshold - val) < Math.abs(a.threshold - val) ? b : a, scan[0] || {});
    if (!near) return;
    $('#thr-pill').textContent = near.threshold;
    $('#thr-p').textContent = near.p ?? near.precision;
    $('#thr-r').textContent = near.recall;
    $('#thr-f').textContent = near.f1;
    $('#thr-e').textContent = `${near.fp} / ${near.fn}`;
    $('#thr-bars').innerHTML = `<div class="tiny">precision</div>
      <div class="bar-mini"><i style="width:${near.precision * 100}%"></i></div>
      <div class="tiny" style="margin-top:8px">recall</div>
      <div class="bar-mini"><i style="width:${near.recall * 100}%"></i></div>`;
  };

  $('#retrain-btn').onclick = async () => {
    const r = await POST('/api/model/retrain', {});
    if (!r.success) return toast(r.error || 'failed', 'err');
    toast('Retraining started — polling the job log');
    const tick = setInterval(async () => {
      const s = await GET('/api/model/retrain/status');
      $('#retrain-log').innerHTML = (s.log || []).map(l =>
        `<span class="${/error/i.test(l) ? 'e' : 'ok'}">${esc(l)}</span>`).join('\n');
      if (!s.running) { clearInterval(tick); toast(s.result ? 'Retraining finished — champion promoted' : 'Retraining failed; check server logs', s.result ? 'ok' : 'err'); renderModel(); }
    }, 1200);
  };
  $$('[data-act]', root).forEach(b => b.onclick = async () => {
    const r = await POST('/api/model/activate/' + b.dataset.act, {});
    toast(r.success ? 'Promoted ' + r.version : (r.error || 'failed'), r.success ? 'ok' : 'err');
    renderModel();
  });
}

/* ================================ AUDIT ================================ */
async function renderAudit() {
  const root = $('#v-audit');
  const d = await GET('/api/audit/events?limit=120');
  const al = await GET('/api/alerts');
  root.innerHTML = `
  <div class="grid g-23">
    <div class="card">
      <div class="hd"><h3>Hash-chained audit trail</h3>
        <button class="btn sm primary" id="verify-btn">Verify integrity</button></div>
      <div class="tiny" style="margin-bottom:10px">Every row stores <code>H(prev_hash ‖ ts ‖ actor ‖ action ‖ target ‖ meta)</code>.
        Editing or deleting any historical row breaks the chain from that point onward.</div>
      <div id="verify-out"></div>
      <div class="scroll" style="max-height:520px"><table class="tbl"><thead>
        <tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Hash</th></tr></thead><tbody>
        ${(d.events || []).map(e => `<tr>
          <td class="num tiny">${e.id}</td><td class="mono-sm">${fmtTime(e.ts)}</td>
          <td class="mono-sm">${esc(e.actor)}</td><td>${esc(e.action)}</td>
          <td class="tiny">${esc(e.target)}</td>
          <td class="mono-sm tiny">${esc((e.hash || '').slice(0, 10))}…</td></tr>`).join('')}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="hd"><h3>Alerts</h3><span class="pill bad">${al.unacked} open</span></div>
      <div class="scroll" style="max-height:600px">
      ${(al.alerts || []).map(a => `<div style="padding:10px 0;border-bottom:1px solid rgba(23,35,60,.6)">
        <div style="display:flex;gap:9px;align-items:center">
          <span class="pill ${a.severity === 'critical' ? 'bad' : a.severity === 'warning' ? 'warn' : 'cyan'}">${a.severity}</span>
          <div style="flex:1">${esc(a.title)}</div>
          ${a.acked ? '<span class="tiny">acked</span>' :
            `<button class="btn sm ghost" data-ack="${a.id}">Ack</button>`}</div>
        <div class="tiny" style="margin-top:4px">${esc(a.detail || '')} · ${fmtAgo(a.ts)}</div>
      </div>`).join('') || '<div class="tiny">No alerts.</div>'}
      </div>
    </div>
  </div>`;
  $('#verify-btn').onclick = async () => {
    const v = await GET('/api/audit/verify');
    $('#verify-out').innerHTML = v.ok
      ? `<div class="demo-code" style="border-color:rgba(52,211,153,.5);background:rgba(52,211,153,.08);color:#adf5da">
           <div>Chain intact — ${v.checked} rows verified<br><span class="tiny">head ${esc((v.head || '').slice(0, 24))}…</span></div></div>`
      : `<div class="err" style="display:block">Chain broken at row #${v.broken_at} (checked ${v.checked})</div>`;
  };
  $$('[data-ack]', root).forEach(b => b.onclick = async () => {
    await POST('/api/alerts/' + b.dataset.ack + '/ack', {}); renderAudit(); });
  refreshAlertBadge(al.unacked);
}

/* ================================ ADMIN ================================ */
async function renderAdmin() {
  const root = $('#v-admin');
  const [u, s, ap] = await Promise.all([GET('/api/admin/users'), GET('/api/admin/sessions'),
                                        GET('/api/admin/approvals')]);
  if (!u.success) {
    root.innerHTML = `<div class="card">Administrator role required for this view.</div>`; return;
  }
  root.innerHTML = `
  <div class="card">
    <div class="hd"><h3>Users &amp; roles</h3><span class="pill violet">RBAC</span></div>
    <div class="scroll"><table class="tbl"><thead><tr><th>User</th><th>Email</th><th>Role</th>
      <th>MFA</th><th>Status</th><th>Failed</th><th>Last login</th><th></th></tr></thead><tbody>
      ${u.users.map(x => `<tr>
        <td><b>${esc(x.username)}</b></td><td class="tiny">${esc(x.email)}</td>
        <td><select class="input" style="padding:5px 8px;font-size:12px" data-role="${x.id}">
          ${['admin', 'analyst', 'user'].map(r => `<option ${r === x.role ? 'selected' : ''}>${r}</option>`).join('')}
        </select></td>
        <td>${x.totp_enabled ? '<span class="pill ok">TOTP</span>' : '<span class="pill warn">email OTP</span>'}</td>
        <td>${x.status === 'active' ? '<span class="pill ok">active</span>' : '<span class="pill bad">suspended</span>'}</td>
        <td class="num">${x.failed_attempts}</td>
        <td class="tiny">${x.last_login ? fmtAgo(x.last_login) : 'never'}</td>
        <td style="text-align:right;white-space:nowrap">
          <button class="btn sm ghost" data-sus="${x.id}" data-to="${x.status === 'active' ? 'suspended' : 'active'}">
            ${x.status === 'active' ? 'Suspend' : 'Reinstate'}</button>
          <button class="btn sm ghost" data-unlock="${x.id}">Unlock</button></td>
      </tr>`).join('')}
    </tbody></table></div>
  </div>

  <div class="grid g-2">
    <div class="card">
      <div class="hd"><h3>Demo review queue</h3><span class="pill bad">
        ${ap.approvals.filter(a => a.status === 'pending').length} pending</span></div>
      <div class="scroll" style="max-height:420px"><table class="tbl"><thead>
        <tr><th>#</th><th>Identity</th><th>Risk</th><th>Decision</th><th></th></tr></thead><tbody>
        ${ap.approvals.map(a => `<tr>
          <td class="num tiny">${a.decision_id}</td><td class="mono-sm">${esc(a.actor)}</td>
          <td class="num">${(a.risk_score || 0).toFixed(0)}</td>
          <td><span class="tag ${a.decision}">${a.decision}</span></td>
          <td style="text-align:right;white-space:nowrap">${a.status === 'pending' ? `
            <button class="btn sm ghost" data-app="${a.id}" data-st="approved">Approve</button>
            <button class="btn sm danger" data-app="${a.id}" data-st="rejected">Reject</button>`
            : `<span class="pill ${a.status === 'approved' ? 'ok' : 'bad'}">${a.status}</span>`}</td></tr>`).join('')
        || '<tr><td colspan="5" class="tiny">Queue is empty.</td></tr>'}
      </tbody></table></div>
    </div>
    <div class="card">
      <div class="hd"><h3>Active sessions</h3><span class="tiny">server-side revocable</span></div>
      <div class="scroll" style="max-height:420px"><table class="tbl"><thead>
        <tr><th>User</th><th>IP</th><th>Last seen</th><th>State</th></tr></thead><tbody>
        ${s.sessions.map(x => `<tr><td class="mono-sm">${esc(x.username)}</td>
          <td class="mono-sm">${esc(x.ip)}</td><td class="tiny">${fmtAgo(x.last_seen)}</td>
          <td>${x.revoked ? '<span class="pill bad">revoked</span>' : '<span class="pill ok">active</span>'}</td></tr>`).join('')}
      </tbody></table></div>
    </div>
  </div>`;

  $$('[data-role]', root).forEach(s2 => s2.onchange = async () => {
    await POST('/api/admin/users/' + s2.dataset.role, { role: s2.value });
    toast('Role updated'); });
  $$('[data-sus]', root).forEach(b => b.onclick = async () => {
    await POST('/api/admin/users/' + b.dataset.sus, { status: b.dataset.to });
    toast('Status updated'); renderAdmin(); });
  $$('[data-unlock]', root).forEach(b => b.onclick = async () => {
    await POST('/api/admin/users/' + b.dataset.unlock, { unlock: true });
    toast('Account unlocked'); renderAdmin(); });
  $$('[data-app]', root).forEach(b => b.onclick = async () => {
    await POST('/api/admin/approvals/' + b.dataset.app, { status: b.dataset.st });
    toast('Approval ' + b.dataset.st); renderAdmin(); });
}

/* ================================= boot ================================= */
(async function boot() {
  try {
    const me = await GET('/api/auth/me');
    if (!me.success) { location.href = '/'; return; }
    STATE.user = me;
    if (me.role !== 'admin') $('#nav-admin').style.display = 'none';
  } catch (e) { return; }

  $$('.nav-item[data-view]').forEach(n => n.onclick = () => go(n.dataset.view));
  $('#nav-logout').onclick = async () => { await POST('/api/auth/logout', {}); location.href = '/'; };

  const start = (location.hash || '#overview').slice(1);
  go(VIEW_META[start] ? start : 'overview');

  setInterval(async () => {
    if (STATE.view === 'overview' && !document.hidden) {
      STATE.overview = null; renderOverview();
    }
  }, 30000);
  GET('/api/alerts').then(a => refreshAlertBadge(a.unacked || 0));
})();
