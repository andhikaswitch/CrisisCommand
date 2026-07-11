// REST client. Three deploy shapes:
//  - dev: vite proxies /api to the backend (vite.config.js)
//  - docker/full host: same-origin /api, live backend
//  - static showcase (VITE_DEMO_DATA=1): no backend at all. Reads pre-baked
//    JSON from demo-data/ so the app runs on a card-free static host
//    (Netlify Drop, Cloudflare Pages, GitHub Pages). Simulation results and
//    AI briefings are captured once by scripts/bake_demo_data.py.
const BASE = import.meta.env.VITE_API_BASE || '';
const DEMO = import.meta.env.VITE_DEMO_DATA === '1';
const DEMO_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`;

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

const get = (path) => getJson(`${BASE}${path}`);
const post = (path) =>
  fetch(`${BASE}${path}`, { method: 'POST' }).then((r) => {
    if (!r.ok) throw new Error(`${path} -> ${r.status}`);
    return r.json();
  });

export const fetchEvents = () =>
  DEMO ? getJson(`${DEMO_BASE}/events.json`) : get('/api/events');
export const fetchHealth = () =>
  DEMO ? Promise.resolve({ status: 'ok', seed_mode: true }) : get('/api/health');
export const fetchStatus = () =>
  DEMO ? getJson(`${DEMO_BASE}/status.json`) : get('/api/status');
export const fetchGpu = () =>
  DEMO
    ? Promise.resolve({ device: 'cpu', backend: 'cpu', vram_total_gb: null, vram_used_gb: null })
    : get('/api/health/gpu');
export const fetchBriefing = (id) =>
  DEMO ? getJson(`${DEMO_BASE}/brief-${id}.json`) : post(`/api/events/${id}/brief`);
export const runSimulation = (id, horizon = '24h') =>
  DEMO ? getJson(`${DEMO_BASE}/sim-${id}.json`) : post(`/api/events/${id}/simulate?horizon=${horizon}`);

export function fmtRange([lo, hi], unit = '') {
  const f = (n) =>
    n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
    : n >= 1e3 ? `${Math.round(n / 1e3)}K`
    : `${n}`;
  return `${unit}${f(lo)}–${unit}${f(hi)}`;
}

// Severity palette thresholds per UI_DESIGN.md §3.
export function severityColor(event) {
  if (event.kind === 'tension') return 'var(--tension-violet)';
  if (event.severity >= 0.7) return 'var(--alert-red)';
  if (event.severity >= 0.4) return 'var(--alert-amber)';
  return 'var(--alert-teal)';
}

// Raw hex values for WebGL layers (CSS vars don't reach three.js materials).
export function severityHex(event, alpha = 1) {
  const hex =
    event.kind === 'tension' ? '#a78bfa'
    : event.severity >= 0.7 ? '#f43f5e'
    : event.severity >= 0.4 ? '#fbbf24'
    : '#2dd4bf';
  if (alpha >= 1) return hex;
  const a = Math.round(alpha * 255).toString(16).padStart(2, '0');
  return hex + a;
}
